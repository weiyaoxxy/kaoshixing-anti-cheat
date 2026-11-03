#!/usr/bin/env python3
from native_harness import *
import threading

out=ROOT/'artifacts'/('continuous-native-'+stamp());out.mkdir()
for mode in ['raster-baseline','raster-protected']:
    s=Session(out/mode,mode,duration=80)
    captures=[]
    try:
        state=s.command('setText',text='INPUTSECRETSTAGE00')
        for scope in ['window','display']:
            folder=s.directory/('capture-'+scope)
            cmd=[str(PROBE),'--window-id',str(state['windowID']),'--only','stream','--scope',scope,
                 '--duration','22','--omit-cursor','--output',str(folder)]
            f=(s.directory/(scope+'-probe-console.log')).open('w')
            p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT)
            captures.append((scope,p,f))
        end=time.monotonic()+8
        while time.monotonic()<end:
            if all(list((s.directory/('capture-'+scope)/('sck-stream-'+scope)).glob('frame-*.png')) for scope,_,_ in captures):break
            time.sleep(.1)
        else:raise RuntimeError('No first frame from both streams; no phase actions attempted')
        start=time.monotonic()
        schedule=[(1,'setText',{'text':'INPUTSECRETSTAGE01'}),(2.5,'select',{'location':11,'length':7}),
                  (3.5,'insert',{'text':'EDIT02'}),(5,'toggle',{}),(6,'button',{}),(7,'scroll',{'y':350}),
                  (8,'minimize',{}),(10,'restore',{}),(12,'hide',{}),(14,'show',{}),
                  (16,'setText',{'text':'INPUTSECRETSTAGEFINAL03'})]
        for offset,action,kw in schedule:
            delay=start+offset-time.monotonic()
            if delay>0:time.sleep(delay)
            s.command(action,**kw)
            s.command('saveFrame',filename=f'phase-{offset:g}-{action}-source.png')
        for scope,p,f in captures:
            p.wait(timeout=20);f.close()
            if p.returncode:raise RuntimeError(scope+' capture process failed')
        final=s.finish()
        reports={scope:read(s.directory/('capture-'+scope)/'report.json') for scope,_,_ in captures}
        write(s.directory/'continuous-validity.json',{'capturePermissions':{k:v.get('permissionAfter') for k,v in reports.items()},
              'independentPIDs':{k:v.get('processID')!=s.proc.pid for k,v in reports.items()},
              'sourceNeverVisible':not final.get('sourceWindowEverOrderedFront'),
              'driver':'file-command-programmatic native editor actions; this series does not claim CGEvent or human input'})
        print(mode,'continuous complete',flush=True)
    finally:
        for _,p,f in captures:
            if p.poll() is None:p.terminate();p.wait(timeout=10)
            if not f.closed:f.close()
        if s.proc.poll() is None:s.finish()
print(out,flush=True)
