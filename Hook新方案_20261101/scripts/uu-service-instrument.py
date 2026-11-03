#!/usr/bin/env python3
"""Temporarily instrument the current user's UU Service launch job.

Only start/restore mutate launchd state. A reversible LoadWitness experiment was
executed and restored on 2026-11-01; see docs/UU加载验证.md for the negative loading result.
Help and syntax checks do not launch/stop any application.
No sudo, original plist edit, app modification, resigning, or GUI/Server kill.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parents[1]
ARTIFACTS = (BASE / 'artifacts').resolve()
SOURCE = Path('/Library/LaunchAgents/com.netease.uuremote.agent.plist')
LABEL = 'com.netease.uuremote.agent'
PROGRAM = '/Applications/UURemote.app/Contents/MacOS/UURemoteService'
APP_PREFIX = '/Applications/UURemote.app/'
LAUNCHCTL = '/bin/launchctl'
STATE_NAME = 'instrumentation-state.json'
SCHEMA = 1


class InstrumentError(RuntimeError):
    pass


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def within(path, parent):
    try:
        path.relative_to(parent)
        return path != parent
    except ValueError:
        return False


def run_dir(value):
    p = Path(value).expanduser().resolve()
    if not within(p, ARTIFACTS):
        raise InstrumentError('Run directory must be a new child of this project artifacts directory.')
    return p


def domain():
    if os.geteuid() == 0 or os.getuid() != os.geteuid():
        raise InstrumentError('Run as the ordinary logged-in user, without sudo or changed effective UID.')
    return f'gui/{os.getuid()}'


def atomic_json(path, data):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as f:
        os.chmod(temporary, 0o600)
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    os.replace(temporary, path)


def save(state):
    state['updatedAtUTC'] = utc()
    atomic_json(Path(state['runDirectory']) / STATE_NAME, state)


def event(state, name, **fields):
    state.setdefault('events', []).append({'atUTC': utc(), 'event': name, **fields})
    save(state)


def call_launchctl(arguments):
    try:
        r = subprocess.run([LAUNCHCTL, *arguments], capture_output=True, text=True,
                           timeout=15, check=False)
        # Never retain raw `print` output: it may include unrelated environment values.
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        raise InstrumentError('launchctl timed out; its resulting job state must be checked.')


def probe_job(dom):
    rc, output, _ = call_launchctl(['print', f'{dom}/{LABEL}'])
    result = {'serviceTarget': f'{dom}/{LABEL}', 'loaded': rc == 0,
              'printReturnCode': rc}
    if rc == 0:
        for key, output_key in [('path', 'definitionPath'), ('program', 'program'),
                                ('state', 'state'), ('pid', 'pid'),
                                ('last exit code', 'lastExitCode')]:
            match = re.search(r'^\s*' + re.escape(key) + r'\s*=\s*(.*?)\s*$', output, re.M)
            if match:
                value = match.group(1)
                result[output_key] = int(value) if key in ('pid', 'last exit code') and value.lstrip('-').isdigit() else value
    return result


def process_snapshot():
    r = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,uid=,comm='],
                       capture_output=True, text=True, timeout=10, check=True)
    result = []
    for line in r.stdout.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) == 4 and parts[3].startswith(APP_PREFIX):
            result.append({'pid': int(parts[0]), 'parentPID': int(parts[1]),
                           'uid': int(parts[2]), 'executable': parts[3]})
    return result


def plist_identity(data):
    if not isinstance(data, dict) or data.get('Label') != LABEL:
        raise InstrumentError('Unexpected launch job Label; refusing to operate.')
    argv = data.get('ProgramArguments', [])
    program = data.get('Program') or (argv[0] if isinstance(argv, list) and argv else None)
    if program != PROGRAM:
        raise InstrumentError('Unexpected launch job executable; refusing to operate.')
    # Avoid ambiguous executable selection if both forms exist.
    if argv and (not isinstance(argv, list) or argv[0] != PROGRAM):
        raise InstrumentError('Unexpected ProgramArguments executable; refusing to operate.')


def read_original(expected_hash=None):
    raw = SOURCE.read_bytes()
    actual_hash = hashlib.sha256(raw).hexdigest()
    if expected_hash is not None and actual_hash != expected_hash:
        raise InstrumentError('Original /Library plist hash changed; refusing to use a changed job definition.')
    data = plistlib.loads(raw)
    plist_identity(data)
    return raw, data, actual_hash


def expected_job(job, definition):
    return (job.get('loaded') is True and
            job.get('definitionPath') == str(definition) and
            job.get('program') == PROGRAM)


def require_allowed_loaded_job(job, allowed):
    if job.get('loaded'):
        if job.get('definitionPath') not in {str(x) for x in allowed} or job.get('program') != PROGRAM:
            raise InstrumentError('Loaded exact-label job has an unexpected definition path or executable; refusing to remove it.')
    elif job.get('printReturnCode') != 113:
        # `launchctl print` uses ESRCH 113 when a service is absent on this macOS.
        # Any other failure is not safely interpretable as an absent job.
        raise InstrumentError('Cannot establish whether the exact-label job exists; launchctl print did not return the expected absent-service status.')


def wait_for(dom, definition=None, seconds=4, require_running=False):
    deadline = time.monotonic() + seconds
    last = probe_job(dom)
    while time.monotonic() < deadline:
        if definition is None:
            if not last.get('loaded') and last.get('printReturnCode') == 113:
                return last
        elif expected_job(last, definition):
            if not require_running or (last.get('state') == 'running' and isinstance(last.get('pid'), int) and last['pid'] > 0):
                return last
        time.sleep(0.25)
        last = probe_job(dom)
    return last


def load_state(directory):
    state = json.loads((directory / STATE_NAME).read_text())
    dom = domain()
    if (state.get('schema') != SCHEMA or state.get('runDirectory') != str(directory)
            or state.get('sourcePlist') != str(SOURCE) or state.get('label') != LABEL
            or state.get('domain') != dom or state.get('program') != PROGRAM
            or state.get('modifiedPlist') != str(directory / 'instrumented-job.plist')):
        raise InstrumentError('Saved state identity does not match this script, user, or exact job.')
    return state


def restore_original(state, reason):
    """Best effort rollback, with identity checks before every job removal."""
    dom = state['domain']
    modified = Path(state['modifiedPlist'])
    read_original(state['originalPlistSHA256'])
    current = probe_job(dom)
    require_allowed_loaded_job(current, [SOURCE, modified])
    event(state, 'restore-begin', reason=reason, jobBefore=current)
    if expected_job(current, modified):
        rc, _, _ = call_launchctl(['bootout', f'{dom}/{LABEL}'])
        event(state, 'restore-bootout-instrumented', returnCode=rc)
        current = wait_for(dom)
        if current.get('loaded') or current.get('printReturnCode') != 113:
            raise InstrumentError('Instrumented job did not unload; refusing to bootstrap over an uncertain state.')
    # Re-check source and job immediately before bootstrap to reduce race exposure.
    read_original(state['originalPlistSHA256'])
    current = probe_job(dom)
    require_allowed_loaded_job(current, [SOURCE])
    if not current.get('loaded'):
        rc, _, _ = call_launchctl(['bootstrap', dom, str(SOURCE)])
        event(state, 'restore-bootstrap-original', returnCode=rc)
        current = wait_for(dom, SOURCE)
        if not expected_job(current, SOURCE):
            raise InstrumentError('Original job was not restored at the expected path/executable.')
    state['status'] = 'restored'
    state['restoredAtUTC'] = utc()
    state['jobAfterRestore'] = current
    state['processesAfterRestore'] = process_snapshot()
    state['restoreNote'] = 'Original job restored; existing UU GUI/Server processes were not terminated. No claim that remote capture resumed.'
    event(state, 'restore-completed')
    return current


def start(args):
    directory = run_dir(args.run_dir)
    if directory.exists():
        raise InstrumentError('Run directory already exists; refusing to overwrite a previous experiment.')
    dom = domain()
    library = Path(args.library).expanduser().resolve(strict=True)
    config = Path(args.config).expanduser().resolve(strict=True)
    log = Path(args.log).expanduser().resolve()
    if not within(library, BASE) or library.suffix != '.dylib' or not library.is_file() or ':' in str(library):
        raise InstrumentError('Library must be one existing .dylib in this project; colon-separated library lists are not accepted.')
    if not within(config, BASE) or not config.is_file():
        raise InstrumentError('Config must be one existing file in this project.')
    if not isinstance(json.loads(config.read_text()), dict):
        raise InstrumentError('Hook config must be a JSON object.')
    if not within(log, directory) or log.exists():
        raise InstrumentError('Log must be a new file beneath the new run directory.')
    raw, original, original_hash = read_original()
    before = probe_job(dom)
    if not expected_job(before, SOURCE):
        raise InstrumentError('Start requires the original exact-label job to be loaded from the original plist path.')
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    log.parent.mkdir(parents=True, exist_ok=True)
    backup = directory / 'original-job.plist'
    backup.write_bytes(raw)
    os.chmod(backup, 0o600)
    modified = directory / 'instrumented-job.plist'
    env = original.get('EnvironmentVariables', {})
    if not isinstance(env, dict):
        raise InstrumentError('Original EnvironmentVariables is not a dictionary.')
    configured = dict(env)
    configured.update({'DYLD_INSERT_LIBRARIES': str(library), 'HOOK_DEMO_LOG': str(log),
                       'HOOK_DEMO_MODE': args.mode, 'HOOK_DEMO_CONFIG': str(config)})
    original['EnvironmentVariables'] = configured
    modified.write_bytes(plistlib.dumps(original, fmt=plistlib.FMT_XML, sort_keys=False))
    os.chmod(modified, 0o600)
    state = {'schema': SCHEMA, 'createdAtUTC': utc(), 'status': 'prepared',
             'runDirectory': str(directory), 'sourcePlist': str(SOURCE),
             'originalPlistSHA256': original_hash, 'originalBackup': str(backup),
             'modifiedPlist': str(modified), 'modifiedPlistSHA256': digest(modified),
             'label': LABEL, 'domain': dom, 'program': PROGRAM,
             'library': str(library), 'librarySHA256': digest(library),
             'config': str(config), 'configSHA256': digest(config),
             'log': str(log), 'mode': args.mode,
             'jobBefore': before, 'processesBefore': process_snapshot(),
             'events': [], 'libraryLoaded': 'unverified', 'captureHookHit': 'unverified',
             'remoteRedaction': 'unverified'}
    save(state)
    try:
        read_original(original_hash)
        current = probe_job(dom)
        if not expected_job(current, SOURCE):
            raise InstrumentError('Original job changed before mutation.')
        state['status'] = 'replacing'
        event(state, 'bootout-original-requested')
        rc, _, _ = call_launchctl(['bootout', f'{dom}/{LABEL}'])
        event(state, 'bootout-original-returned', returnCode=rc)
        absent = wait_for(dom)
        if absent.get('loaded') or absent.get('printReturnCode') != 113:
            raise InstrumentError('Original job did not unload; replacement aborted.')
        read_original(original_hash)
        if digest(modified) != state['modifiedPlistSHA256']:
            raise InstrumentError('Instrumented plist changed before bootstrap.')
        plist_identity(plistlib.loads(modified.read_bytes()))
        event(state, 'bootstrap-instrumented-requested')
        rc, _, _ = call_launchctl(['bootstrap', dom, str(modified)])
        event(state, 'bootstrap-instrumented-returned', returnCode=rc)
        installed = wait_for(dom, modified, seconds=8, require_running=True)
        if not expected_job(installed, modified):
            raise InstrumentError('Instrumented job was not registered at the expected path/executable.')
        if installed.get('state') != 'running' or not isinstance(installed.get('pid'), int) or installed['pid'] <= 0:
            raise InstrumentError('Instrumented UU Service did not reach a running state with a PID; restoring original job.')
        state['status'] = 'instrumented-job-registered'
        state['jobAfterStart'] = installed
        state['processesAfterStart'] = process_snapshot()
        state['note'] = 'Job registration is not proof of hook library loading, capture API calls, or remote redaction. Existing UU GUI/Server processes were not killed.'
        event(state, 'start-completed')
    except BaseException as error:
        state['startError'] = f'{type(error).__name__}: {error}'
        save(state)
        try:
            restore_original(state, 'automatic rollback after start failure')
            state['automaticRollbackSucceeded'] = True
        except BaseException as rollback_error:
            state['status'] = 'rollback-failed'
            state['automaticRollbackSucceeded'] = False
            state['rollbackError'] = f'{type(rollback_error).__name__}: {rollback_error}'
        save(state)
        raise InstrumentError('Start failed. Review the saved state for automatic rollback outcome: ' + str(directory / STATE_NAME)) from error
    print(json.dumps({'status': state['status'], 'runDirectory': str(directory),
                      'job': state['jobAfterStart'], 'hookLibraryLoaded': 'unverified',
                      'existingUUProcessesWereNotKilled': True}, ensure_ascii=False, indent=2))


def status(args):
    directory = run_dir(args.run_dir)
    state = load_state(directory)
    _, _, current_hash = read_original()
    result = {'atUTC': utc(), 'recordedStatus': state['status'], 'domain': state['domain'],
              'label': LABEL, 'originalPlistHashMatches': current_hash == state['originalPlistSHA256'],
              'job': probe_job(state['domain']), 'processes': process_snapshot(),
              'note': 'Process presence does not prove hook loading or successful redaction.'}
    atomic_json(directory / 'last-status.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def restore(args):
    directory = run_dir(args.run_dir)
    state = load_state(directory)
    try:
        restored = restore_original(state, 'explicit restore command')
    except BaseException as error:
        state['status'] = 'restore-failed'
        state['restoreError'] = f'{type(error).__name__}: {error}'
        save(state)
        raise
    print(json.dumps({'status': state['status'], 'job': restored,
                      'originalPlistHashUnchanged': True,
                      'existingUUProcessesWereNotKilled': True}, ensure_ascii=False, indent=2))


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('start', help='Temporarily replace only the current user UU Service job; auto-restore on failure.')
    s.add_argument('--run-dir', required=True, help='New non-existing directory below this project artifacts/.')
    s.add_argument('--library', required=True, help='Existing hook .dylib inside this project.')
    s.add_argument('--config', required=True, help='Existing hook JSON config inside this project.')
    s.add_argument('--log', required=True, help='New hook log path below --run-dir.')
    s.add_argument('--mode', choices=['audit', 'block'], default='audit')
    s.set_defaults(handler=start)
    for name, help_text, handler in [('status', 'Read exact-label job status and write a metadata-only snapshot.', status),
                                     ('restore', 'Restore the original loaded job from /Library after checking its hash.', restore)]:
        q = sub.add_parser(name, help=help_text)
        q.add_argument('--run-dir', required=True)
        q.set_defaults(handler=handler)
    return p.parse_args()


def main():
    args = parse_args()
    try:
        args.handler(args)
        return 0
    except (InstrumentError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({'error': str(error), 'type': type(error).__name__}, ensure_ascii=False), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({'error': 'Interrupted; check saved state and restore outcome.'}), file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
