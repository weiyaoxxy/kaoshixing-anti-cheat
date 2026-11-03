#!/usr/bin/env python3
from native_harness import *

out=ROOT/'artifacts'/('native-keyboard-'+stamp());out.mkdir()
for mode in ['raster-baseline','raster-protected']:
    s=Session(out/mode,mode,duration=80);checks=[]
    try:
        state=s.command('setText',text='INPUTSECRET WORD TWO')
        p=state['controlGeometry']['field']['quartzGlobalCenter'];left=p[0]-420
        common=['--post','--activate','--global']
        state,_=s.input('01-double-click',*common,'--double-click',f'{left+80},{p[1]}')
        checks.append({'action':'double-click','pass':state['selectionRange']['length']>0,'state':state})
        state,_=s.input('02-drag-selection',*common,'--drag',f'{left+20},{p[1]},{left+180},{p[1]}')
        checks.append({'action':'drag-selection','pass':state['selectionRange']['length']>0,'state':state})
        state,_=s.input('03-tab-checkbox',*common,'--key','tab')
        checks.append({'action':'tab-to-checkbox','pass':state['focus']=='checkbox','state':state})
        before=state['checkbox'];state,_=s.input('04-space-toggle',*common,'--key','space')
        checks.append({'action':'space-checkbox','pass':state['checkbox']!=before,'state':state})
        state,_=s.input('05-tab-button',*common,'--key','tab')
        checks.append({'action':'tab-to-button','pass':state['focus']=='button','state':state})
        before=state['buttonCount'];state,_=s.input('06-return-button',*common,'--key','return')
        checks.append({'action':'return-button','pass':state['buttonCount']==before+1,'state':state})
        state,_=s.input('07-tab-textview',*common,'--key','tab')
        checks.append({'action':'tab-to-textView','pass':state['focus']=='textView','state':state})
        state,_=s.input('08-shift-tab',*common,'--key','tab','--flags','shift')
        checks.append({'action':'shift-tab-to-button','pass':state['focus']=='button','state':state})
        s.capture(duration=1)
        write(s.directory/'keyboard-checks.json',checks)
        s.finish()
        print(mode,[(v['action'],v['pass']) for v in checks],flush=True)
    finally:
        if s.proc.poll() is None:s.finish()
print(out,flush=True)
