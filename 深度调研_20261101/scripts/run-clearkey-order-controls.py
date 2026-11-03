#!/usr/bin/env python3
from pathlib import Path
import datetime,json,subprocess,time,urllib.request
root=Path(__file__).resolve().parents[1]
out=root/'artifacts'/('clearkey-order-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir()
log=(out/'http-server.log').open('w')
server=subprocess.Popen(['python3','-m','http.server','8766','--bind','127.0.0.1','--directory',str(root/'research/clearkey/media')],stdout=log,stderr=log)
try:
 for n in range(30):
  try:urllib.request.urlopen('http://127.0.0.1:8766/encrypted/stream.m3u8');break
  except Exception:time.sleep(.1)
 for order in ['after','none']:
  case=out/order;case.mkdir()
  console=(case/'demo-console.log').open('w')
  app=subprocess.Popen([str(root/'build/ClearKeyDemo.app/Contents/MacOS/ClearKeyDemo'),'--url','http://127.0.0.1:8766/encrypted/stream.m3u8','--allow-capture','false','--output-order',order,'--duration','11','--output',str(case)],stdout=console,stderr=console)
  ready=False
  for n in range(60):
   p=case/'player-state.json'
   if p.exists():
    try:
     state=json.loads(p.read_text());ready=state['isReadyForDisplay'] and state.get('currentTimeSeconds',0)>1
     if ready:break
    except (KeyError,json.JSONDecodeError):pass
   time.sleep(.1)
  (case/'state-before-capture.json').write_text(json.dumps({'playbackReadyAndAdvanced':ready,'state':state},indent=2))
  screenshot=subprocess.run(['/usr/sbin/screencapture','-x','-l',str(state['windowID']),str(case/'system-window.png')],capture_output=True,text=True)
  (case/'system-capture.json').write_text(json.dumps({'exitCode':screenshot.returncode,'stderr':screenshot.stderr},indent=2))
  probe=subprocess.run([str(root.parent/'build/CaptureProbe'),'--window-id',str(state['windowID']),'--duration','0.5','--output',str(case/'capture')],capture_output=True,text=True)
  (case/'probe-console.log').write_text(probe.stdout+probe.stderr)
  app.wait(timeout=20)
  images=sorted(case.rglob('*.png'))
  inspect=subprocess.run([str(root.parent/'build/InspectMedia'),*[str(x) for x in images]],capture_output=True,text=True)
  (case/'media-inspection.jsonl').write_text(inspect.stdout)
  print(order,ready,len(images),flush=True)
finally:
 server.terminate();server.wait(timeout=5);log.close()
(out/'main.swift.snapshot').write_text((root/'Sources/ClearKeyDemo/main.swift').read_text())
print(out,flush=True)
