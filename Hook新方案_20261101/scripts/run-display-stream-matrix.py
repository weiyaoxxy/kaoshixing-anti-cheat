#!/usr/bin/env python3
"""Run legacy display-stream tests only in this project's independent probe."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, subprocess, time

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--library', type=Path, default=ROOT / 'build/libCaptureHook-v1.2.dylib')
p.add_argument('--duration', type=float, default=2)
a = p.parse_args()
library = a.library.resolve()
native = Path((ROOT / 'artifacts/latest-native-session.txt').read_text().strip())
probe = ROOT / 'build/DisplayStreamProbe'
matrix = ROOT / 'artifacts' / ('display-stream-matrix-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
matrix.mkdir(exist_ok=False)
def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
manifest = {'createdAtUTC': datetime.now(timezone.utc).isoformat(), 'nativeSession': str(native),
            'library': str(library), 'librarySHA256': hashlib.sha256(library.read_bytes()).hexdigest(),
            'probe': str(probe), 'probeSHA256': hashlib.sha256(probe.read_bytes()).hexdigest(),
            'scope': 'independent self-owned probe only; not actual UU or ToDesk process', 'cases': []}
write(matrix / 'manifest.json', manifest)
(ROOT / 'artifacts/latest-display-stream-matrix.txt').write_text(str(matrix) + '\n')
for api in ['queue', 'runloop']:
    for mode_name, mode in [('baseline', None), ('audit', 'audit'), ('block', 'block'), ('recovery', None)]:
        name = api + '-' + mode_name
        case = matrix / name
        case.mkdir()
        activation = subprocess.run(['/usr/bin/osascript', '-e', 'tell application id "local.examcapture.hook.native" to activate'], capture_output=True, text=True, timeout=10)
        time.sleep(.4)
        state = json.loads((native / 'state.json').read_text())
        assert state['nativeUI'] and not state['captureProtectionEnabled'], 'wrong target type'
        assert state['exam']['visible'] and state['control']['visible'], 'native windows not visible'
        assert state['exam']['sharingType'] == 1, 'native exam sharing policy was modified'
        os.kill(state['ownerPID'], 0)
        write(case / 'target-before.json', state)
        env = os.environ.copy()
        for key in ['DYLD_INSERT_LIBRARIES', 'HOOK_DEMO_MODE', 'HOOK_DEMO_LOG', 'HOOK_DEMO_CONFIG']:
            env.pop(key, None)
        if mode:
            env.update(DYLD_INSERT_LIBRARIES=str(library), HOOK_DEMO_MODE=mode,
                       HOOK_DEMO_LOG=str(case / 'hook.jsonl'), HOOK_DEMO_CONFIG=str(native / 'hook-config.json'))
        cmd = [str(probe), '--api', api, '--duration', str(a.duration), '--output', str(case / 'capture')]
        row = {'case': name, 'api': api, 'mode': mode, 'command': cmd,
               'startedAtUTC': datetime.now(timezone.utc).isoformat(), 'targetActivationReturnCode': activation.returncode}
        with (case / 'console.log').open('w') as log:
            try:
                result = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=a.duration+15)
                row['returnCode'] = result.returncode
            except subprocess.TimeoutExpired:
                row['timedOut'] = True
        row['finishedAtUTC'] = datetime.now(timezone.utc).isoformat()
        write(case / 'run.json', row)
        write(case / 'target-after.json', json.loads((native / 'state.json').read_text()))
        manifest['cases'].append(row)
        write(matrix / 'manifest.json', manifest)
        print(json.dumps(row, ensure_ascii=False), flush=True)
print(str(matrix), flush=True)
