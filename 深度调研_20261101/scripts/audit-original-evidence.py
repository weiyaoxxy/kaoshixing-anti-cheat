#!/usr/bin/env python3
"""Read-only audit of the first-round evidence; write solely inside this new root."""
from pathlib import Path
import collections, datetime, hashlib, json

new_root = Path(__file__).resolve().parent.parent
old_root = new_root.parent
sets = [old_root / 'artifacts/matrix-20261101T082724Z', old_root / 'artifacts/filter-update-protected', old_root / 'artifacts/filter-update-window-none']
rows = []
for group in sets:
    reports = sorted(group.glob('*/capture/report.json')) if group.name.startswith('matrix-') else [group / 'report.json']
    for path in reports:
        report = json.loads(path.read_text())
        for key, stream in report.items():
            if not key.startswith('stream_') or not isinstance(stream, dict):
                continue
            directory = path.parent / stream.get('directory', key.replace('stream_', 'sck-stream-'))
            saved = [f for f in stream.get('frames', []) if f.get('saved') and f.get('file')]
            expected = [f['file'] for f in saved]
            files = sorted(directory.glob('*.png'))
            names = [f.name for f in files]
            pts = [f['ptsSeconds'] for f in saved if isinstance(f.get('ptsSeconds'), (float, int))]
            diffs = [b - a for a, b in zip(pts, pts[1:])]
            hashes = collections.Counter(hashlib.sha256(f.read_bytes()).hexdigest() for f in files)
            rows.append({
                'report': str(path.relative_to(old_root)), 'path': key,
                'reportSHA256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'status': stream.get('status'), 'permissionBefore': report.get('permissionBefore'), 'permissionAfter': report.get('permissionAfter'),
                'framesReportedSaved': stream.get('completeFramesSaved'), 'savedFrameEntries': len(saved),
                'filesPresent': len(files), 'missing': sorted(set(expected)-set(names)), 'extra': sorted(set(names)-set(expected)),
                'duplicateFileNamesInReport': len(expected)-len(set(expected)),
                'sampleStatusCounts': dict(collections.Counter(str(f.get('SCFrameStatusRaw')) for f in stream.get('frames', []))),
                'savedInvalidSamples': sum(not f.get('sampleValid') for f in saved),
                'streamErrors': stream.get('streamErrors', []),
                'ptsSpanSeconds': max(pts)-min(pts) if pts else None,
                'positiveMaxPTSGapSeconds': max(diffs) if diffs else None,
                'nonIncreasingPTSIntervals': sum(d <= 0 for d in diffs),
                'phaseCounts': dict(collections.Counter(f.get('phase', 'initial') for f in saved)),
                'phaseEvents': stream.get('phaseEvents', []),
                'uniquePNGByteHashes': len(hashes),
                'largestIdenticalPNGGroup': max(hashes.values()) if hashes else 0,
            })
summaries = []
for group in sets:
    data = json.loads((group / 'analysis-summary.json').read_text())
    for case in data['cases']:
        for kind, stream in case['streams'].items():
            summaries.append({'group': group.name, 'case': case['mode'], 'path': kind,
                **{k: stream.get(k) for k in ['imagesReadable','ocrFramesInspected','ocrSecretDetectedFrames','ocrNativeLeakDetectedFrames','markerDetectedFrames','allTransparentFrames','roiPixelCountMin','roiPixelCountMax']},
                'frameErrors': [f.get('error') for f in stream.get('frames',[]) if f.get('error')],
                'ocrErrorRows': [f['ocr']['error'] for f in stream.get('frames',[]) if f.get('ocr') and f['ocr'].get('error')],
            })
result = {'auditedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'sourceRoot': str(old_root),
    'method':'Read existing report.json, PNG byte hashes, and existing analysis-summary.json; no captures and no OCR rerun; original evidence not rewritten.',
    'streamLifetimes': len(rows), 'savedSamples': sum(r['filesPresent'] for r in rows),
    'allCountsMatch': all(r['filesPresent']==r['savedFrameEntries']==r['framesReportedSaved'] and not r['missing'] and not r['extra'] and not r['duplicateFileNamesInReport'] for r in rows),
    'allPermissionsPreflightTrue': all(r['permissionBefore'] is True and r['permissionAfter'] is True for r in rows),
    'allSamplesValidComplete': all(r['savedInvalidSamples']==0 and set(r['sampleStatusCounts'])=={'0'} for r in rows),
    'allStreamErrorsEmpty': all(not r['streamErrors'] for r in rows),
    'allRecordedOCRRowsPresent': all(r['imagesReadable']==r['ocrFramesInspected'] for r in summaries),
    'streamRows': rows, 'analysisRows': summaries,
    'originalDocumentSHA256': {str(p.relative_to(old_root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((old_root/'docs').glob('*.md'))}}
out = new_root / 'research/evidence-audit/original-evidence-audit.json'
out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['streamRows','analysisRows','originalDocumentSHA256']},indent=2,ensure_ascii=False))
for row in rows:
    print(row['report'],row['path'],'files',row['filesPresent'],'unique PNG hashes',row['uniquePNGByteHashes'],'span',round(row['ptsSpanSeconds'],3),'max gap',round(row['positiveMaxPTSGapSeconds'],3))
