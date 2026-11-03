#!/usr/bin/env python3
from native_harness import *

tool=ROOT/'build/InputSourceProbe'
out=ROOT/'artifacts'/('native-ime-'+stamp());out.mkdir()
initial=subprocess.run([str(tool)],capture_output=True,text=True,check=True)
initial_info=json.loads(initial.stdout);write(out/'initial-input-source.json',initial_info)
original=initial_info['beforeID'];pinyin='com.apple.inputmethod.SCIM.ITABC'
if not any(v.get('id')==pinyin and v.get('enabled') and v.get('selectCapable') for v in initial_info['sources']):
    write(out/'not-tested.json',{'reason':'No enabled selectable Simplified Pinyin; did not install or enable input methods'})
    raise SystemExit(0)
results=[]
try:
    for mode in ['direct','raster-baseline','raster-protected']:
        s=Session(out/mode,mode,duration=80)
        try:
            state=s.command('setText',text='')
            pt=','.join(str(v) for v in state['controlGeometry']['field']['quartzGlobalCenter'])
            s.input('01-focus','--post','--activate','--global','--click',pt)
            sel=run([tool,'--select',pinyin],s.directory/'select-input-source.json',timeout=10)
            if sel.returncode:raise RuntimeError('Could not select installed Pinyin')
            # Real virtual-key events feed the active input method, unlike --text Unicode insertion.
            state,_=s.input('02-pinyin-compose','--post','--activate','--global',
                  '--key','n','--key','i','--key','h','--key','a','--key','o')
            write(s.directory/'composition-state.json',state)
            s.capture('capture-composition',only='screenshot')
            run(['/usr/sbin/screencapture','-x',str(s.directory/'system-composition-display.png')],s.directory/'system-composition-result.json',timeout=10)
            committed,_=s.input('03-commit','--post','--activate','--global','--key','space')
            write(s.directory/'committed-state.json',committed)
            s.capture('capture-committed',only='screenshot')
            s.input('ax-ime','--ax-inspect')
            results.append({'mode':mode,'compositionHasMarkedText':state.get('hasMarkedText'),
                'compositionText':state.get('editorText'),'markedRange':state.get('markedRange'),
                'committedText':committed.get('currentText'),'committedHasMarkedText':committed.get('hasMarkedText'),
                'ChineseCharactersCommitted':any('\u4e00'<=c<='\u9fff' for c in committed.get('currentText','')),
                'physicalHumanObservation':False,'inputMethod':pinyin,
                'driver':'Independent CGEvent virtual keys n i h a o and space, not direct Unicode insertion'})
            s.finish()
            print(mode,json.dumps(results[-1],ensure_ascii=False),flush=True)
        finally:
            if s.proc.poll() is None:s.finish()
finally:
    restored=run([tool,'--restore',original],out/'restore-input-source.json',timeout=10)
    if restored.returncode:raise RuntimeError('Original input source restoration failed')
write(out/'ime-summary.json',results)
print(out,flush=True)
