#!/usr/bin/env python3
"""Read-only static inspection of installed UU/ToDesk application bundles.
Only known capture API names are retained from symbol/string searches.
Does not attach, launch, stop, inject, resign, or alter any target.
"""
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,os,plistlib,re,subprocess
BASE=Path(__file__).resolve().parents[1]
APPS=[Path('/Applications/ToDesk.app'),Path('/Applications/UURemote.app')]
MAGIC={bytes.fromhex(s) for s in ['feedface','cefaedfe','feedfacf','cffaedfe','cafebabe','bebafeca','cafebabf','bfbafeca']}
PAT=re.compile(r'CGDisplayStream[A-Za-z0-9_]*|CGDisplayCreateImage(?:ForRect)?|CGWindowListCreateImage(?:FromArray)?|SC(?:ScreenshotManager|Stream|ShareableContent|ContentFilter|Display|Window|RunningApplication)|CGPreflightScreenCaptureAccess|CGRequestScreenCaptureAccess|CGS[A-Za-z]*Capture[A-Za-z]*|SLS[A-Za-z]*Capture[A-Za-z]*|captureImageWithFilter:configuration:completionHandler:|captureImageInRect:completionHandler:|getShareableContentWithCompletionHandler:|getShareableContentExcludingDesktopWindows:onScreenWindowsOnly:completionHandler:|initWithFilter:configuration:delegate:|startCaptureWithCompletionHandler:|stopCaptureWithCompletionHandler:|addStreamOutput:type:sampleHandlerQueue:error:|stream:didOutputSampleBuffer:ofType:')
KEYS=['com.apple.security.get-task-allow','com.apple.security.cs.allow-dyld-environment-variables','com.apple.security.cs.disable-library-validation','com.apple.security.cs.disable-executable-page-protection','com.apple.security.cs.allow-unsigned-executable-memory','com.apple.security.cs.allow-jit','com.apple.security.app-sandbox']
def run(argv):
 r=subprocess.run(argv,capture_output=True,timeout=60)
 return r.returncode,r.stdout,r.stderr
rc,out,err=run(['/bin/ps','-axo','pid=,uid=,comm='])
processes=[]
for line in out.decode(errors='replace').splitlines():
 p=line.strip().split(None,2)
 if len(p)==3 and any(p[2].startswith(str(a)+'/') for a in APPS):processes.append({'pid':int(p[0]),'uid':int(p[1]),'executable':p[2]})
apps=[];targets=[]
for app in APPS:
 with (app/'Contents/Info.plist').open('rb') as f:d=plistlib.load(f)
 apps.append({'path':str(app),'bundleID':d.get('CFBundleIdentifier'),'version':d.get('CFBundleShortVersionString'),'build':d.get('CFBundleVersion')})
 rc,out,err=run(['rg','--files',str(app/'Contents')])
 for line in out.decode().splitlines():
  p=Path(line)
  try:
   with p.open('rb') as f:magic=f.read(4)
   if magic in MAGIC:targets.append((app,p))
  except OSError:pass
def inspect(item):
 app,p=item
 d={'app':app.name,'path':str(p),'relativePath':str(p.relative_to(app)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'runningInstances':[x for x in processes if x['executable']==str(p)]}
 rc,out,err=run(['/usr/bin/lipo','-archs',str(p)]);d['architectures']=out.decode().strip().split() if rc==0 else [];d['architectureReadReturnCode']=rc
 rc,out,err=run(['/usr/bin/codesign','-d','--verbose=4',str(p)])
 lines=err.decode(errors='replace').splitlines();d['signatureMetadataReadReturnCode']=rc
 d['codeDirectory']=next((l for l in lines if l.startswith('CodeDirectory ')),None)
 d['signatureIdentifier']=next((l.split('=',1)[1] for l in lines if l.startswith('Identifier=')),None)
 d['teamIdentifier']=next((l.split('=',1)[1] for l in lines if l.startswith('TeamIdentifier=')),None)
 d['runtimeVersion']=next((l.split('=',1)[1] for l in lines if l.startswith('Runtime Version=')),None)
 d['hardenedRuntimeFlag']='(runtime)' in (d['codeDirectory'] or '') or ',runtime' in (d['codeDirectory'] or '')
 rc,out,err=run(['/usr/bin/codesign','-d','--entitlements',':-',str(p)])
 d['entitlementsReadReturnCode']=rc;ent={}
 if out:
  try:
   offset=out.find(b'<?xml');ent=plistlib.loads(out[offset:] if offset>=0 else out);d['entitlementsParse']='parsed'
  except Exception:d['entitlementsParse']='parse-error'
 else:d['entitlementsParse']='no-output'
 d['selectedEntitlements']={k:ent.get(k,None) for k in KEYS}
 rc,out,err=run(['/usr/bin/otool','-L',str(p)])
 deps=[]
 for line in out.decode(errors='replace').splitlines():
  s=line.strip()
  if ' (compatibility version' in s:deps.append(s.split(' (compatibility version')[0])
 d['linkedLibraries']=sorted(set(deps));d['otoolReturnCode']=rc
 rc,out,err=run(['/usr/bin/nm','-u',str(p)])
 d['undefinedCaptureSymbolTokens']=sorted(set(PAT.findall(out.decode(errors='replace'))));d['nmReturnCode']=rc
 d['undefinedCaptureSymbolTokensByArchitecture']={}
 for arch in d['architectures']:
  arc,ao,ae=run(['/usr/bin/nm','-arch',arch,'-u',str(p)])
  d['undefinedCaptureSymbolTokensByArchitecture'][arch]={'returnCode':arc,'tokens':sorted(set(PAT.findall(ao.decode(errors='replace'))))}
 rc,out,err=run(['/usr/bin/strings','-a',str(p)])
 d['captureStringTokens']=sorted(set(PAT.findall(out.decode(errors='replace'))));d['stringsReturnCode']=rc
 return d
with ThreadPoolExecutor(max_workers=4) as pool:components=list(pool.map(inspect,targets))
rc,out,err=run(['/usr/bin/csrutil','status'])
sip={'returnCode':rc,'stdout':out.decode().strip(),'stderr':err.decode().strip()}
rc,out,err=run(['/usr/bin/sw_vers'])
launchItems=[]
for folder in [Path('/Library/LaunchAgents'),Path('/Library/LaunchDaemons'),Path.home()/'Library/LaunchAgents']:
 if not folder.exists():continue
 for lp in folder.glob('*.plist'):
  if not any(k in lp.name.lower() for k in ['todesk','uuremote']):continue
  try:
   with lp.open('rb') as f:li=plistlib.load(f)
   argv=li.get('ProgramArguments',[])
   launchItems.append({'path':str(lp),'label':li.get('Label'),'program':li.get('Program') or (argv[0] if argv else None),'keepAlive':li.get('KeepAlive'),'runAtLoad':li.get('RunAtLoad'),'userName':li.get('UserName')})
  except Exception as ex:launchItems.append({'path':str(lp),'error':type(ex).__name__})
report={'launchItems':launchItems,'createdAtUTC':datetime.now(timezone.utc).isoformat(),'mode':'read-only static inspection; no runtime attach/injection or launch/stop','applications':apps,'processSnapshot':processes,'systemIntegrityProtection':sip,'os':out.decode().strip(),'machOCount':len(components),'components':components,'interpretation':['Undefined imports, framework linkage and matching string tokens are static clues, not evidence of executed capture calls.','Selected entitlement null means the inspected entitlement plist did not contain the key; inspect entitlementsParse before interpreting.','CodeDirectory runtime flags plus exceptions inform possible launch-time experiments; they do not prove successful injection, active backend, or frame redaction.','A new process inherits environment only through its launch path; starting a GUI process with a hook does not automatically instrument already-running privileged services.']}
(BASE/'research/target-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
summary=[{'path':c['relativePath'],'app':c['app'],'architectures':c['architectures'],'hardenedRuntime':c['hardenedRuntimeFlag'],'captureSymbols':c['undefinedCaptureSymbolTokens'],'captureStrings':c['captureStringTokens']} for c in components if c['undefinedCaptureSymbolTokens'] or c['captureStringTokens']]
print(json.dumps({'machOCount':len(components),'captureCandidates':summary,'output':str(BASE/'research/target-audit.json')},ensure_ascii=False,indent=2))
