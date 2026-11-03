#!/usr/bin/env python3
"""Sequential real external capture tests. Each mode gets a fresh Demo process.
Screenshots stay local. This does not infer protection from absent/black output.
"""
from pathlib import Path
import subprocess, time, json, sys, datetime
root = Path(__file__).resolve().parent.parent
out = root / 'artifacts' / ('matrix-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
out.mkdir(parents=True)
(root / 'artifacts/latest-matrix.txt').write_text(str(out))
modes = sys.argv[1:] or ['baseline','window-none','protected','both','mixed']
for mode in modes:
    case = out / mode
    case.mkdir()
    with (case/'demo-console.log').open('w') as log:
        process = subprocess.Popen([str(root/'build/ExamCaptureDemo.app/Contents/MacOS/ExamCaptureDemo'), '--mode', mode, '--output', str(case), '--record','--duration','18'], stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic()+6
        state = {}
        while time.monotonic()<deadline:
            try:
                state = json.loads((case/'demo-state.json').read_text())
                if state.get('isReadyForDisplay') and state.get('submittedFrames',0)>10: break
            except (FileNotFoundError, json.JSONDecodeError): pass
            time.sleep(.2)
        if not state.get('windowID'):
            print(mode, 'FAILED: no window state', flush=True)
        else:
            result = subprocess.run(['/usr/sbin/screencapture','-x','-l',str(state['windowID']),str(case/'system-window.png')],capture_output=True,text=True,timeout=8)
            full = subprocess.run(['/usr/sbin/screencapture','-x',str(case/'system-display.png')],capture_output=True,text=True,timeout=8)
            (case/'screencapture.json').write_text(json.dumps({'window':{'returncode':result.returncode,'stderr':result.stderr},'display':{'returncode':full.returncode,'stderr':full.stderr}},indent=2))
            with (case/'probe-console.log').open('w') as probe_log:
                subprocess.run([str(root/'build/CaptureProbe'),'--window-id',str(state['windowID']),'--output',str(case/'capture')],stdout=probe_log,stderr=subprocess.STDOUT,timeout=40)
        process.wait(timeout=25)
        with (case/'media-inspection.jsonl').open('w') as report:
            files = sorted(case.glob('*.mp4')) + sorted(case.glob('system-*.png')) + sorted((case/'capture').glob('*.png'))
            files += [case/'capture/sck-stream-window/frame-001.png',case/'capture/sck-stream-display/frame-001.png']
            subprocess.run([str(root/'build/InspectMedia')]+[str(p) for p in files if p.exists()],stdout=report,check=True,timeout=90)
        print(mode, 'completed', case, flush=True)
print(out, flush=True)
