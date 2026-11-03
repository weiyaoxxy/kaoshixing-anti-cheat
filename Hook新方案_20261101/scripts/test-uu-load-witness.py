#!/usr/bin/env python3
"""Restart the installed UU GUI with a log-only dylib; never change its signature."""
from pathlib import Path
from datetime import datetime, timezone
import subprocess, os, time, json, hashlib, plistlib, signal

BASE = Path(__file__).resolve().parents[1]
EXE = '/Applications/UURemote.app/Contents/MacOS/UURemote'
LIB = BASE / 'build/libLoadWitness.dylib'

def processes():
    r = subprocess.run(['/bin/ps', '-axo', 'pid=,uid=,comm='], capture_output=True, text=True, check=True)
    rows = []
    for line in r.stdout.splitlines():
        p = line.strip().split(None, 2)
        if len(p) == 3 and '/UURemote.app/' in p[2]:
            rows.append({'pid': int(p[0]), 'uid': int(p[1]), 'executable': p[2]})
    return rows

out = BASE / 'artifacts' / ('uu-load-witness-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
out.mkdir(exist_ok=False)
before = processes()
quit_actions = []
if any(p['executable'] == EXE for p in before):
    try:
        q = subprocess.run(['/usr/bin/osascript', '-e', 'tell application id "com.netease.uuremote" to quit'],
                           capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        q = None
    deadline = time.monotonic() + 8
    while any(p['executable'] == EXE for p in processes()) and time.monotonic() < deadline:
        time.sleep(.25)
    if any(p['executable'] == EXE for p in processes()):
        for p in processes():
            if p['executable'] == EXE and p['uid'] == os.getuid():
                os.kill(p['pid'], signal.SIGTERM)
                quit_actions.append({'action': 'SIGTERM exact current-user GUI after graceful quit remained pending', 'pid': p['pid']})
        deadline = time.monotonic() + 3
        while any(p['executable'] == EXE for p in processes()) and time.monotonic() < deadline:
            time.sleep(.25)
        if any(p['executable'] == EXE for p in processes()):
            (out / 'result.json').write_text(json.dumps({'status': 'not-started', 'reason': 'UU GUI remained running', 'quitActions': quit_actions}, indent=2) + '\n')
            raise SystemExit('UU GUI remained running; no second instance was launched.')

env = os.environ.copy()
for key in ['DYLD_INSERT_LIBRARIES', 'HOOK_DEMO_LOG', 'HOOK_DEMO_MODE', 'HOOK_DEMO_CONFIG']:
    env.pop(key, None)
env.update(DYLD_INSERT_LIBRARIES=str(LIB), HOOK_DEMO_LOG=str(out / 'witness.jsonl'))
before_hash = hashlib.sha256(Path(EXE).read_bytes()).hexdigest()
proc = subprocess.Popen([EXE], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True)
time.sleep(3)
after = processes()
vm = subprocess.run(['/usr/bin/vmmap', str(proc.pid)], capture_output=True, text=True, timeout=15)
matches = [line.strip() for line in vm.stdout.splitlines() if 'libLoadWitness' in line]
vm_note = {'returnCode': vm.returncode, 'witnessMappingLines': matches,
           'interpretation': 'An empty result is corroborative only when vmmap succeeded.'}
(out / 'mapping-check.json').write_text(json.dumps(vm_note, ensure_ascii=False, indent=2) + '\n')
with Path('/Applications/UURemote.app/Contents/Info.plist').open('rb') as f:
    info = plistlib.load(f)
log = out / 'witness.jsonl'
events = [json.loads(s) for s in log.read_text().splitlines()] if log.exists() else []
result = {'startedAtUTC': datetime.now(timezone.utc).isoformat(), 'application': EXE,
          'version': info.get('CFBundleShortVersionString'), 'build': info.get('CFBundleVersion'),
          'spawnedPID': proc.pid, 'spawnedProcessExitCode': proc.poll(),
          'processesBefore': before, 'processesAfter': after, 'quitActions': quit_actions,
          'library': str(LIB), 'librarySHA256': hashlib.sha256(LIB.read_bytes()).hexdigest(),
          'targetSHA256Before': before_hash, 'targetSHA256After': hashlib.sha256(Path(EXE).read_bytes()).hexdigest(),
          'witnessEvents': events, 'mappingCheck': vm_note,
          'scope': 'Installed original UU GUI startup loading test, not live-process injection or capture blocking.'}
(out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
(BASE / 'artifacts/latest-uu-load-witness.txt').write_text(str(out) + '\n')
print(json.dumps({'output': str(out), 'spawnedPID': proc.pid, 'exitCode': proc.poll(),
                  'witnessEventCount': len(events), 'mappingReturnCode': vm.returncode,
                  'witnessMappingCount': len(matches), 'targetHashUnchanged': result['targetSHA256Before'] == result['targetSHA256After']},
                 ensure_ascii=False), flush=True)
