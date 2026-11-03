#!/usr/bin/env python3
"""Bounded audit-only experiment for the current user's original AweSun agent.

The single `run` controller owns both replacement and restoration. Request an
early restore by creating RUN/restore.request or sending SIGINT/SIGTERM to this
controller. It never kills child sessions, changes a root job, edits an original
plist, or re-signs an app. SIGKILL, machine failure and scheduling stalls cannot
be handled by a Python finally block; always inspect result.json after a run.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import subprocess
import sys
import time
import uuid

BASE = Path(__file__).resolve().parents[1]
WORKSPACE = BASE.parent
ARTIFACTS = WORKSPACE / 'artifacts'
SOURCE = Path('/Library/LaunchAgents/com.oray.awesun.agent.plist')
LABEL = 'com.oray.awesun.desktopagent'
PROGRAM = '/Applications/AweSun.app/Contents/Helpers/AweSun_Desktop.app/Contents/MacOS/AweSun_Desktop'
DESKTOP_APP = Path(PROGRAM).parents[2]
TEAM = 'ZBNMDRTU32'
LIBRARY = BASE / 'build/libCaptureHook-v1.4.dylib'
LIBRARY_SHA256 = '662d7c4476fbefd70884082bb6bc4c8b9f4f4a2591412479b9eac16aa0cef44a'
APP_PREFIXES = ('/Applications/AweSun.app/', '/Library/Application Support/Oray/AweSun/AweSun.app/')
KNOWN_HOOK_NAMES = ('libCaptureHook', 'libLoadWitness')


class ExperimentError(RuntimeError):
    pass


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    os.replace(temporary, path)


def original_plist(expected=None):
    raw = SOURCE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected is not None and digest != expected:
        raise ExperimentError('Original source plist changed; no further launchd mutation is allowed.')
    data = plistlib.loads(raw)
    argv = data.get('ProgramArguments')
    if data.get('Label') != LABEL or not isinstance(argv, list) or not argv or argv[0] != PROGRAM:
        raise ExperimentError('Original plist label or executable does not match the fixed target.')
    if data.get('Program', PROGRAM) != PROGRAM:
        raise ExperimentError('Original Program conflicts with ProgramArguments.')
    env = data.get('EnvironmentVariables', {})
    if not isinstance(env, dict) or any(k.startswith(('DYLD_', 'HOOK_DEMO_')) for k in env):
        raise ExperimentError('Original plist contains unexpected experiment environment settings.')
    return raw, data, digest


def expected_job(job, path):
    return (job.get('loaded') is True and job.get('definitionPath') == str(path)
            and job.get('program') == PROGRAM)


def require_known_job(job, paths):
    if job.get('loaded'):
        if not any(expected_job(job, path) for path in paths):
            raise ExperimentError('Exact-label job has an unknown definition or executable; will not remove it.')
    elif job.get('printReturnCode') != 113:
        raise ExperimentError('Cannot establish that the job is absent; will not mutate launchd.')


class BSDInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (
        'flags', 'status', 'xstatus', 'pid', 'ppid', 'uid', 'gid', 'ruid', 'rgid', 'svuid', 'svgid', 'rfu')]
    _fields_ += [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)]
    _fields_ += [(name, ctypes.c_uint32) for name in ('nfiles', 'pgid', 'pjobc', 'tdev', 'tpgid')]
    _fields_ += [('nice', ctypes.c_int32), ('startSeconds', ctypes.c_uint64), ('startMicroseconds', ctypes.c_uint64)]


class Operations:
    def __init__(self, uid):
        self.uid = uid
        self.domain = f'gui/{uid}'
        self.native = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        self.native.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        self.native.proc_pidinfo.restype = ctypes.c_int
        self.native.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        self.native.proc_pidpath.restype = ctypes.c_int
        self.clock = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
        self.clock.mach_continuous_time.restype = ctypes.c_uint64
        class Timebase(ctypes.Structure):
            _fields_ = [('numer', ctypes.c_uint32), ('denom', ctypes.c_uint32)]
        info = Timebase()
        if self.clock.mach_timebase_info(ctypes.byref(info)) != 0 or not info.denom:
            raise ExperimentError('Cannot establish a clock that includes system sleep.')
        self.clock_seconds_per_tick = info.numer / info.denom / 1_000_000_000

    def monotonic(self):
        return self.clock.mach_continuous_time() * self.clock_seconds_per_tick

    def sleep(self, seconds):
        time.sleep(seconds)

    def launchctl(self, args):
        # Do not persist or print raw output: print may include inherited secrets.
        result = subprocess.run(['/bin/launchctl', *args], capture_output=True, text=True, timeout=15)
        return result.returncode, result.stdout

    def job(self):
        code, output = self.launchctl(['print', f'{self.domain}/{LABEL}'])
        job = {'loaded': code == 0, 'printReturnCode': code}
        if code == 0:
            for key, target in [('path', 'definitionPath'), ('program', 'program'), ('state', 'state'), ('pid', 'pid')]:
                found = re.search(r'^\s*' + key + r'\s*=\s*(.*?)\s*$', output, re.M)
                if found:
                    job[target] = int(found[1]) if key == 'pid' and found[1].isdigit() else found[1]
        return job

    def verify_original_files(self, state):
        original_plist(state['sourceSHA256'])
        if sha(PROGRAM) != state['programSHA256']:
            raise ExperimentError('Original desktop executable changed.')
        self.verify_signature()

    def verify_files(self, state):
        self.verify_original_files(state)
        if sha(LIBRARY) != LIBRARY_SHA256:
            raise ExperimentError('Fixed Hook library hash does not match.')

    def verify_signature(self):
        check = subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(DESKTOP_APP)],
                               capture_output=True, text=True, timeout=20)
        detail = subprocess.run(['/usr/bin/codesign', '-dv', str(DESKTOP_APP)], capture_output=True, text=True, timeout=10)
        if check.returncode or detail.returncode or f'TeamIdentifier={TEAM}' not in detail.stderr.splitlines():
            raise ExperimentError('Original Desktop sub-bundle signature or Team ID verification failed.')

    def identity(self, pid):
        info = BSDInfo()
        size = self.native.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
        path = ctypes.create_string_buffer(4096)
        length = self.native.proc_pidpath(pid, path, len(path))
        if size != ctypes.sizeof(info) or length <= 0 or info.pid != pid:
            raise ExperimentError(f'Cannot establish native process identity for PID {pid}.')
        return {'pid': pid, 'parentPID': info.ppid, 'uid': info.uid, 'executable': os.fsdecode(path.value),
                'startSeconds': info.startSeconds, 'startMicroseconds': info.startMicroseconds}

    def snapshot(self):
        result = subprocess.run(['/bin/ps', '-axo', 'pid=,uid=,comm='], capture_output=True, text=True, timeout=10, check=True)
        found, unresolved = [], []
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) != 3 or not parts[2].startswith(APP_PREFIXES):
                continue
            pid = int(parts[0])
            try:
                identity = self.identity(pid)
                if not identity['executable'].startswith(APP_PREFIXES) or identity['uid'] != int(parts[1]):
                    raise ExperimentError('Process changed while enumerating.')
                found.append(identity)
            except ExperimentError:
                unresolved.append({'pid': pid, 'observedUID': int(parts[1]), 'observedPath': parts[2],
                                   'reason': 'native_identity_unavailable_or_changed', 'observationSource': 'ps'})
        return {'processes': found, 'unresolved': unresolved, 'enumerationComplete': not unresolved,
                'currentUserEnumerationComplete': not any(p['observedUID'] == self.uid for p in unresolved)}

    def mapping_check(self):
        before = self.snapshot()
        checks = []
        for proc in before['processes']:
            if proc['uid'] != self.uid or Path(proc['executable']).name != 'AweSun_Desktop':
                continue
            item = {'process': proc, 'status': 'unknown', 'knownHookNameMatches': [],
                    'filenameOnlyNotGenericHookDetection': True}
            try:
                if self.identity(proc['pid']) != proc:
                    raise ExperimentError('Process changed before vmmap.')
                result = subprocess.run(['/usr/bin/vmmap', '-w', str(proc['pid'])], capture_output=True, text=True, timeout=15)
                item['vmmapExitCode'] = result.returncode
                item['identityStable'] = self.identity(proc['pid']) == proc
                if result.returncode == 0 and item['identityStable']:
                    item['knownHookNameMatches'] = [name for name in KNOWN_HOOK_NAMES if name in result.stdout]
                    item['status'] = 'known_hook_present' if item['knownHookNameMatches'] else 'known_hook_not_observed'
            except (ExperimentError, OSError, subprocess.SubprocessError) as error:
                item['errorType'] = type(error).__name__
            checks.append(item)
        after = self.snapshot()
        def desktop_ids(snapshot):
            return sorted((p['pid'], p['uid'], p['executable'], p['startSeconds'], p['startMicroseconds'])
                          for p in snapshot['processes'] if p['uid'] == self.uid and Path(p['executable']).name == 'AweSun_Desktop')
        stable = (before['currentUserEnumerationComplete'] and after['currentUserEnumerationComplete']
                  and desktop_ids(before) == desktop_ids(after))
        return {'checks': checks, 'inventoryStable': stable,
                'knownHookAbsentInObservedDesktopProcesses': bool(checks) and stable and all(c['status'] == 'known_hook_not_observed' for c in checks),
                'snapshotAfter': after, 'childProcessesTerminated': False}


class Experiment:
    def __init__(self, state, operations, seconds):
        self.state, self.ops, self.seconds = state, operations, seconds
        self.directory = Path(state['runDirectory'])
        self.modified = Path(state['modifiedPlist'])
        self.restore_requested = False
        self.request_reason = None
        self.deadline = None
        self.mutation_attempted = False

    def signal_handler(self, signum, _frame):
        # Never run restoration inside a handler or interrupt a launchctl call.
        self.restore_requested = True
        self.request_reason = f'signal_{signum}'

    def event(self, name, **fields):
        self.state.setdefault('events', []).append({'atUTC': utc(), 'event': name, **fields})
        atomic_json(self.directory / 'state.json', self.state)

    def restore_event(self, name, **fields):
        # A full disk must not prevent a best-effort restoration after mutation.
        try:
            self.event(name, **fields)
        except OSError as error:
            self.state.setdefault('restoreJournalErrors', []).append(type(error).__name__)

    def check_request(self):
        if self.restore_requested:
            return True
        if (self.directory / 'restore.request').exists():
            self.restore_requested, self.request_reason = True, 'restore_request_file'
        elif self.deadline is not None and self.ops.monotonic() >= self.deadline:
            self.restore_requested, self.request_reason = True, 'deadline_reached'
        return self.restore_requested

    def wait_for(self, path=None, running=False, seconds=6):
        end = self.ops.monotonic() + seconds
        last = self.ops.job()
        while self.ops.monotonic() < end:
            if path is None and not last.get('loaded') and last.get('printReturnCode') == 113:
                return last
            if path is not None and expected_job(last, path) and (not running or last.get('state') == 'running' and isinstance(last.get('pid'), int) and last['pid'] > 0):
                return last
            self.ops.sleep(0.2)
            last = self.ops.job()
        return last

    def guard(self, paths, restoring=False):
        # Called before every mutation, including every bootout.
        if restoring:
            self.ops.verify_original_files(self.state)
        else:
            self.ops.verify_files(self.state)
        job = self.ops.job()
        require_known_job(job, paths)
        return job

    def restore(self):
        self.state['restoreStartedAtUTC'] = utc()
        self.restore_event('restore_started', reason=self.request_reason or 'failure')
        current = self.guard([SOURCE, self.modified], restoring=True)
        if expected_job(current, self.modified):
            # A known path alone is insufficient if its backing plist changed.
            if sha(self.modified) != self.state['modifiedSHA256']:
                raise ExperimentError('Instrumented definition changed; refusing to remove an uncertain job.')
            self.restore_event('restore_bootout_requested')
            self.mutation_attempted = True
            code, _ = self.ops.launchctl(['bootout', f'{self.ops.domain}/{LABEL}'])
            self.restore_event('restore_bootout_returned', returnCode=code)
            current = self.wait_for()
            require_known_job(current, [SOURCE])
            if current.get('loaded') and not expected_job(current, SOURCE):
                raise ExperimentError('Instrumented job remains loaded.')
        current = self.guard([SOURCE], restoring=True)
        if not current.get('loaded'):
            self.restore_event('restore_bootstrap_requested')
            code, _ = self.ops.launchctl(['bootstrap', self.ops.domain, str(SOURCE)])
            self.restore_event('restore_bootstrap_returned', returnCode=code)
        current = self.wait_for(SOURCE, running=True)
        self.state['jobAfterRestore'] = current
        self.state['originalJobRestored'] = expected_job(current, SOURCE)
        self.state['originalJobRunning'] = self.state['originalJobRestored'] and current.get('state') == 'running' and isinstance(current.get('pid'), int) and current['pid'] > 0
        if not self.state['originalJobRunning']:
            raise ExperimentError('Original job was not verified running after restoration.')
        self.ops.verify_original_files(self.state)
        self.state['status'] = 'original_job_restored'
        self.restore_event('restore_job_verified')

    def run(self):
        error = None
        try:
            current = self.guard([SOURCE])
            if not expected_job(current, SOURCE):
                raise ExperimentError('Start requires the source job already registered.')
            self.deadline = self.ops.monotonic() + self.seconds
            self.state['restoreDeadlineUTC'] = (datetime.now(timezone.utc) + timedelta(seconds=self.seconds)).isoformat()
            if self.check_request():
                raise ExperimentError('Restoration requested before any mutation.')
            self.event('bootout_original_requested')
            self.mutation_attempted = True
            code, _ = self.ops.launchctl(['bootout', f'{self.ops.domain}/{LABEL}'])
            self.event('bootout_original_returned', returnCode=code)
            current = self.wait_for()
            require_known_job(current, [])
            if current.get('loaded'):
                raise ExperimentError('Original task did not unload.')
            if self.check_request():
                raise ExperimentError('Restoration requested during setup.')
            current = self.guard([])
            if current.get('loaded') or sha(self.modified) != self.state['modifiedSHA256']:
                raise ExperimentError('Job or instrumented plist changed before bootstrap.')
            # Signature verification in guard() can be slow. Do not bootstrap a
            # new experiment after the lease or a signal expired during it.
            if self.check_request():
                raise ExperimentError('Restoration requested during pre-bootstrap verification.')
            self.event('bootstrap_instrumented_requested')
            code, _ = self.ops.launchctl(['bootstrap', self.ops.domain, str(self.modified)])
            self.event('bootstrap_instrumented_returned', returnCode=code)
            installed = self.wait_for(self.modified, running=True)
            if not expected_job(installed, self.modified) or installed.get('state') != 'running' or not isinstance(installed.get('pid'), int) or installed['pid'] <= 0:
                raise ExperimentError('Instrumented agent did not reach running state.')
            if self.check_request():
                raise ExperimentError('Restoration requested before readiness.')
            self.state['jobAfterStart'] = installed
            self.state['processesAfterStart'] = self.ops.snapshot()
            if self.check_request():
                raise ExperimentError('Restoration requested while checking readiness.')
            self.state['status'] = 'audit_waiting'
            ready = {'readyAtUTC': utc(), 'restoreDeadlineUTC': self.state['restoreDeadlineUTC'],
                     'remainingSeconds': max(0, self.deadline - self.ops.monotonic()), 'job': installed,
                     'sessionID': self.state['sessionID'], 'logPattern': self.state['logPattern'],
                     'restoreRequestPath': str(self.directory / 'restore.request'),
                     'libraryLoaded': 'unverified', 'captureHookHit': 'unverified',
                     'deadlineIsScheduledRestoreStartNotHardRealtimeGuarantee': True}
            atomic_json(self.directory / 'ready.json', ready)
            self.event('ready')
            while not self.check_request():
                self.ops.sleep(min(0.2, max(0, self.deadline - self.ops.monotonic())))
        except Exception as caught:
            error = caught
            self.state['experimentError'] = f'{type(caught).__name__}: {caught}'
        finally:
            self.state['mutationAttempted'] = self.mutation_attempted
            # Nothing needs restoration if preflight rejected before mutation.
            if self.mutation_attempted:
                try:
                    self.restore()
                except Exception as caught:
                    self.state['status'] = 'restore_incomplete'
                    self.state['restoreError'] = f'{type(caught).__name__}: {caught}'
            else:
                self.state['status'] = 'not_started'
            try:
                self.state['postRestoreMappingCheck'] = self.ops.mapping_check()
            except Exception as caught:
                self.state['postRestoreMappingCheck'] = {'status': 'unknown', 'errorType': type(caught).__name__}
            self.state['finishedAtUTC'] = utc()
            self.state['remoteRecoveryVerified'] = False
            self.state['rootJobsChanged'] = False
            self.state['childProcessesTerminated'] = False
            atomic_json(self.directory / 'result.json', self.state)
            atomic_json(self.directory / 'state.json', self.state)
        return 0 if error is None and self.state['status'] == 'original_job_restored' else 1


def prepare(args, ops):
    directory = Path(args.run_dir).expanduser().resolve()
    try:
        relative = directory.relative_to(ARTIFACTS.resolve())
    except ValueError as error:
        raise ExperimentError('Run directory must be inside workspace artifacts.') from error
    if len(relative.parts) < 2 or not relative.parts[0].startswith('sunlogin-hook-test') or directory.exists():
        raise ExperimentError('Use a fresh artifacts/sunlogin-hook-test.../audit directory.')
    config = Path(args.config).expanduser().resolve(strict=True)
    if not config.is_relative_to(WORKSPACE) or not config.is_file():
        raise ExperimentError('Config must be an existing project file.')
    value = json.loads(config.read_text())
    if not isinstance(value, dict):
        raise ExperimentError('Config must be a JSON object.')
    raw, original, source_hash = original_plist()
    if sha(LIBRARY) != LIBRARY_SHA256:
        raise ExperimentError('Hook v1.4 hash mismatch.')
    ops.verify_signature()
    before = ops.job()
    if not expected_job(before, SOURCE):
        raise ExperimentError('Original exact-label source job must already be registered.')
    state = {'schemaVersion': 1, 'createdAtUTC': utc(), 'status': 'prepared',
             'runDirectory': str(directory), 'sourcePlist': str(SOURCE), 'sourceSHA256': source_hash,
             'program': PROGRAM, 'programSHA256': sha(PROGRAM), 'teamID': TEAM,
             'signatureScope': 'original Desktop sub-bundle; not the outer AweSun application',
             'domain': ops.domain, 'label': LABEL, 'jobBefore': before,
             'processesBefore': ops.snapshot(), 'mode': 'audit', 'sessionID': str(uuid.uuid4()),
             'library': str(LIBRARY), 'librarySHA256': LIBRARY_SHA256,
             'config': str(config), 'configSHA256': sha(config),
             'logPattern': str(directory / 'hook-%p.jsonl'),
             'modifiedPlist': str(directory / 'instrumented-job.plist'), 'events': []}
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(directory, 0o700)
    backup = directory / 'original-job.plist'
    backup.write_bytes(raw)
    os.chmod(backup, 0o600)
    env = dict(original.get('EnvironmentVariables', {}))
    env.update({'DYLD_INSERT_LIBRARIES': str(LIBRARY), 'HOOK_DEMO_MODE': 'audit',
                'HOOK_DEMO_LOG': state['logPattern'], 'HOOK_DEMO_CONFIG': str(config),
                'HOOK_DEMO_SESSION_ID': state['sessionID']})
    original['EnvironmentVariables'] = env
    modified = Path(state['modifiedPlist'])
    modified.write_bytes(plistlib.dumps(original, sort_keys=False))
    os.chmod(modified, 0o600)
    state['modifiedSHA256'] = sha(modified)
    atomic_json(directory / 'state.json', state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run', help='Run audit and restore synchronously; never start a second restore controller.')
    run.add_argument('--run-dir', required=True)
    run.add_argument('--config', required=True)
    run.add_argument('--seconds', type=int, default=300, choices=range(1, 301), metavar='1..300')
    args = parser.parse_args()
    if os.getuid() == 0 or os.getuid() != os.geteuid():
        parser.error('Run as the ordinary logged-in user without sudo.')
    if not ARTIFACTS.is_dir():
        parser.error('Workspace artifacts directory does not exist.')
    # One global lock serializes all instances. Keep its inode after unlocking.
    with (ARTIFACTS / '.sunlogin-user-agent-experiment.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('Another Sunlogin experiment controller holds the lock.')
        ops = Operations(os.getuid())
        state = prepare(args, ops)
        experiment = Experiment(state, ops, args.seconds)
        old_handlers = {sig: signal.signal(sig, experiment.signal_handler) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        try:
            code = experiment.run()
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
        print(json.dumps({'status': state['status'], 'result': str(Path(state['runDirectory']) / 'result.json'),
                          'remoteRecoveryVerified': False}, ensure_ascii=False))
        return code


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ExperimentError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({'error': str(error), 'type': type(error).__name__}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
