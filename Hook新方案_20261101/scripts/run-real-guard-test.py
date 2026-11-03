#!/usr/bin/env python3
"""Interactive real GUI/worker test. Explicit vendor only; bounded automatic end.

This test DOES request administrator authorization and temporarily stop the
selected remote application's verified components. Use only in an agreed test.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--app', type=Path, required=True)
p.add_argument('--inventory', type=Path, required=True)
p.add_argument('--policy', type=Path, required=True)
p.add_argument('--worker', type=Path, required=True)
p.add_argument('--vendor', choices=['uu', 'todesk', 'sunlogin'], required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--lease', type=int, default=180)
a = p.parse_args()
if not 30 <= a.lease <= 300:
    p.error('real test lease must be 30..300 seconds')
a.output.mkdir(parents=True, mode=0o700, exist_ok=False)
project = Path(__file__).resolve().parents[1]
binary = a.app / 'Contents/MacOS/NativeExamHookDemo'
ui = a.output / 'ui'
session = ui / 'guard-session'
files = [binary, a.inventory, a.policy, a.worker, project / 'scripts/exam-guard.py', project / 'runtime/enforcement.py']
hashes = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
actions = []

def load(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def click(title, close=False):
    if title not in ('开始检查 / 重新检查', '申请管理员服务', '结束并恢复', None):
        raise ValueError('unsupported test action')
    operation = ('click (first button of window "考试准备 — 本机开发验证" whose subrole is "AXCloseButton")' if close
                 else 'click button ' + json.dumps(title, ensure_ascii=False) + ' of window "考试准备 — 本机开发验证"')
    script = ('tell application "System Events"\nset targetProcess to first application process whose unix id is '
              + str(proc.pid) + '\ntell targetProcess\n' + operation + '\nend tell\nend tell')
    result = subprocess.run(['/usr/bin/osascript', '-e', script], capture_output=True, text=True, timeout=8)
    actions.append({'action': 'close' if close else title, 'atUTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'exitCode': result.returncode, 'stderr': result.stderr[:500]})
    (a.output / 'ui-actions.json').write_text(json.dumps(actions, ensure_ascii=False, indent=2))
    if result.returncode:
        raise RuntimeError(result.stderr)

def wait(predicate, duration, description):
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        state = load(ui / 'state.json')
        if predicate(state):
            return state
        if proc.poll() is not None:
            raise RuntimeError('UI exited before ' + description)
        time.sleep(.2)
    raise TimeoutError(description)

argv = [str(binary), '--output', str(ui), '--guard-runner', str(project / 'scripts/exam-guard.py'),
        '--guard-inventory', str(a.inventory), '--guard-policy', str(a.policy), '--guard-worker', str(a.worker),
        '--guard-vendors', a.vendor, '--guard-worker-lease', str(a.lease)]
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
with (a.output / 'app-output.log').open('wb') as log:
    proc = subprocess.Popen(argv, stdout=log, stderr=log)
    (a.output / 'test-session.json').write_text(json.dumps({'guiPID': proc.pid, 'vendor': a.vendor,
        'startedAtUTC': started, 'rootLeaseSeconds': a.lease, 'endTrigger': str(a.output / 'end-now'),
        'mode': 'reactiveTerminate', 'productionReady': False}, indent=2))
    try:
        wait(lambda s: s and s.get('guardSequence', 0) > 0, 15, 'initial status')
        click('开始检查 / 重新检查')
        wait(lambda s: (session / 'latest-inventory.json').exists(), 35, 'read-only baseline')
        (a.output / 'inventory-before.json').write_bytes((session / 'latest-inventory.json').read_bytes())
        click('申请管理员服务')
        authorize_started = time.monotonic()
        # The worker's own finite lease is independent from this harness.
        deadline = authorize_started + 120 + a.lease
        first_monitoring = None
        while time.monotonic() < deadline:
            state = load(ui / 'state.json') or {}
            guard = load(session / 'guard-status.json') or {}
            if guard:
                (a.output / 'latest-test-status.json').write_text(json.dumps(guard, ensure_ascii=False, indent=2))
            if state.get('guardState') in ('finished', 'recoveryPending'):
                break
            if (a.output / 'end-now').exists():
                break
            if guard.get('backend') == 'development-root-worker' and not first_monitoring:
                first_monitoring = time.monotonic()
            if proc.poll() is not None:
                raise RuntimeError('UI exited during administrator session')
            time.sleep(.5)
        click('结束并恢复')
        final = wait(lambda s: s and s.get('guardState') in ('finished', 'recoveryPending'), 45, 'restore result')
        if (session / 'latest-inventory.json').exists():
            (a.output / 'inventory-last.json').write_bytes((session / 'latest-inventory.json').read_bytes())
        summary = {'vendor': a.vendor, 'startedAtUTC': started,
                   'finishedAtUTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'guardState': final.get('guardState'), 'questionsVisible': final.get('questionsVisible'),
                   'questionControlsCreated': final.get('questionControlsCreated'),
                   'formalServerReported': False, 'remoteRecoveryHumanVerified': False,
                   'inputHashes': hashes, 'inputFilesUnchanged': all(hashlib.sha256(Path(f).read_bytes()).hexdigest() == h for f,h in hashes.items())}
        (a.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        if final.get('guardState') == 'finished':
            click(None, close=True)
            proc.wait(timeout=8)
    except Exception as error:
        (a.output / 'test-error.json').write_text(json.dumps({'error': type(error).__name__ + ':' + str(error)}, ensure_ascii=False, indent=2))
        if proc.poll() is None:
            try:
                click('结束并恢复')
            except Exception:
                pass
        # Preserve UI/recovery state on uncertainty. Never kill a privileged worker.
        raise
