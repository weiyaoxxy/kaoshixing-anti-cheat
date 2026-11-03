#!/usr/bin/env python3
"""Explicit UI-only fixture. Never enumerates or signals another process."""
import argparse, json, os, select, sys, time
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--ui-protocol', action='store_true')
p.add_argument('--ui-test-mode', action='store_true')
p.add_argument('--session-dir', required=True)
p.add_argument('--ui-session-id', required=True)
p.add_argument('--inventory', required=True)
p.add_argument('--policy', required=True)
p.add_argument('--worker')
p.add_argument('--vendors')
p.add_argument('--worker-lease')
a = p.parse_args()
if not a.ui_test_mode:
    p.error('fixture requires --ui-test-mode; never use as an actual guard')
Path(a.session_dir).mkdir(mode=0o700)
scenario = json.loads(Path(a.policy).read_text())['scenario']
state, sequence, started, exam_at = 'ready', 0, time.monotonic(), None
fault_sent = False
commands = []
end_at = None
while time.monotonic() - started < 26:
    if select.select([sys.stdin], [], [], 0.05)[0]:
        line = sys.stdin.readline()
        if not line:
            break
        command = json.loads(line)['command']
        commands.append(command)
        Path(a.session_dir,'fixture-commands.json').write_text(json.dumps(commands))
        if command in ('start', 'resume'):
            state, exam_at = 'exam', time.monotonic()
        elif command == 'pause':
            state = 'paused'
        elif command == 'end':
            if scenario == 'no_end_ack':
                state = 'restoring'
                end_at = end_at or time.monotonic()
            else:
                state = 'finished'
        elif command == 'inspect':
            state = 'ready'
    sequence += 1
    elapsed = time.monotonic() - exam_at if exam_at else 0
    status = dict(protocolVersion=1, type='status', sessionID=a.ui_session_id, sequence=sequence,
                  state=state, canStart=state=='ready', examAllowed=state=='exam', health='healthy',
                  message='合成 UI 测试；没有检测或终止真实远控', backend='mock',
                  mode='reactiveTerminate', serverMode='not_used', productionReady=False, reasons=[])
    if state == 'exam' and elapsed > 1.2:
        if scenario == 'pause':
            state = status['state'] = 'paused'
            status['examAllowed'] = False
        elif scenario == 'stale' and elapsed < 5.4:
            time.sleep(0.1)
            continue
        elif not fault_sent:
            fault_sent = True
            if scenario == 'invalid':
                print('{invalid json', flush=True)
            elif scenario == 'wrong_session':
                bad = dict(status, sessionID='other-session')
                print(json.dumps(bad), flush=True)
            elif scenario == 'replay':
                bad = dict(status, sequence=sequence-1)
                print(json.dumps(bad), flush=True)
            elif scenario == 'oversized':
                print('x'*70_000, flush=True)
            elif scenario == 'exit':
                sys.exit(7)
    print(json.dumps(status, ensure_ascii=False), flush=True)
    if state == 'finished':
        break
    time.sleep(0.15)
