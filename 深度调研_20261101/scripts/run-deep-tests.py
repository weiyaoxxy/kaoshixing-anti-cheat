#!/usr/bin/env python3
from pathlib import Path
import subprocess, time, json, datetime, re, threading, hashlib
root=Path(__file__).resolve().parent.parent
out=root/'artifacts'/('deep-matrix-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
out.mkdir(parents=True)
(root/'artifacts/latest-deep-matrix.txt').write_text(str(out))
app=root/'build/ExamCaptureDeepDemo.app/Contents/MacOS/ExamCaptureDemo'
probe=root/'build/CaptureProbe'
inspector=root/'build/InspectMedia'
for tool in [app,probe,inspector]:
    if not tool.exists(): raise RuntimeError(f'Build first: {tool}')
configs=[dict(name='extended-'+m,mode=m,kind='extended',duration=20) for m in ['baseline','protected','mixed']]
configs += [dict(name=s+'-'+scope,mode='baseline' if s=='sharing-toggle' else 'protected',kind='lifecycle',scenario=s,scope=scope,duration=24) for s in ['protection-toggle','sharing-toggle','window-lifecycle'] for scope in ['window','display']]
configs += [dict(name='window-lifecycle-baseline-'+scope,mode='baseline',kind='lifecycle',scenario='window-lifecycle',scope=scope,duration=24) for scope in ['window','display']]
configs += [dict(name='render-4x-60fps',mode='protected',kind='performance',scale='4',fps='60',duration=20)]
for conf in configs:
    case=out/conf['name']; case.mkdir()
    cmd=[str(app),'--mode',conf['mode'],'--output',str(case),'--record','--duration',str(conf['duration'])]
    if conf['kind']=='extended': cmd += ['--self-capture']
    if 'scenario' in conf: cmd += ['--scenario',conf['scenario']]
    if 'scale' in conf: cmd += ['--render-scale',conf['scale'],'--fps',conf['fps']]
    (case/'test-config.json').write_text(json.dumps({'config':conf,'command':cmd,'sourceSHA256':hashlib.sha256((root/'Sources/ExamCaptureDemo/main.swift').read_bytes()).hexdigest()},indent=2))
    with (case/'demo-console.log').open('w') as log:
      proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
      samples=[]
      def sample():
        while proc.poll() is None:
          res=subprocess.run(['ps','-p',str(proc.pid),'-o','%cpu=,rss='],capture_output=True,text=True)
          try:
            cpu,rss=res.stdout.split();samples.append({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cpuPercentReportedByPS':float(cpu),'rssKiB':int(rss)})
          except ValueError: pass
          time.sleep(1)
      thread=threading.Thread(target=sample,daemon=True);thread.start()
      state={}
      for _ in range(60):
        try:
          state=json.loads((case/'demo-state.json').read_text())
          if state.get('isReadyForDisplay') and state.get('submittedFrames',0)>10:break
        except (FileNotFoundError,json.JSONDecodeError):pass
        time.sleep(.1)
      if not state.get('windowID') or not state.get('isReadyForDisplay') or state.get('submittedFrames',0)<=10:
        proc.wait(timeout=35)
        raise RuntimeError(f'No ready target; case is inconclusive: {case}')
      (case/'initial-state.json').write_text(json.dumps(state,indent=2))
      if conf['kind']=='extended':
        with (case/'probe-console.log').open('w') as log2:
          subprocess.run([str(probe),'--window-id',str(state['windowID']),'--extended','--capture-application','--omit-cursor','--output',str(case/'capture')],stdout=log2,stderr=subprocess.STDOUT,timeout=35,check=True)
        vals=[float(v) for v in re.findall(r'-?\d+(?:\.\d+)?',state['windowFrameAppKit'])]
        screen=[float(v) for v in re.findall(r'-?\d+(?:\.\d+)?',state['screenFrame'])]
        x,y,w,h=vals; rect=','.join(str(round(v)) for v in [x,screen[3]-y-h,w,h])
        result=subprocess.run(['/usr/sbin/screencapture','-v','-V','3','-R'+rect,str(case/'system-recording.mov')],capture_output=True,text=True,timeout=10)
        (case/'system-recording-result.json').write_text(json.dumps({'command':['screencapture','-v','-V','3','-R'+rect],'returnCode':result.returncode,'stdout':result.stdout,'stderr':result.stderr},indent=2))
      elif conf['kind']=='lifecycle':
        with (case/'probe-console.log').open('w') as log2:
          subprocess.run([str(probe),'--window-id',str(state['windowID']),'--only','stream','--scope',conf['scope'],'--duration','20','--omit-cursor','--output',str(case/'capture')],stdout=log2,stderr=subprocess.STDOUT,timeout=35,check=True)
      proc.wait(timeout=35);thread.join(timeout=2)
      (case/'resource-samples.json').write_text(json.dumps({'method':'ps point samples, own process only; not GPU utilization or end-to-end latency','samples':samples},indent=2))
      final=json.loads((case/'demo-state.json').read_text())
      validity={'demoPIDMatches':final.get('pid')==proc.pid,'writerCompleted':final.get('writerStatus')==2 and not final.get('writerError'),'rendererError':final.get('rendererError'),'interpretation':'Validity only; successful API/status is not a protection verdict.'}
      if (case/'capture/report.json').exists():
        report=json.loads((case/'capture/report.json').read_text())
        validity['probePIDIsIndependent']=report.get('processID')!=proc.pid
        validity['capturePermission']=report.get('permissionAfter')
        validity['streams']={k:{'status':v.get('status'),'completeFramesSaved':v.get('completeFramesSaved',0),'errors':v.get('streamErrors',[])} for k,v in report.items() if k.startswith('stream_')}
      (case/'validity.json').write_text(json.dumps(validity,indent=2))
    media=sorted(case.glob('*.mp4'))+sorted(case.glob('*.mov'))+sorted(case.glob('self-sck-*.png'))+sorted((case/'capture').glob('*.png'))
    with (case/'media-inspection.jsonl').open('w') as f:
      subprocess.run([str(inspector)]+[str(p) for p in media],stdout=f,check=True,timeout=60)
    print(conf['name'],'completed',flush=True)
print(out,flush=True)
