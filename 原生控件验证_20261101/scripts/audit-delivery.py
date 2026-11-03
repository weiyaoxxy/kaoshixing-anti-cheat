#!/usr/bin/env python3
"""Offline consistency audit; never launches the Demo or capture/input tools."""
import json, hashlib
from pathlib import Path
r=Path(__file__).resolve().parents[1]
out={'offlineOnly':True,'interactiveChecks':[],'externalSamples':[],'errors':[]}
for batch,fname,modes in [('native-final-v03-20261101T133147Z','interaction-checks.json',['direct','raster-baseline','raster-protected']),('native-keyboard-20261101T133448Z','keyboard-checks.json',['raster-baseline','raster-protected'])]:
 for mode in modes:
  d=r/'artifacts'/batch/mode
  rows=json.loads((d/fname).read_text())
  checks=[x.get('passed',x.get('pass')) for x in rows]
  out['interactiveChecks'].append({'batch':batch,'mode':mode,'checks':len(checks),'passed':sum(x is True for x in checks)})
  ar=[json.loads(s) for s in (d/'native-image-analysis.jsonl').read_text().splitlines()]
  external=[x for x in ar if x['evidenceRole']=='external-system-capture']
  out['externalSamples'].append({'batch':batch,'mode':mode,'actual':len(external),'publicTokenPresent':sum(x['tokens']['public_control'] for x in external),'examTokenPresent':sum(x['tokens']['exam_secret'] for x in external),'nativeEditTokenPresent':sum(x['tokens']['native_edit'] for x in external),'inputPrefixPresent':sum(x['tokens']['input_secret_prefix'] for x in external)})
  summary=json.loads((d/'native-image-summary.json').read_text())
  if summary['ocrErrors'] or summary['imageErrors'] or summary['missingDeclaredPNGs']:out['errors'].append(str(d)+' OCR/image/missing failure')
  for stream in summary['streamIntegrity']:
   if stream.get('missing') or stream.get('extra') or stream.get('duplicateSavedNames'):out['errors'].append(str(d)+' stream file mismatch')
out['totalInteractiveChecks']=sum(x['checks'] for x in out['interactiveChecks'])
out['totalInteractivePassed']=sum(x['passed'] for x in out['interactiveChecks'])
assert out['totalInteractiveChecks']==out['totalInteractivePassed']==40
out['protectedValidImageObservations']=sum(x['publicTokenPresent'] for x in out['externalSamples'] if x['mode']=='raster-protected')
assert out['protectedValidImageObservations']==74
old=json.loads((r/'research/previous-documents-sha256.json').read_text())
out['previousDocumentsChecked']=len(old)
for p,s in old.items():
 f=r.parent/p
 if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest()!=s:out['errors'].append('Previous file changed: '+p)
v=json.loads((r/'research/video-integrity.json').read_text())['files']
out['videoCount']=len(v);out['decodedFrames']=sum(x['inputFrameCount'] for x in v)
for x in v:
 if x['fullDecodeReturnCode'] or x['fullDecodeErrors'] or x['nonIncreasingPTS']:out['errors'].append('Video failed: '+x['video'])
for x in json.loads((r/'research/report-figure-provenance.json').read_text()):
 if hashlib.sha256((r/x['source']).read_bytes()).hexdigest()!=x['sourceSHA256']:out['errors'].append('Figure source mismatch: '+x['source'])
assets=['Sources/NativeControlDemo/main.swift','build/NativeControlDemo.app/Contents/MacOS/NativeControlDemo','交付报告/原生控件保护_专项验证报告_v1.0.docx']
out['deliverableHashes']={p:hashlib.sha256((r/p).read_bytes()).hexdigest() for p in assets}
out['scope']='Counts prove saved evidence consistency, not universal capture prevention. Candidate-window leakage and excluded samples remain material findings.'
(r/'交付报告/交付校验.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in out.items() if k not in ['interactiveChecks','externalSamples','deliverableHashes']},ensure_ascii=False,indent=2))
if out['errors']:raise SystemExit(1)
