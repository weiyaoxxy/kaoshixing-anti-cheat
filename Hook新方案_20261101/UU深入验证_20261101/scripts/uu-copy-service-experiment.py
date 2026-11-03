#!/usr/bin/env python3
"""Temporarily run the copied UU Service through one recoverable user job.

Only start/restore mutate launchd state. This script has been prepared but not
executed against a job during its authoring. Syntax and --help are read-only.
The original /Library plist and /Applications app are never modified. The only
experimental executable is sandbox-apps/UURemote-Test-Resigned.app/.../UURemoteService.
No sudo, root-process kill, app resigning, TCC/SIP change, GUI or Server kill.
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
BUILD = (BASE / 'build').resolve()
RUNTIME_ROOT = Path.home() / 'Library/Caches/ExamHookUULab/20261101-runtime'
RUNTIME_BUILD = RUNTIME_ROOT / 'build'
RUNTIME_CONFIG = RUNTIME_ROOT / 'hook-config.json'
PARENT_NATIVE_CONFIG = (BASE.parent / 'artifacts/native-session-20261101T132925Z/hook-config.json').resolve()
SOURCE = Path('/Library/LaunchAgents/com.netease.uuremote.agent.plist')
LABEL = 'com.netease.uuremote.agent'
PROGRAM = '/Applications/UURemote.app/Contents/MacOS/UURemoteService'
COPY_APP = BASE / 'sandbox-apps/UURemote-Test-Resigned.app'
COPY_PROGRAM = str(COPY_APP / 'Contents/MacOS/UURemoteService')
APP_PREFIXES = ('/Applications/UURemote.app/', str(COPY_APP) + '/')
LAUNCHCTL = '/bin/launchctl'
STATE_NAME = 'instrumentation-state.json'
SCHEMA = 2


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
        if len(parts) == 4 and parts[3].startswith(APP_PREFIXES):
            result.append({'pid': int(parts[0]), 'parentPID': int(parts[1]),
                           'uid': int(parts[2]), 'executable': parts[3],
                           'applicationOrigin': 'original' if parts[3].startswith(APP_PREFIXES[0]) else 'experimental-copy'})
    return result


def plist_identity(data, expected_program):
    if not isinstance(data, dict) or data.get('Label') != LABEL:
        raise InstrumentError('Unexpected launch job Label; refusing to operate.')
    argv = data.get('ProgramArguments', [])
    program = data.get('Program') or (argv[0] if isinstance(argv, list) and argv else None)
    if program != expected_program:
        raise InstrumentError('Unexpected launch job executable; refusing to operate.')
    # Avoid ambiguous executable selection if both forms exist.
    if argv and (not isinstance(argv, list) or argv[0] != expected_program):
        raise InstrumentError('Unexpected ProgramArguments executable; refusing to operate.')


def read_original(expected_hash=None):
    raw = SOURCE.read_bytes()
    actual_hash = hashlib.sha256(raw).hexdigest()
    if expected_hash is not None and actual_hash != expected_hash:
        raise InstrumentError('Original /Library plist hash changed; refusing to use a changed job definition.')
    data = plistlib.loads(raw)
    plist_identity(data, PROGRAM)
    return raw, data, actual_hash


def expected_job(job, definition, expected_program):
    return (job.get('loaded') is True and
            job.get('definitionPath') == str(definition) and
            job.get('program') == expected_program)


def require_allowed_loaded_job(job, allowed):
    if job.get('loaded'):
        identities = {(str(definition), program) for definition, program in allowed}
        if (job.get('definitionPath'), job.get('program')) not in identities:
            raise InstrumentError('Loaded exact-label job has an unexpected definition path or executable; refusing to remove it.')
    elif job.get('printReturnCode') != 113:
        # `launchctl print` uses ESRCH 113 when a service is absent on this macOS.
        # Any other failure is not safely interpretable as an absent job.
        raise InstrumentError('Cannot establish whether the exact-label job exists; launchctl print did not return the expected absent-service status.')


def wait_for(dom, definition=None, expected_program=None, seconds=4, require_running=False):
    deadline = time.monotonic() + seconds
    last = probe_job(dom)
    while time.monotonic() < deadline:
        if definition is None:
            if not last.get('loaded') and last.get('printReturnCode') == 113:
                return last
        elif expected_job(last, definition, expected_program):
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
            or state.get('copyProgram') != COPY_PROGRAM
            or state.get('modifiedPlist') != str(directory / 'instrumented-job.plist')):
        raise InstrumentError('Saved state identity does not match this script, user, or exact job.')
    return state


def restore_original(state, reason):
    """Best effort rollback, with identity checks before every job removal."""
    dom = state['domain']
    modified = Path(state['modifiedPlist'])
    read_original(state['originalPlistSHA256'])
    current = probe_job(dom)
    require_allowed_loaded_job(current, [(SOURCE, PROGRAM), (modified, COPY_PROGRAM)])
    event(state, 'restore-begin', reason=reason, jobBefore=current)
    if expected_job(current, modified, COPY_PROGRAM):
        rc, _, _ = call_launchctl(['bootout', f'{dom}/{LABEL}'])
        event(state, 'restore-bootout-instrumented', returnCode=rc)
        current = wait_for(dom)
        if current.get('loaded') or current.get('printReturnCode') != 113:
            raise InstrumentError('Instrumented job did not unload; refusing to bootstrap over an uncertain state.')
    # Re-check source and job immediately before bootstrap to reduce race exposure.
    read_original(state['originalPlistSHA256'])
    current = probe_job(dom)
    require_allowed_loaded_job(current, [(SOURCE, PROGRAM)])
    if not current.get('loaded'):
        rc, _, _ = call_launchctl(['bootstrap', dom, str(SOURCE)])
        event(state, 'restore-bootstrap-original', returnCode=rc)
        current = wait_for(dom, SOURCE, PROGRAM)
        if not expected_job(current, SOURCE, PROGRAM):
            raise InstrumentError('Original job was not restored at the expected path/executable.')
    state['status'] = 'restored'
    state['restoredAtUTC'] = utc()
    state['jobAfterRestore'] = current
    state['processesAfterRestore'] = process_snapshot()
    state['restoreNote'] = 'Original Service job restored at the original path and executable. Existing original/copy GUI/Server processes were not explicitly terminated; job removal can affect its managed service. No claim that remote capture resumed.'
    event(state, 'restore-completed')
    return current


def start(args):
    directory = run_dir(args.run_dir)
    if directory.exists():
        raise InstrumentError('Run directory already exists; refusing to overwrite a previous experiment.')
    dom = domain()
    library = Path(args.library).expanduser().resolve(strict=True)
    config = Path(args.config).expanduser().resolve(strict=True)
    log_input = Path(args.log).expanduser()
    log = log_input.resolve()
    runtime_log = RUNTIME_ROOT / 'runs' / directory.name / 'hook.jsonl'
    # Canonical candidate paths are compared with these fixed lexical cache
    # paths, so a cache symlink cannot widen access to some unrelated directory.
    runtime_used = within(library, RUNTIME_BUILD) or config == RUNTIME_CONFIG or log == runtime_log
    if runtime_used and RUNTIME_ROOT.resolve() != RUNTIME_ROOT:
        raise InstrumentError('The fixed runtime cache root must not resolve to a different directory.')
    if not (within(library, BUILD) or within(library, RUNTIME_BUILD)) or library.suffix != '.dylib' or not library.is_file() or ':' in str(library):
        raise InstrumentError('Library must be one existing .dylib inside this experiment build/ or the fixed runtime cache build/; library lists are not accepted.')
    if not config.is_file() or not (within(config, BASE) or config == PARENT_NATIVE_CONFIG or config == RUNTIME_CONFIG):
        raise InstrumentError('Config must be inside this experiment, the exact parent native-session-20261101T132925Z/hook-config.json, or fixed runtime cache hook-config.json.')
    if not isinstance(json.loads(config.read_text()), dict):
        raise InstrumentError('Hook config must be a JSON object.')
    if not (within(log, directory) or log == runtime_log) or log.exists() or log_input.is_symlink():
        raise InstrumentError('Log must be new: inside the new run directory, or exactly runtime/runs/<run-dir.name>/hook.jsonl. Existing files and symlinks are refused.')
    copy_executable = Path(COPY_PROGRAM)
    if (not copy_executable.is_file() or copy_executable.resolve(strict=True) != copy_executable
            or not os.access(copy_executable, os.X_OK)):
        raise InstrumentError('Expected fixed copy Service executable is absent, non-executable, or resolves outside the fixed copy path.')
    copy_hash = digest(copy_executable)
    raw, original, original_hash = read_original()
    argv = original.get('ProgramArguments')
    if not isinstance(argv, list) or not argv or argv[0] != PROGRAM or not all(isinstance(v, str) for v in argv):
        raise InstrumentError('Original ProgramArguments must start with the exact original Service followed by string arguments.')
    env = original.get('EnvironmentVariables', {})
    if not isinstance(env, dict):
        raise InstrumentError('Original EnvironmentVariables is not a dictionary.')
    before = probe_job(dom)
    if not expected_job(before, SOURCE, PROGRAM):
        raise InstrumentError('Start requires the original exact-label job to be loaded from the original plist path.')
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    log.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    backup = directory / 'original-job.plist'
    backup.write_bytes(raw)
    os.chmod(backup, 0o600)
    modified = directory / 'instrumented-job.plist'
    # Preserve every argument after argv[0], MachServices, WorkingDirectory,
    # and other original keys. Program (when present) must agree with argv[0].
    original['ProgramArguments'] = [COPY_PROGRAM, *argv[1:]]
    if 'Program' in original:
        original['Program'] = COPY_PROGRAM
    configured = dict(env)
    configured.update({'DYLD_INSERT_LIBRARIES': str(library), 'HOOK_DEMO_LOG': str(log),
                       'HOOK_DEMO_MODE': args.mode, 'HOOK_DEMO_CONFIG': str(config)})
    original['EnvironmentVariables'] = configured
    plist_identity(original, COPY_PROGRAM)
    modified.write_bytes(plistlib.dumps(original, fmt=plistlib.FMT_XML, sort_keys=False))
    os.chmod(modified, 0o600)
    state = {'schema': SCHEMA, 'createdAtUTC': utc(), 'status': 'prepared',
             'runDirectory': str(directory), 'sourcePlist': str(SOURCE),
             'originalPlistSHA256': original_hash, 'originalBackup': str(backup),
             'modifiedPlist': str(modified), 'modifiedPlistSHA256': digest(modified),
             'label': LABEL, 'domain': dom, 'program': PROGRAM,
             'copyProgram': COPY_PROGRAM, 'copyProgramSHA256': copy_hash,
             'copyApplication': str(COPY_APP), 'processPrefixes': list(APP_PREFIXES),
             'runtimeRoot': str(RUNTIME_ROOT), 'runtimeCacheUsed': runtime_used,
             'originalProgramArguments': argv, 'originalWorkingDirectory': original.get('WorkingDirectory'),
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
        if not expected_job(current, SOURCE, PROGRAM):
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
        plist_identity(plistlib.loads(modified.read_bytes()), COPY_PROGRAM)
        if digest(copy_executable) != copy_hash:
            raise InstrumentError('Copy Service executable changed after preparation; replacement aborted.')
        if digest(library) != state['librarySHA256']:
            raise InstrumentError('Experiment library changed after preparation; replacement aborted.')
        event(state, 'bootstrap-instrumented-requested')
        rc, _, _ = call_launchctl(['bootstrap', dom, str(modified)])
        event(state, 'bootstrap-instrumented-returned', returnCode=rc)
        installed = wait_for(dom, modified, COPY_PROGRAM, seconds=8, require_running=True)
        if not expected_job(installed, modified, COPY_PROGRAM):
            raise InstrumentError('Instrumented job was not registered at the exact experiment plist path and copied Service executable.')
        if installed.get('state') != 'running' or not isinstance(installed.get('pid'), int) or installed['pid'] <= 0:
            raise InstrumentError('Copied UU Service did not reach a running state with a PID; restoring original job.')
        state['status'] = 'instrumented-job-registered'
        state['jobAfterStart'] = installed
        state['processesAfterStart'] = process_snapshot()
        state['note'] = 'Copied Service job registration is not proof of library loading, capture API calls, or remote redaction. Snapshot includes original and copied app paths; a child may come from either. Existing UU GUI/Server processes were not explicitly killed.'
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
                      'noExplicitGUIOrServerKill': True, 'jobServiceMayRestart': True}, ensure_ascii=False, indent=2))


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
                      'noExplicitGUIOrServerKill': True, 'jobServiceMayRestart': True}, ensure_ascii=False, indent=2))


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('start', help='Temporarily run the fixed copied Service under the exact user job; restore original on failure.')
    s.add_argument('--run-dir', required=True, help='New non-existing directory below this project artifacts/.')
    s.add_argument('--library', required=True, help='Existing .dylib inside this experiment build/ or ~/Library/Caches/ExamHookUULab/20261101-runtime/build/. No library list.')
    s.add_argument('--config', required=True, help='Existing JSON config in this experiment, the exact parent native-session-20261101T132925Z/hook-config.json, or fixed runtime/hook-config.json.')
    s.add_argument('--log', required=True, help='New log beneath --run-dir, or exactly ~/Library/Caches/ExamHookUULab/20261101-runtime/runs/<run-dir.name>/hook.jsonl.')
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
