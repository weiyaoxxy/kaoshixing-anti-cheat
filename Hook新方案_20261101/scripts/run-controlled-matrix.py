#!/usr/bin/env python3
"""Compare unmodified, audit, block, and restored independent capture processes."""
from pathlib import Path
from datetime import datetime, timezone
import os, json, subprocess, hashlib, argparse

BASE = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--only', choices=['all', 'cg', 'screenshot', 'stream'], default='all')
parser.add_argument('--library', type=Path, default=BASE / 'build/libCaptureHook.dylib')
options = parser.parse_args()
native = Path((BASE / 'artifacts/latest-native-session.txt').read_text().strip())
state = json.loads((native / 'state.json').read_text())
assert state['nativeUI'] and not state['captureProtectionEnabled']
assert state['exam']['visible'] and state['control']['visible']
matrix = BASE / 'artifacts' / ('controlled-matrix-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
matrix.mkdir(exist_ok=False)
library = options.library.resolve()
manifest = {'createdAtUTC': datetime.now(timezone.utc).isoformat(), 'nativeSession': str(native),
            'targetInitialState': state, 'library': str(library),
            'librarySHA256': hashlib.sha256(library.read_bytes()).hexdigest(), 'only': options.only, 'cases': []}
(BASE / 'artifacts/latest-controlled-matrix.txt').write_text(str(matrix) + '\n')
for name, mode in [('baseline', None), ('audit', 'audit'), ('block', 'block'), ('recovery', None)]:
    case = matrix / name
    case.mkdir()
    activation = subprocess.run(['/usr/bin/osascript', '-e',
                                 'tell application id "local.examcapture.hook.native" to activate'],
                                capture_output=True, text=True, timeout=10)
    current = json.loads((native / 'state.json').read_text())
    (case / 'target-before.json').write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n')
    env = os.environ.copy()
    for key in ['DYLD_INSERT_LIBRARIES', 'HOOK_DEMO_MODE', 'HOOK_DEMO_LOG', 'HOOK_DEMO_CONFIG']:
        env.pop(key, None)
    if mode:
        env.update(DYLD_INSERT_LIBRARIES=str(library), HOOK_DEMO_MODE=mode,
                   HOOK_DEMO_LOG=str(case / 'hook.jsonl'), HOOK_DEMO_CONFIG=str(native / 'hook-config.json'))
    cmd = [str(BASE / 'build/CaptureProbe'), '--window-id', str(current['windowID']),
           '--extended', '--omit-cursor', '--only', options.only, '--duration', '2',
           '--output', str(case / 'capture')]
    if options.only in ['all', 'stream']:
        cmd.append('--capture-application')
    start = datetime.now(timezone.utc).isoformat()
    with (case / 'console.log').open('w') as log:
        try:
            result = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=45)
            status = {'returnCode': result.returncode}
        except subprocess.TimeoutExpired:
            status = {'timedOut': True}
    row = {'case': name, 'mode': mode, 'startedAtUTC': start,
           'finishedAtUTC': datetime.now(timezone.utc).isoformat(),
           'targetActivationReturnCode': activation.returncode, **status}
    (case / 'run.json').write_text(json.dumps(row, indent=2) + '\n')
    manifest['cases'].append(row)
    (matrix / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(row), flush=True)
print(str(matrix), flush=True)
