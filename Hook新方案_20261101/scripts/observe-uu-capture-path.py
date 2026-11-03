#!/usr/bin/env python3
"""Bounded external sampling of verified original, current-user UU processes.

Does not inject, resign, alter launchd, read process arguments or capture pixels.
sample briefly suspends/resumes threads and can affect timing. Its results are
external stack evidence, never CaptureHook events or proof of a valid frame.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
APP = Path('/Applications/UURemote.app')
PATHS = {
    'gui': APP / 'Contents/MacOS/UURemote',
    'service': APP / 'Contents/MacOS/UURemoteService',
    'server': APP / 'Contents/Helpers/UURemoteServer',
    'daemon': APP / 'Contents/MacOS/UURemoteDaemon',
}
PLISTS = [Path('/Library/LaunchAgents/com.netease.uuremote.agent.plist'),
          Path('/Library/LaunchDaemons/com.netease.uuremote.daemon.plist')]
TEAM = 'PU9BNSBJW7'
STOP_REQUESTED = False


def request_stop(*unused):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    os.replace(temporary, path)


def command(arguments, timeout=15):
    return subprocess.run(arguments, capture_output=True, text=True, timeout=timeout,
                          env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
                               'LANG': 'C', 'LC_ALL': 'C'})


def inventory(binary):
    result = command([str(binary)])
    if result.returncode:
        raise RuntimeError('processInventoryFailed')
    value = json.loads(result.stdout)
    if value.get('schemaVersion') != 1 or not isinstance(value.get('processes'), list):
        raise RuntimeError('invalidProcessInventory')
    return value


def identity(row):
    keys = ('pid', 'uid', 'executable', 'startTimeSeconds', 'startTimeMicroseconds')
    if not row or any(key not in row for key in keys):
        return None
    if type(row['pid']) is not int or row['pid'] <= 0 or row['startTimeSeconds'] <= 0:
        return None
    return tuple(row[key] for key in keys)


def matching_snapshot(value, row):
    return next((item for item in value['processes'] if identity(item) == identity(row)), None)


def original_targets(value, roles):
    return [row for row in value['processes']
            if row.get('role') in roles and row.get('uid') == os.getuid()
            and row.get('executable') == str(PATHS[row['role']]) and identity(row)]


def signing(path):
    metadata = command(['/usr/bin/codesign', '-d', '--verbose=4', str(path)])
    team = re.search(r'^TeamIdentifier=(\S+)$', metadata.stderr, re.M)
    identifier = re.search(r'^Identifier=([A-Za-z0-9_.-]+)$', metadata.stderr, re.M)
    verify = command(['/usr/bin/codesign', '--verify', '--strict', str(path)])
    return {'teamIdentifier': team.group(1) if team else None,
            'identifier': identifier.group(1) if identifier else None,
            'verificationExitCode': verify.returncode,
            'originalVendorSignatureVerified': metadata.returncode == 0 and
                verify.returncode == 0 and team is not None and team.group(1) == TEAM,
            'basis': 'on_disk_code_at_inspection_time_not_runtime_attestation'}


def baseline():
    files = [*PATHS.values(), APP / 'Contents/Frameworks/libstreamer.dylib', *PLISTS]
    return {'atUTC': utc(), 'files': [
        {'path': str(path), 'sha256': digest(path), 'size': path.stat().st_size}
        for path in files]}


def launch_job():
    target = f'gui/{os.getuid()}/com.netease.uuremote.agent'
    result = command(['/bin/launchctl', 'print', target])
    value = {'target': target, 'exitCode': result.returncode}
    for key in ('path', 'program', 'state', 'pid'):
        match = re.search(r'^\s*' + key + r'\s*=\s*(.*?)\s*$', result.stdout, re.M)
        value[key] = match.group(1) if match else None
    value['experimentalEnvironmentKeys'] = re.findall(
        r'^\s*((?:DYLD_|HOOK_DEMO_)[A-Za-z0-9_]+)\s*=>', result.stdout, re.M)
    return value


def load_analyzer():
    path = ROOT / 'scripts/analyze-uu-capture-sample.py'
    spec = importlib.util.spec_from_file_location('uu_capture_sample_analyzer', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('analyzerUnavailable')
    module = importlib.util.module_from_spec(spec)
    # dataclasses and similar helpers may resolve their defining module.
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.analyze


def run_sample(arguments, duration):
    # Never use subprocess.run(timeout=...) here: it SIGKILLs its child on timeout.
    # Normal requests finish naturally, including when this collector is asked to stop.
    task = subprocess.Popen(arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'})
    try:
        rc = task.wait(timeout=duration + 60)
        return {'exitCode': rc, 'timedOut': False, 'cleanupConfirmed': True}
    except subprocess.TimeoutExpired:
        task.send_signal(signal.SIGINT)
        try:
            rc = task.wait(timeout=10)
            return {'exitCode': rc, 'timedOut': True, 'cleanupConfirmed': True,
                    'sampleInterruptRequested': True, 'targetContinuityRequiresVerification': True}
        except subprocess.TimeoutExpired:
            # Do not SIGKILL sample or blindly SIGCONT the inspected process.
            return {'exitCode': None, 'timedOut': True, 'cleanupConfirmed': False,
                    'sampleInterruptRequested': True, 'sampleToolPID': task.pid,
                    'targetContinuityRequiresVerification': True}


def sample_one(row, binary, duration, interval, analyze, directory, number):
    stem = f'{number:02d}-{row["role"]}-{row["pid"]}'
    record = {'role': row['role'], 'processBefore': row, 'atUTC': utc(),
              'requestedDurationSeconds': duration, 'requestedIntervalMilliseconds': interval,
              'evidenceSource': 'external_stack_sample', 'captureHookHitVerified': False,
              'validFrameVerified': False, 'remoteSessionVerified': False,
              'status': 'sampleAttemptPrepared', 'rawSampleRetained': None}
    save(directory / (stem + '-result.json'), record)
    temporary_path = None
    try:
        current = matching_snapshot(inventory(binary), row)
        if current is None:
            record['status'] = 'processChangedBeforeSampling'
            return record
        path = Path(row['executable'])
        file_hash = digest(path)
        signed = signing(path)
        record['signing'] = signed
        if not signed['originalVendorSignatureVerified']:
            record['status'] = 'originalSignatureUnverified'
            return record
        if matching_snapshot(inventory(binary), row) is None or STOP_REQUESTED:
            record['status'] = 'processChangedOrStopRequestedBeforeSampling'
            return record
        start = time.monotonic()
        started_utc = utc()
        with tempfile.TemporaryDirectory(prefix='uu-capture-stack-') as temporary:
            temporary_path = Path(temporary)
            raw = temporary_path / 'sample.txt'
            raw.touch(mode=0o600)
            record.update(status='sampling', startedAtUTC=started_utc)
            save(directory / (stem + '-result.json'), record)
            outcome = run_sample(['/usr/bin/sample', str(row['pid']), str(duration),
                                  str(interval), '-file', str(raw)], duration)
            end = time.monotonic()
            record['sampleTool'] = outcome
            same, unchanged = False, False
            try:
                after = inventory(binary)
                record['processAfter'] = matching_snapshot(after, row)
                same = record['processAfter'] is not None
            except Exception as exc:
                record['postIdentityError'] = type(exc).__name__
            try:
                unchanged = path.is_file() and digest(path) == file_hash
            except Exception as exc:
                record['postFileError'] = type(exc).__name__
            expect = {'pid': row['pid'], 'executable': row['executable'],
                      'uid': row['uid'], 'startTimeSeconds': row['startTimeSeconds'],
                      'startTimeMicroseconds': row['startTimeMicroseconds'],
                      'identityMatchedBeforeAfter': same and unchanged,
                      'sampleStartedAtUTC': started_utc, 'sampleEndedAtUTC': utc(),
                      'sampleStartMonotonic': start, 'sampleEndMonotonic': end,
                      'executableSHA256': file_hash,
                      'sampleExitCode': outcome['exitCode'], 'sampleTimedOut': outcome['timedOut'],
                      'sampleOutputTruncated': False,
                      'sampleOutputComplete': outcome['exitCode'] == 0 and not outcome['timedOut']}
            record.update(elapsedSeconds=end-start, identityMatchedBeforeAfter=same,
                          executableUnchanged=unchanged)
            if not outcome['cleanupConfirmed']:
                record['status'] = 'sampleToolCleanupUnconfirmed'
            elif outcome['timedOut']:
                record['status'] = 'sampleToolTimeout'
            elif outcome['exitCode'] != 0 or not raw.is_file() or raw.stat().st_size == 0:
                record['status'] = 'sampleUnavailable'
            elif raw.stat().st_size > 32 * 1024 * 1024:
                record['status'] = 'sampleTooLarge'
                expect['sampleOutputTruncated'] = True
                expect['sampleOutputComplete'] = False
            else:
                raw_bytes = raw.read_bytes()
                sample_hash = hashlib.sha256(raw_bytes).hexdigest()
                expect['expectedSampleSHA256'] = sample_hash
                record['rawSampleSHA256'] = sample_hash
                record['rawSampleBytes'] = len(raw_bytes)
                analysis = analyze(raw_bytes, expect)
                save(directory / (stem + '-analysis.json'), analysis)
                record.update(status=analysis['status'], analysisFile=stem+'-analysis.json',
                              pathObserved=analysis.get('pathObserved', False),
                              encodingObserved=analysis.get('encodingObserved', False),
                              iosurfaceObserved=analysis.get('iosurfaceObserved', False))
            save(directory / (stem + '-expect.json'), expect)
    except Exception as exc:
        record.update(status='sampleAttemptIncomplete', errorClass=type(exc).__name__)
    finally:
        record['endedAtUTC'] = utc()
        record['rawSampleRetained'] = temporary_path.exists() if temporary_path is not None else False
        save(directory / (stem + '-result.json'), record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=['preflight', 'idle', 'connected', 'disconnected'], required=True)
    parser.add_argument('--inventory', type=Path, default=ROOT/'build/UUProcessInventory')
    parser.add_argument('--roles', nargs='+', choices=['gui', 'service', 'server'], default=['server'])
    parser.add_argument('--rounds', type=int, default=2, choices=range(1, 5))
    parser.add_argument('--duration', type=int, default=3, choices=range(1, 6))
    parser.add_argument('--interval-ms', type=int, default=5, choices=range(1, 21))
    args = parser.parse_args()
    if os.geteuid() == 0 or os.getuid() != os.geteuid():
        parser.error('Run as the ordinary logged-in user; no sudo.')
    if not args.inventory.is_file():
        parser.error('Build the process inventory helper first.')
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    before = baseline()
    initial = inventory(args.inventory)
    initial_job = launch_job()
    save(output/'baseline-before.json', before)
    save(output/'processes-before.json', initial)
    save(output/'job-before.json', initial_job)
    rows = []
    error = None
    try:
        if (initial_job.get('exitCode') != 0 or
            initial_job.get('path') != str(PLISTS[0]) or
            initial_job.get('program') != str(PATHS['service']) or
            initial_job.get('experimentalEnvironmentKeys')):
            raise RuntimeError('originalLaunchConfigurationNotConfirmed')
        if args.phase != 'preflight':
            analyzer = load_analyzer()
            for _ in range(args.rounds):
                if STOP_REQUESTED:
                    break
                targets = original_targets(inventory(args.inventory), args.roles)
                for row in targets:
                    if STOP_REQUESTED:
                        break
                    value = sample_one(row, args.inventory, args.duration, args.interval_ms,
                                       analyzer, output, len(rows)+1)
                    rows.append(value)
                    print(json.dumps({'sample': len(rows), 'role': row['role'],
                                      'status': value['status'],
                                      'pathObserved': value.get('pathObserved', False)}), flush=True)
                    if value['status'] in ('sampleToolCleanupUnconfirmed', 'sampleToolTimeout'):
                        raise RuntimeError('sampleInterruptedFurtherSamplingStopped')
                if not targets:
                    rows.append({'status': 'noVerifiedOriginalUserTarget', 'atUTC': utc()})
    except Exception as exc:
        error = type(exc).__name__ + ':' + str(exc)[:160]
    finally:
        checks = {}
        final_errors = {}
        for name, reader in [('baseline-after', baseline),
                             ('processes-after', lambda: inventory(args.inventory)),
                             ('job-after', launch_job)]:
            try:
                checks[name] = reader()
                save(output/(name+'.json'), checks[name])
            except Exception as exc:
                final_errors[name] = type(exc).__name__
        after, final_job = checks.get('baseline-after'), checks.get('job-after')
        report = {'schemaVersion': 1, 'phaseLabel': args.phase,
                  'phaseLabelIsHumanSuppliedNotSessionDetection': True,
                  'startedAtUTC': before['atUTC'], 'endedAtUTC': utc(),
                  'samples': rows, 'error': error, 'finalCheckErrors': final_errors,
                  'collectionComplete': not error and not final_errors and not STOP_REQUESTED and
                      (args.phase == 'preflight' or bool(rows)) and
                      all(row.get('status') in ('path_observed', 'path_not_observed') for row in rows),
                  'stopRequested': STOP_REQUESTED,
                  'originalFilesUnchanged': before['files'] == after['files'] if after else None,
                  'originalLaunchJobUnchanged': initial_job == final_job if final_job else None,
                  'evidenceSource': 'external_stack_sample',
                  'captureHookHitVerified': False, 'validFrameVerified': False,
                  'remoteSessionVerified': False, 'screenPixelsCollected': False,
                  'rawSampleRetained': any(row.get('rawSampleRetained') is not False for row in rows),
                  'rootDaemonSampled': False,
                  'limitations': [
                      'sample briefly suspends/resumes threads and may affect timing.',
                      'Short calls and other processes/backends may be missed.',
                      'Stack evidence does not establish frame validity, hook execution, or remote display.',
                      'Before/after process identity is not atomic or remote attestation.',
                      'Only exact original current-user executables are sampled.']}
        save(output/'summary.json', report)

    if error:
        raise SystemExit(error)
    if final_errors or report['originalFilesUnchanged'] is not True or report['originalLaunchJobUnchanged'] is not True:
        raise SystemExit('finalVerificationIncompleteOrChanged')


if __name__ == '__main__':
    main()
