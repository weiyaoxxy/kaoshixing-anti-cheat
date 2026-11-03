#!/usr/bin/env python3
"""OCR every actual PNG in a native-control experiment without merging source and capture evidence.

Usage: python3 scripts/analyze-native-images.py artifacts/CASE [artifacts/CASE2 ...]
  --token edited=INPUT-SECRET-ABC --batch-size 24
The inspector decodes PNG pixels and uses Vision OCR. This script never counts an
API/status success, missing image, zero callbacks, or absent OCR hit as a security verdict.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import re
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TOKENS = {
    'exam_secret': 'EXAM-SECRET-7K9Q',
    'native_edit': 'NATIVE-EDIT-6T2W',
    'input_secret_prefix': 'INPUT-SECRET',
    'native_leak': 'NATIVE-LEAK-8R3T',
    'public_control': 'PUBLIC-CONTROL-4M2P',
}

def normalized(text):
    # Keep Unicode letters/digits so Chinese IME tokens remain meaningful.
    # ASCII letters/digits retain the same case/punctuation-insensitive behavior.
    return ''.join(character for character in text.upper() if character.isalnum())

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default

def read_rows(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows

def evidence_role(path, case):
    relative = path.relative_to(case)
    low = relative.as_posix().lower()
    name = path.name.lower()
    directories = [part.lower() for part in relative.parts[:-1]]
    # A screenshot targeting the hidden native window is still an external
    # capture. It must never be counted as a trusted native source snapshot.
    if any(part.startswith('hidden-source-capture') for part in directories) or case.name.lower().startswith('hidden-source-capture'):
        return 'external-hidden-source-target'
    if any(part.startswith('source-') and part.endswith(('-cg','-screenshot')) for part in directories):
        return 'external-source-window-control'
    if name.startswith('self-sck'):
        return 'same-process-system-capture'
    # Capture directories and system-recording frames take precedence over the
    # source filename suffix and the generic own-video frame directory.
    if any('capture' in part for part in directories) or name.startswith(('cg-', 'sck-', 'system-')):
        return 'external-system-capture'
    if (name.startswith('self-recording') and name.endswith(('.decoded.png', '-decoded.png'))) or 'video-frames' in directories:
        return 'own-recording-representative-frame'
    if name.startswith(('source-', 'native-source', 'native-frame')) or name.endswith('-source.png'):
        return 'native-source-reference'
    if 'snapshot' in low or name.startswith('snapshot'):
        return 'native-source-snapshot-unless-case-doc-says-otherwise'
    return 'unclassified-review-required'

def collect_report_evidence(case):
    expected = {}
    stream_checks = []
    capture_failures = []
    for report_path in sorted(case.rglob('report.json')):
        report = read_json(report_path, {})
        if not isinstance(report, dict):
            continue
        for key, stream in report.items():
            if not key.startswith('stream_') or not isinstance(stream, dict):
                continue
            directory = report_path.parent / stream.get('directory', 'sck-'+key.replace('_','-'))
            names = []
            for frame in stream.get('frames', []):
                if frame.get('saved') and frame.get('file'):
                    p = (directory/frame['file']).resolve()
                    names.append(p)
                    expected[p] = {k:frame.get(k) for k in ['phase', 'ptsSeconds', 'callbackHostUptimeSeconds', 'sampleValid', 'SCFrameStatusRaw']}
                    expected[p].update({'captureReport':str(report_path.relative_to(case)), 'streamKey':key})
            actual = set(directory.glob('*.png')) if directory.exists() else set()
            actual = {p.resolve() for p in actual}
            saved = stream.get('completeFramesSaved')
            stream_checks.append({
                'report': str(report_path.relative_to(case)), 'stream':key,
                'status':stream.get('status'), 'streamErrors':stream.get('streamErrors', []),
                'reportedSaved':saved, 'savedFrameRows':len(names), 'pngFiles':len(actual),
                'missing':[str(p.relative_to(case)) for p in sorted(set(names)-actual)],
                'extra':[str(p.relative_to(case)) for p in sorted(actual-set(names))],
                'duplicateSavedNames':len(names)-len(set(names)),
                'reportedCountMatchesRows':saved == len(names),
                'interpretation':'Zero saved frames or suspended callbacks are not a protection pass.'
            })
        def walk(value, parts):
            if isinstance(value,dict):
                if value.get('status') in ('error','skipped','nil_image','unavailable'):
                    capture_failures.append({'report':str(report_path.relative_to(case)), 'path':'.'.join(parts), 'details':value})
                if value.get('status') == 'saved' and isinstance(value.get('file'),str) and value['file'].lower().endswith('.png'):
                    p=(report_path.parent/value['file']).resolve()
                    expected.setdefault(p, {'captureReport':str(report_path.relative_to(case)), 'reportPath':'.'.join(parts)})
                for k,v in value.items():
                    if k not in ('frames','cgWindows','scWindows','scDisplays'):
                        walk(v,parts+[k])
            elif isinstance(value,list):
                for n,v in enumerate(value):walk(v,parts+[str(n)])
        walk(report,[])
    return expected,stream_checks,capture_failures

def analyze_case(case, inspector, tokens, batch_size):
    case=case.resolve()
    if not case.is_dir():raise RuntimeError(f'No case directory: {case}')
    paths=sorted(p.resolve() for p in case.rglob('*.png'))
    expected,stream_checks,capture_failures=collect_report_evidence(case)
    cache_path=case/'native-ocr-cache.jsonl'
    cached={r['path']:r for r in read_rows(cache_path) if r.get('path')}
    hashes={str(p):sha256(p) for p in paths}
    pending=[p for p in paths if cached.get(str(p),{}).get('inputSHA256') != hashes[str(p)] or cached.get(str(p),{}).get('error')]
    with cache_path.open('a') as f:
        for start in range(0,len(pending),batch_size):
            batch=pending[start:start+batch_size]
            try:
                run=subprocess.run([str(inspector),*[str(p) for p in batch]],capture_output=True,text=True,timeout=120)
                returned={}
                for line in run.stdout.splitlines():
                    try:
                        row=json.loads(line)
                        if row.get('path'):returned[str(Path(row['path']).resolve())]=row
                    except (ValueError,TypeError):pass
                failure=f'No inspector row; exit={run.returncode}, stderr={run.stderr[-600:]}'
            except subprocess.TimeoutExpired:
                returned={};failure='OCR batch timed out after 120 seconds'
            for p in batch:
                row=returned.get(str(p),{'path':str(p),'error':failure})
                row['inputSHA256']=hashes[str(p)]
                cached[str(p)]=row
                f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
            f.flush()
            print(f'{case.name}: OCR {min(start+batch_size,len(pending))}/{len(pending)} new images',flush=True)
    rows=[]
    for p in paths:
        ocr=cached[str(p)]
        lines=ocr.get('lines',[])
        text=normalized(' '.join(lines))
        row={
            'path':str(p.relative_to(case)), 'evidenceRole':evidence_role(p,case),
            'inputSHA256':hashes[str(p)], 'lines':lines,
            'textObservations':ocr.get('textObservations',[]),
            'tokens':{k:normalized(v) in text for k,v in tokens.items()},
            'inputSecretCandidateLines':[s for s in lines if 'INPUTSECRET' in normalized(s)],
            'metadata':expected.get(p,{}),
        }
        if ocr.get('error'):row['ocrError']=ocr['error']
        try:
            with Image.open(p) as im:
                rgba=im.convert('RGBA')
                extrema=rgba.getextrema();alpha=rgba.getchannel('A').histogram()
                row.update({'width':rgba.width,'height':rgba.height,
                    'rgbaExtrema':extrema,'allTransparent':alpha[0]==rgba.width*rgba.height,
                    'nontransparentPixels':rgba.width*rgba.height-alpha[0],
                    'allRGBZero':all(x==(0,0) for x in extrema[:3])})
        except Exception as e:row['imageError']=str(e)
        rows.append(row)
    groups={}
    for role in sorted({r['evidenceRole'] for r in rows}):
        group=[r for r in rows if r['evidenceRole']==role]
        groups[role]={'images':len(group),'tokens':{k:sum(r['tokens'][k] for r in group) for k in tokens},
            'allTransparent':sum(r.get('allTransparent',False) for r in group),
            'ocrErrors':sum('ocrError' in r for r in group),'imageErrors':sum('imageError' in r for r in group)}
    missing=[str(p.relative_to(case)) for p in expected if not p.exists()]
    summary={'case':str(case),'actualPNGCount':len(paths),'tokens':tokens,'groups':groups,
        'streamIntegrity':stream_checks,'missingDeclaredPNGs':missing,'captureFailureOrSkippedEntries':capture_failures,
        'ocrErrors':sum('ocrError' in r for r in rows),'imageErrors':sum('imageError' in r for r in rows),
        'limitations':[
            'No automatic security pass: inspect baseline positive controls, permission, actual input state and visual rendering.',
            'OCR-negative does not exclude readable text missed by OCR or unsampled frames.',
            'Own-recording representative frames and native source references are not external captures.',
            'Video completeness/full decoding is not evaluated by this PNG-only analyzer.',
            'Application status or successful API returns are not substituted for pixel evidence.'
        ]}
    (case/'native-image-analysis.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows))
    (case/'native-image-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'case':str(case),'PNG':len(paths),'groups':groups,'missing':len(missing),'ocrErrors':summary['ocrErrors'],'imageErrors':summary['imageErrors']},ensure_ascii=False),flush=True)
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases',nargs='+',type=Path)
    parser.add_argument('--inspector',type=Path,default=ROOT/'build/InspectMedia')
    parser.add_argument('--token',action='append',default=[],help='Extra OCR token NAME=TEXT')
    parser.add_argument('--batch-size',type=int,default=24)
    options=parser.parse_args()
    if not options.inspector.is_file():parser.error('Build/copy InspectMedia first')
    if not 1<=options.batch_size<=100:parser.error('batch size must be 1...100')
    tokens=dict(DEFAULT_TOKENS)
    for value in options.token:
        name,sep,text=value.partition('=')
        if not sep or not name or not normalized(text):parser.error('--token needs NAME=TEXT with at least one Unicode letter or digit')
        tokens[name]=text
    summaries=[analyze_case(p,options.inspector.resolve(),tokens,options.batch_size) for p in options.cases]
    invalid=any(s['missingDeclaredPNGs'] or s['ocrErrors'] or s['imageErrors'] or any(
        x['missing'] or x['extra'] or x['duplicateSavedNames'] or not x['reportedCountMatchesRows'] for x in s['streamIntegrity']) for s in summaries)
    raise SystemExit(2 if invalid else 0)

if __name__=='__main__':main()
