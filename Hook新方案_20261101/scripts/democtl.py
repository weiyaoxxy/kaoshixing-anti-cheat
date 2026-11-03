#!/usr/bin/env python3
"""Convenience controller for this local experiment; all launch changes are reversible."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, os, subprocess, time

BASE = Path(__file__).resolve().parents[1]
ART = BASE / 'artifacts'
NATIVE = BASE / 'build/NativeExamHookDemo.app'
APP_ID = 'local.examcapture.hook.native'
INSTRUMENT = BASE / 'scripts/todesk-proxy-instrument.py'

def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def pointer(name):
    p = ART / name
    return Path(p.read_text().strip()) if p.exists() else None

def native_running():
    folder = pointer('latest-native-session.txt')
    if not folder or not (folder / 'state.json').exists():
        return None
    s = json.loads((folder / 'state.json').read_text())
    pid = s.get('pid')
    if not isinstance(pid, int) or s.get('finishing'):
        return None
    r = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'comm='], capture_output=True, text=True)
    expected = str(NATIVE / 'Contents/MacOS/NativeExamHookDemo')
    return folder if r.returncode == 0 and r.stdout.strip() == expected else None

def start_native():
    folder = native_running()
    if not folder:
        folder = ART / ('native-session-' + stamp())
        subprocess.run(['/usr/bin/open', '-n', str(NATIVE), '--args', '--output', str(folder)], check=True)
        deadline = time.monotonic() + 10
        while not (folder / 'hook-config.json').exists() and time.monotonic() < deadline:
            time.sleep(.2)
        if not (folder / 'hook-config.json').exists():
            raise RuntimeError('Native demo did not publish its target config.')
        (ART / 'latest-native-session.txt').write_text(str(folder) + '\n')
    subprocess.run(['/usr/bin/osascript', '-e', f'tell application id "{APP_ID}" to activate'], check=True)
    return folder

def restore():
    previous = pointer('latest-todesk-run.txt')
    if previous and (previous / 'instrumentation-state.json').exists():
        subprocess.run(['python3', str(INSTRUMENT), 'restore', '--run-dir', str(previous)], check=True)
    else:
        print('No recorded ToDesk instrumentation to restore.')

def instrument(mode):
    native = start_native()
    restore()
    # The vendor may re-register its original job during replacement. One retry
    # is permitted only after the helper reports a completed automatic rollback.
    for attempt in range(2):
        folder = ART / (f'todesk-{mode}-' + stamp() + f'-attempt{attempt + 1}')
        cmd = ['python3', str(INSTRUMENT), 'start', '--run-dir', str(folder),
               '--library', str(BASE / 'build/libCaptureHook.dylib'),
               '--config', str(native / 'hook-config.json'), '--log', str(folder / 'hook.jsonl'), '--mode', mode]
        r = subprocess.run(cmd)
        statefile = folder / 'instrumentation-state.json'
        if statefile.exists():
            (ART / 'latest-todesk-run.txt').write_text(str(folder) + '\n')
        if r.returncode == 0:
            print(f'ToDesk {mode} job started: {folder}')
            print('Reconnect from the remote device; job startup alone does not prove frame interception.')
            return
        if not statefile.exists() or json.loads(statefile.read_text()).get('status') != 'restored':
            raise RuntimeError('Start did not finish with a verified rollback; inspect its saved state.')
    raise RuntimeError('Both launch attempts failed and were restored; review the saved experiments.')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('action', choices=['start-native', 'todesk-audit', 'todesk-block', 'restore', 'status', 'quit-native'])
args = parser.parse_args()
ART.mkdir(exist_ok=True)
if args.action == 'start-native':
    print(start_native())
elif args.action in ['todesk-audit', 'todesk-block']:
    instrument(args.action.split('-')[1])
elif args.action == 'restore':
    restore()
elif args.action == 'quit-native':
    if native_running():
        subprocess.run(['/usr/bin/osascript', '-e', f'tell application id "{APP_ID}" to quit'], check=False)
else:
    print(json.dumps({'nativeSession': str(native_running()) if native_running() else None,
                      'lastToDeskRun': str(pointer('latest-todesk-run.txt'))}, ensure_ascii=False))
    previous = pointer('latest-todesk-run.txt')
    if previous and (previous / 'instrumentation-state.json').exists():
        subprocess.run(['python3', str(INSTRUMENT), 'status', '--run-dir', str(previous)], check=True)
