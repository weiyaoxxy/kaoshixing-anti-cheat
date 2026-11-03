#!/usr/bin/env python3
"""Drive only our NativeControlDemo and write immutable per-run evidence."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, subprocess, time, uuid

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT/'build/NativeControlDemo.app/Contents/MacOS/NativeControlDemo'
PROBE = ROOT/'build/CaptureProbe'
INPUT = ROOT/'build/NativeInputProbe'

def read(path):
    return json.loads(Path(path).read_text())

def write(path, value):
    path = Path(path)
    tmp = path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    tmp.replace(path)

def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def run(command, output, timeout=60):
    t=time.monotonic()
    result=subprocess.run([str(v) for v in command], capture_output=True, text=True, timeout=timeout)
    write(output, {'command':[str(v) for v in command], 'returnCode':result.returncode,
                   'stdout':result.stdout,'stderr':result.stderr,'elapsedSeconds':time.monotonic()-t})
    return result

class Session:
    def __init__(self, directory, mode, record=True, duration=180):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=False)
        self.log=(self.directory/'demo-console.log').open('w')
        self.commandline=[str(APP),'--mode',mode,'--output',str(self.directory),'--duration',str(duration)]
        if record:self.commandline.append('--record')
        source=(ROOT/'Sources/NativeControlDemo/main.swift').read_bytes()
        (self.directory/'source-snapshot.swift').write_bytes(source)
        self.proc=subprocess.Popen(self.commandline,stdout=self.log,stderr=subprocess.STDOUT)
        self.actions=[]
        write(self.directory/'run-config.json',{'command':self.commandline,'mode':mode,
            'appSHA256':hashlib.sha256(APP.read_bytes()).hexdigest(),
            'sourceSHA256':hashlib.sha256(source).hexdigest(),
            'probeSHA256':hashlib.sha256(PROBE.read_bytes()).hexdigest(),
            'startedAtUTC':datetime.now(timezone.utc).isoformat()})
        end=time.monotonic()+12
        while time.monotonic()<end:
            if self.proc.poll() is not None:raise RuntimeError('Demo exited before readiness')
            try:
                state=self.state()
                if state.get('isReadyForDisplay') and state.get('renderedFrames',0)>5:
                    write(self.directory/'initial-state.json',state)
                    return
            except (FileNotFoundError,json.JSONDecodeError):pass
            time.sleep(.1)
        raise RuntimeError('Demo did not become ready')

    def state(self):return read(self.directory/'demo-state.json')

    def command(self,action,**kw):
        data={'id':str(uuid.uuid4()),'action':action,**kw}
        before=self.state()
        start=time.monotonic()
        write(self.directory/'control-command.json',data)
        if action=='finish':return None
        while time.monotonic()-start<8:
            try:
                ack=read(self.directory/'control-ack.json')
                if ack.get('id')==data['id']:
                    self.actions.append({'command':data,'before':before,'after':ack['state'],
                                         'hostTimeRequest':start,'hostTimeAck':time.monotonic()})
                    write(self.directory/'harness-actions.json',self.actions)
                    return ack['state']
            except (FileNotFoundError,json.JSONDecodeError):pass
            if self.proc.poll() is not None:raise RuntimeError('Demo exited while waiting for command')
            time.sleep(.08)
        raise RuntimeError('No ack for '+action)

    def capture(self,name='capture',window_id=None,only='all',duration=1,offscreen=False,extended=True):
        if window_id is None:
            self.command('show')
            subprocess.run(['/usr/bin/open',str(APP.parents[2])],check=True)
            time.sleep(.4)
        state=self.state()
        wid=window_id if window_id is not None else state['windowID']
        args=[PROBE,'--window-id',str(wid),'--output',self.directory/name,'--only',only,
              '--duration',str(duration),'--omit-cursor']
        if extended:args+=['--extended']
        if extended and only in ('all','stream'):args+=['--capture-application']
        if offscreen:args+=['--include-offscreen']
        result=run(args,self.directory/(name+'-invocation.json'),timeout=50)
        if result.returncode:raise RuntimeError('Capture probe failed: '+name)
        report=read(self.directory/name/'report.json')
        if report.get('permissionAfter') is not True:raise RuntimeError('Capture permission missing; inconclusive')
        if report['processID']==self.proc.pid:raise RuntimeError('Probe is not independent')
        return report

    def input(self,name,*arguments):
        before=self.state()
        result=run([INPUT,'--pid',str(self.proc.pid),*arguments],self.directory/(name+'-input.json'),timeout=15)
        time.sleep(.3)
        after=self.command('saveFrame',filename=name+'-source.png')
        write(self.directory/(name+'-observation.json'),{'before':before,'after':after,'inputReturnCode':result.returncode})
        return after,result

    def finish(self):
        if self.proc.poll() is None:
            self.command('finish')
            self.proc.wait(timeout=20)
        self.log.close()
        state=self.state()
        write(self.directory/'final-state.json',state)
        write(self.directory/'validity.json',{'processExitCode':self.proc.returncode,'demoPIDMatches':state.get('pid')==self.proc.pid,
              'sourceWindowVisible':state.get('sourceWindowVisible'),'sourceWindowEverOrderedFront':state.get('sourceWindowEverOrderedFront'),
              'frameErrors':state.get('frameErrors'),'rendererError':state.get('rendererError'),
              'writerStatus':state.get('writerStatus'),'writerError':state.get('writerError'),
              'interpretation':'API/ready success is not a protection or interaction verdict. Human physical display and actual IME require separate evidence.'})
        return state
