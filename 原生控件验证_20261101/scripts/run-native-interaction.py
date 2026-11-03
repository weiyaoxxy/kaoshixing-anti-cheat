#!/usr/bin/env python3
from native_harness import *
import argparse

parser=argparse.ArgumentParser()
parser.add_argument('--modes',nargs='+',default=['direct','raster-baseline','raster-protected','mixed'])
parser.add_argument('--tag',default='interaction')
opts=parser.parse_args()
out=ROOT/'artifacts'/(opts.tag+'-'+stamp());out.mkdir()
write(out/'matrix-plan.json',{'modes':opts.modes,'purpose':'Actual CGEvent input + native state + source bitmap + independent capture. Unicode injection is not an IME session.'})
results=[]
for mode in opts.modes:
    s=Session(out/mode,mode)
    checks=[]
    def check(name,after,expected,passed):
        checks.append({'name':name,'expected':expected,'passed':bool(passed),'observed':{k:after.get(k) for k in ['currentText','editorText','selectionRange','checkbox','buttonCount','scrollY','visibleFirstResponder','focus']}})
        write(s.directory/'interaction-checks.json',checks)
        print(mode,name,bool(passed),flush=True)
    try:
        state=s.command('setText',text='INPUTSECRETSTART5B7K')
        def point(name):return ','.join(str(v) for v in state['controlGeometry'][name]['quartzGlobalCenter'])
        common=['--post','--global','--activate']
        a,_=s.input('01-click-field',*common,'--click',point('field'))
        a,_=s.input('02-replace',*common,'--key','a','--flags','command','--text','INPUTSECRETABC123')
        check('replace-via-CGEvent',a,'INPUTSECRETABC123',a.get('editorText')=='INPUTSECRETABC123' and a.get('currentText')=='INPUTSECRETABC123')
        a,_=s.input('03-arrow-delete',*common,'--key','left','--key','delete')
        check('left-then-delete',a,'INPUTSECRETABC13',a.get('editorText')=='INPUTSECRETABC13')
        a,_=s.input('04-insert',*common,'--text','Z')
        check('insert-at-caret',a,'INPUTSECRETABC1Z3',a.get('editorText')=='INPUTSECRETABC1Z3')
        a,_=s.input('05-select-all',*common,'--key','a','--flags','command')
        check('select-all',a,'all characters selected',a.get('selectionRange')=={'location':0,'length':len('INPUTSECRETABC1Z3')})
        a,_=s.input('06-final-text',*common,'--text','INPUTSECRETFINAL7H5T')
        check('replace-selection',a,'INPUTSECRETFINAL7H5T',a.get('editorText')=='INPUTSECRETFINAL7H5T')
        a,_=s.input('07-checkbox',*common,'--click',point('checkbox'))
        check('checkbox-click',a,1,a.get('checkbox')==1)
        a,_=s.input('08-button',*common,'--click',point('button'))
        check('button-click',a,1,a.get('buttonCount')==1)
        a,_=s.input('09-scroll',*common,'--scroll','-180','--scroll-at',point('scroll'))
        check('scroll-wheel',a,'positive scrollY',a.get('scrollY',0)>0)
        s.command('saveFrame',filename='edited-source.png')
        s.capture(duration=1.5)
        s.input('ax','--ax-inspect')
        sid=s.state().get('sourceWindowID',-1)
        if sid>0:s.capture('hidden-source-capture',window_id=sid,only='all',duration=.6,offscreen=True)
        # System CLI is an independent user-facing entry, kept separate from API calls.
        state=s.state()
        run(['/usr/sbin/screencapture','-x','-l',str(state['windowID']),str(s.directory/'system-window.png')],s.directory/'system-window-result.json',timeout=10)
        run(['/usr/sbin/screencapture','-x',str(s.directory/'system-display.png')],s.directory/'system-display-result.json',timeout=10)
        final=s.finish()
        results.append({'mode':mode,'checks':checks,'writerStatus':final.get('writerStatus'),'directory':str(s.directory)})
    except Exception as e:
        write(s.directory/'harness-error.json',{'error':str(e)})
        try:s.finish()
        except Exception:pass
        raise
write(out/'interaction-summary.json',results)
print(str(out),flush=True)
