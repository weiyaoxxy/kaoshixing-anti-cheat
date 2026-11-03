#!/usr/bin/env python3
"""Audit real PNG pixels, capture validity and reversible hook controls.

This analyzer never launches the demo, captures the screen, or modifies a hook.
It reads an already completed matrix and writes analysis files inside it.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STATIC_PATHS = {
    'cg-window.png': ('window', ('coreGraphics', 'window'), 'CGWindowListCreateImage'),
    'cg-display.png': ('display', ('coreGraphics', 'display'), 'CGWindowListCreateImage'),
    'cg-direct-display.png': ('display', ('coreGraphics', 'directDisplay'), 'CGDisplayCreateImage'),
    'sck-screenshot-window.png': ('window', ('screenshot_window',), 'SCScreenshotManager.captureImage'),
    'sck-screenshot-display.png': ('display', ('screenshot_display',), 'SCScreenshotManager.captureImage'),
    'sck-screenshot-rectangle.png': ('rectangle', ('screenshot_rectangle',), 'SCScreenshotManager.captureImageInRect'),
}


def read_json(path: Path):
    try:
        return json.loads(path.read_text()), None
    except (OSError, ValueError) as error:
        return {}, f'{path.name}: {error}'


def json_lines(path: Path):
    rows, errors = [], []
    if not path.exists():
        return rows, errors
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('JSONL item is not an object')
            rows.append(row)
        except ValueError as error:
            errors.append({'line': number, 'error': str(error)})
    return rows, errors


def digest(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def normalize(text):
    return re.sub(r'[^A-Z0-9]', '', str(text).upper())


def ocr_all(matrix, paths, inspector, batch_size, timeout):
    cache_path = matrix / 'ocr.jsonl'
    old, cache_errors = json_lines(cache_path)
    cached = {r.get('path'): r for r in old if r.get('path')}
    inspector_hash = digest(inspector)
    hashes = {str(p.resolve()): digest(p) for p in paths}
    pending = [p for p in paths if not (
        (r := cached.get(str(p.resolve()), {})).get('inputSHA256') == hashes[str(p.resolve())]
        and r.get('inspectorSHA256') == inspector_hash and not r.get('error'))]
    with cache_path.open('a') as output:
        for offset in range(0, len(pending), batch_size):
            batch = pending[offset:offset + batch_size]
            failure = None
            try:
                run = subprocess.run([str(inspector), *[str(p.resolve()) for p in batch]],
                                     capture_output=True, text=True, timeout=timeout)
                returned = {}
                for line in run.stdout.splitlines():
                    try:
                        row = json.loads(line)
                        if isinstance(row, dict) and row.get('path'):
                            returned[str(Path(row['path']).resolve())] = row
                    except ValueError:
                        continue
                if run.returncode:
                    failure = f'InspectMedia exit={run.returncode}; {run.stderr[-500:]}'
            except subprocess.TimeoutExpired:
                returned = {}
                failure = f'InspectMedia timeout after {timeout}s'
            for path in batch:
                key = str(path.resolve())
                row = returned.get(key, {'path': key, 'error': failure or 'InspectMedia returned no result'})
                if failure:
                    row.setdefault('error', failure)
                row.update(inputSHA256=hashes[key], inspectorSHA256=inspector_hash,
                           matrixRelativePath=str(path.relative_to(matrix)))
                output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
                cached[key] = row
            output.flush()
            print(f'OCR {min(offset + batch_size, len(pending))}/{len(pending)} new images', flush=True)
    return {str(p.resolve()): cached[str(p.resolve())] for p in paths}, {
        'cacheFile': 'ocr.jsonl', 'cacheParseErrors': cache_errors,
        'currentImages': len(paths), 'newOrRetriedImages': len(pending),
        'inspector': str(inspector), 'inspectorSHA256': inspector_hash,
        'cachePolicy': 'Reuse only when input and inspector SHA-256 match and previous OCR had no error.'}


def observe(path, matrix, ocr):
    row = {'path': str(path.relative_to(matrix)), 'exists': path.exists()}
    if not path.exists():
        row['error'] = 'reported image missing'
        return row
    raw = ocr.get(str(path.resolve()), {})
    text = normalize(' '.join(raw.get('lines', [])))
    row['secretDetected'] = raw.get('secretDetected') is True or 'NATIVEEXAMSECRET' in text or 'HOOK9' in text
    # Require the actual new control marker; the old demo's PUBLIC-CONTROL-4M2P
    # is deliberately not accepted as evidence for this experiment.
    row['publicDetected'] = 'PUBLICCONTROLHOOK' in text
    # Parse each OCR line before stripping punctuation. Joining every line can
    # accidentally append unrelated desktop numbers to a legitimate tick.
    tick_pattern = r'LIVE\s*[-_–—]?\s*TICK\s*[-_:–—]?\s*(\d+)'
    row['liveTickValues'] = sorted({match for line in raw.get('lines', [])
                                  for match in re.findall(tick_pattern, line.upper())})
    row['inputSHA256'] = raw.get('inputSHA256')
    if not raw:
        row['ocrError'] = 'No OCR row'
    elif raw.get('error'):
        row['ocrError'] = raw['error']
    try:
        with Image.open(path) as source:
            image = source.convert('RGBA')
            extrema = image.getextrema()
            row.update(width=image.width, height=image.height,
                       allTransparent=extrema[3][1] == 0,
                       allRGBZero=all(pair == (0, 0) for pair in extrema[:3]),
                       allOpaqueBlack=all(pair == (0, 0) for pair in extrema[:3]) and extrema[3] == (255, 255),
                       rgbaExtrema=extrema)
            if (raw.get('width'), raw.get('height')) != image.size:
                row['ocrError'] = 'Inspector/image dimensions differ'
    except (OSError, ValueError) as error:
        row['error'] = str(error)
    return row


def aggregate(images):
    return {
        'files': sum(r.get('exists') is True for r in images), 'imageRecords': len(images),
        'readableImages': sum(r.get('exists') is True and not r.get('error') for r in images),
        'imageErrors': sum(bool(r.get('error')) for r in images),
        'ocrErrors': sum(bool(r.get('ocrError')) for r in images),
        'secretPositive': sum(r.get('secretDetected') is True for r in images),
        'publicPositive': sum(r.get('publicDetected') is True for r in images),
        'allTransparent': sum(r.get('allTransparent') is True for r in images),
        'allRGBZero': sum(r.get('allRGBZero') is True for r in images),
        'allOpaqueBlack': sum(r.get('allOpaqueBlack') is True for r in images),
        'dimensions': sorted({f"{r['width']}x{r['height']}" for r in images if 'width' in r}),
        'liveTickValues': sorted({v for r in images for v in r.get('liveTickValues', [])}),
        'secretPositivePaths': [r['path'] for r in images if r.get('secretDetected')],
        'publicMissingPaths': [r['path'] for r in images if not r.get('publicDetected')],
    }


def lookup(data, keys):
    for key in keys:
        if not isinstance(data, dict):
            return {}
        data = data.get(key, {})
    return data if isinstance(data, dict) else {}


def option(arguments, name, default):
    try:
        return arguments[arguments.index(name) + 1]
    except (ValueError, IndexError):
        return default


def expected_groups(report):
    if not report:
        # Without a report there is no evidence that any specific API ran.
        # Keep one explicit unavailable case instead of inventing nine calls.
        return [], []
    args = report.get('arguments', [])
    only, scope = option(args, '--only', 'all'), option(args, '--scope', 'all')
    extended = bool(report.get('extended')) or '--extended' in args or not report
    application = '--capture-application' in args or scope == 'application' or not report
    images = []
    if only in ('all', 'cg'):
        images += ['cg-window.png', 'cg-display.png']
        if extended:
            images.append('cg-direct-display.png')
    if only in ('all', 'screenshot'):
        images += [f'sck-screenshot-{s}.png' for s in ('window', 'display') if scope in ('all', s)]
        if extended:
            images.append('sck-screenshot-rectangle.png')
    streams = []
    if only in ('all', 'stream'):
        streams += [f'stream_{s}' for s in ('window', 'display') if scope in ('all', s)]
        if application and scope in ('all', 'application'):
            streams.append('stream_application')
    return images, streams


def mode_for(case, run):
    if run.get('mode') in ('audit', 'block'):
        return run['mode']
    name = case.name.lower()
    if 'recovery' in name or 'restored' in name:
        return 'recovery'
    if 'baseline' in name or 'no-hook' in name or 'no_hook' in name:
        return 'baseline'
    if name in ('audit', 'block'):
        return name
    return 'unknown'


def analyze_case(case, matrix, ocr):
    report, report_error = read_json(case / 'capture/report.json')
    run, run_error = read_json(case / 'run.json')
    state, state_error = read_json(case / 'target-before.json')
    mode = mode_for(case, run)
    issues = []
    for error in (report_error, run_error, state_error):
        if error:
            issues.append(error)
    if run.get('returnCode') != 0 or run.get('timedOut'):
        issues.append('capture process did not exit successfully')
    if report.get('permissionAfter') is not True:
        issues.append('screen capture permission not positively confirmed')
    if not report.get('processID') or report.get('processID') == state.get('ownerPID'):
        issues.append('independent capture process not confirmed')
    if not state.get('nativeUI') or state.get('captureProtectionEnabled') is not False:
        issues.append('ordinary native target without media protection not confirmed')
    if not state.get('exam', {}).get('visible'):
        issues.append('target window was not reported visible before capture')
    if report.get('targetWindowID') != state.get('windowID') or not state.get('windowID'):
        issues.append('capture target window ID not matched to native demo')
    if report and report.get('targetFoundInCGList') is not True:
        issues.append('target was absent from the on-screen CG window list; visible target control not confirmed')
    for key in ('setupError', 'targetError', 'shareableContentError'):
        if report.get(key):
            issues.append(f'capture report contains {key}')
    hooks, hook_parse_errors = json_lines(case / 'hook.jsonl')
    relevant_hooks = [r for r in hooks if r.get('pid') == report.get('processID') and r.get('mode') == mode]
    loaded = any(r.get('event') == 'image_loaded' for r in relevant_hooks)
    if mode in ('audit', 'block') and not loaded:
        issues.append('hook image_loaded not confirmed in capture PID/mode')
    if hook_parse_errors:
        issues.append('hook log contains malformed JSONL')
    api_counts = collections.Counter(r.get('api') for r in relevant_hooks if r.get('event') == 'capture_call')
    image_names, stream_names = expected_groups(report)
    image_names = sorted(set(image_names) | {p.name for p in (case / 'capture').glob('*.png')})
    stream_names = sorted(set(stream_names) | {k for k in report if k.startswith('stream_')}
                          | {p.name.replace('sck-stream-', 'stream_', 1).replace('-', '_')
                             for p in (case / 'capture').glob('sck-stream-*') if p.is_dir()})
    groups = []
    for filename in image_names:
        scope, report_keys, api = STATIC_PATHS.get(filename, ('unknown', (), 'unknown'))
        entry = lookup(report, report_keys) if report_keys else {}
        path = case / 'capture' / filename
        images = [observe(path, matrix, ocr)] if path.exists() else []
        local = []
        if entry.get('status') != 'saved':
            local.append('single-frame report status is not saved')
        if not path.exists():
            local.append('expected single-frame PNG missing')
        groups.append({'path': filename, 'kind': 'single-frame', 'scope': scope,
                       'api': api, 'reportStatus': entry.get('status'), 'reportEntry': entry,
                       'localIssues': local, 'images': images})
    for key in stream_names:
        entry = report.get(key, {})
        scope = key.removeprefix('stream_').removesuffix('_recreated')
        directory = case / 'capture' / entry.get('directory', 'sck-stream-' + scope)
        existing = {p.name: p for p in directory.glob('*.png')}
        samples = entry.get('frames', [])
        saved = [f for f in samples if f.get('saved') is True and f.get('file')]
        names = [f['file'] for f in saved]
        expected = set(names)
        image_metadata = {f['file']: f for f in saved}
        images = []
        for name in sorted(set(existing) | expected):
            image = observe(directory / name, matrix, ocr)
            if name in image_metadata:
                frame = image_metadata[name]
                image['sampleMetadata'] = {k: frame.get(k) for k in ('sampleValid', 'SCFrameStatusRaw', 'ptsSeconds', 'phase', 'attachments')}
            images.append(image)
        local = []
        if entry.get('status') != 'completed':
            local.append('stream did not complete successfully')
        if entry.get('streamErrors') or entry.get('lifecycleError'):
            local.append('stream/lifecycle errors present')
        if expected != set(existing):
            local.append('saved frame entries and PNG file names differ')
        if len(names) != len(expected):
            local.append('duplicate saved frame file names')
        if entry.get('completeFramesSaved') != len(saved) or entry.get('completeFramesReceived') != len(saved):
            local.append('complete/saved frame counters do not match actual saved entries')
        if any(f.get('sampleValid') is not True or f.get('SCFrameStatusRaw') != 0 for f in saved):
            local.append('saved frame has invalid sample or non-complete status')
        if not images:
            local.append('no actual stream PNG; zero frames is inconclusive')
        groups.append({'path': key, 'kind': 'stream', 'scope': scope, 'api': 'SCStream.addStreamOutput',
                       'reportStatus': entry.get('status'), 'localIssues': local, 'images': images,
                       'callbacks': len(samples), 'sampleStatusCounts': dict(collections.Counter(str(f.get('SCFrameStatusRaw')) for f in samples)),
                       'completeFramesReceived': entry.get('completeFramesReceived'),
                       'completeFramesSaved': entry.get('completeFramesSaved'), 'savedEntries': len(saved),
                       'filesPresent': len(existing), 'missingFiles': sorted(expected - set(existing)),
                       'extraFiles': sorted(set(existing) - expected), 'streamErrors': entry.get('streamErrors', []),
                       'lifecycleError': entry.get('lifecycleError')})
    if not groups:
        groups.append({'path': 'capture-unavailable', 'kind': 'unavailable', 'scope': 'unknown',
                       'api': 'unknown', 'reportStatus': None, 'images': [],
                       'localIssues': ['no capture report path or PNG output to assess']})
    for group in groups:
        stats = aggregate(group['images'])
        group.update(summary=stats, publicControlExpected=group['scope'] in ('display', 'application'))
        group['issues'] = issues + group.pop('localIssues')
        if stats['imageErrors'] or stats['ocrErrors']:
            group['issues'].append('image decode or OCR errors')
        if not stats['files']:
            group['issues'].append('no images to assess')
        group['captureValid'] = not group['issues']
        group['hookAPICalls'] = api_counts.get(group['api'], 0)
        group['secretVisibleControl'] = group['captureValid'] and stats['secretPositive'] == stats['files'] and stats['files'] > 0
        public_ok = not group['publicControlExpected'] or stats['publicPositive'] == stats['files']
        motion_ok = not (group['publicControlExpected'] and group['kind'] == 'stream') or len(stats['liveTickValues']) >= 2
        group['publicControlVerified'] = public_ok
        group['publicMotionVerified'] = motion_ok
        group['positiveControlEligible'] = group['secretVisibleControl'] and public_ok and motion_ok
        if not group['captureValid']:
            verdict = 'invalid-or-inconclusive-capture'
        elif mode in ('baseline', 'audit', 'recovery'):
            verdict = 'secret-visible-control' if group['secretVisibleControl'] else 'secret-not-consistently-readable-control'
            if group['secretVisibleControl'] and not public_ok:
                verdict = 'secret-visible-but-public-control-incomplete'
            elif group['secretVisibleControl'] and not motion_ok:
                verdict = 'secret-visible-but-public-motion-unconfirmed'
        elif mode == 'block':
            if stats['secretPositive']:
                verdict = 'secret-visible-in-block-output'
            elif not group['hookAPICalls']:
                verdict = 'no-secret-but-no-matching-hook-call-evidence'
            elif group['publicControlExpected'] and stats['publicPositive'] != stats['files']:
                verdict = 'no-secret-but-public-control-missing-or-incomplete'
            elif group['publicControlExpected'] and group['kind'] == 'stream' and len(stats['liveTickValues']) < 2:
                verdict = 'no-secret-but-public-motion-not-confirmed'
            else:
                verdict = 'redaction-observed-pending-baseline-audit-recovery'
        else:
            verdict = 'unknown-case-mode'
        group['observationVerdict'] = verdict
    return {'case': case.name, 'mode': mode, 'run': run, 'captureProcessID': report.get('processID'),
            'targetWindowID': state.get('windowID'), 'targetOwnerPID': state.get('ownerPID'),
            'permissionAfter': report.get('permissionAfter'), 'caseIssues': issues,
            'hook': {'imageLoadedInCapturePID': loaded, 'parseErrors': hook_parse_errors,
                     'eventCounts': dict(collections.Counter(r.get('event') for r in relevant_hooks)),
                     'captureAPICounts': dict(api_counts)}, 'groups': groups}


def cross_case_controls(cases):
    comparisons = []
    for index, case in enumerate(cases):
        if case['mode'] != 'block':
            continue
        for group in case['groups']:
            controls = {}
            for role in ('baseline', 'audit', 'recovery'):
                candidates = []
                for other_index, other in enumerate(cases):
                    if other['mode'] != role or (role == 'recovery' and other_index <= index) or (role != 'recovery' and other_index >= index):
                        continue
                    if (other['targetWindowID'], other['targetOwnerPID']) != (case['targetWindowID'], case['targetOwnerPID']):
                        continue
                    match = next((g for g in other['groups'] if g['path'] == group['path']), None)
                    if match and match['positiveControlEligible']:
                        candidates.append(other['case'])
                controls[role] = candidates
            observed = group['observationVerdict'] == 'redaction-observed-pending-baseline-audit-recovery'
            matched = all(controls.values())
            group['matchedControls'] = controls
            group['finalVerdict'] = 'redaction-supported-in-tested-path' if observed and matched else group['observationVerdict']
            if observed and not matched:
                group['finalVerdict'] = 'redaction-observed-but-positive-controls-incomplete'
            comparisons.append({'blockCase': case['case'], 'path': group['path'], 'controls': controls,
                                'allRequiredControlsMatched': matched, 'finalVerdict': group['finalVerdict']})
    return comparisons


def markdown(summary):
    out = ['# Hook 捕获矩阵分析', '', f"生成时间：{summary['analyzedAtUTC']}。", '',
           f"共 {len(summary['cases'])} 个 case，逐图解码与 OCR {summary['ocr']['currentImages']} 张 PNG。", '',
           '所有结果仅适用于保存并检查的图像；目标约 10 fps 的有限采样不能排除帧间瞬时泄露。OCR 阴性不是不可识别信息泄露的证明。', '',
           '| case | 路径 | API 状态 | 图数 | 秘密阳性 | 公共对照阳性 | 全透明 | 不透明全黑 | 判定 |',
           '|---|---|---|---:|---:|---:|---:|---:|---|']
    for case in summary['cases']:
        for group in case['groups']:
            s = group['summary']
            out.append(f"| {case['case']} | {group['path']} | {group.get('reportStatus')} | {s['files']} | {s['secretPositive']} | {s['publicPositive']} | {s['allTransparent']} | {s['allOpaqueBlack']} | {group.get('finalVerdict', group['observationVerdict'])} |")
    out += ['', '## 有效性与恢复对照', '',
            'baseline/audit/recovery 只有实际图像中持续可读到秘密标记，才构成正对照。block 的结论还要求同一路径有前置 baseline/audit 和后置无 hook recovery，并匹配同一窗口与 owner PID。', '',
            'display/application 应保留 PUBLIC-CONTROL-HOOK；连续流还应出现至少两个不同 LIVE-TICK。窗口或目标矩形本来不含公共窗口，因此不要求其中出现公共标记。', '',
            '缺图、权限未确认、目标不匹配、hook 未加载、退出失败、流错误、帧计数不一致、OCR/解码错误均不算保护成功。', '']
    for case in summary['cases']:
        if case['caseIssues']:
            out.append(f"- **{case['case']}**：" + '；'.join(case['caseIssues']))
        for group in case['groups']:
            extra = [issue for issue in group['issues'] if issue not in case['caseIssues']]
            if extra:
                out.append(f"- {case['case']} / {group['path']}：" + '；'.join(extra))
    out += ['', '逐图 OCR 原文及 SHA-256 缓存在 `ocr.jsonl`，分组统计、实际帧数、API 状态与恢复对照在 `summary.json`。缓存只有输入图片和检查器二进制哈希均一致且无 OCR 错误时才复用。', '']
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('matrix', type=Path)
    parser.add_argument('--inspector', type=Path, default=ROOT / 'build/InspectMedia')
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--ocr-timeout', type=float, default=180)
    args = parser.parse_args()
    matrix = args.matrix.resolve()
    inspector = args.inspector.resolve()
    if not matrix.is_dir() or not inspector.is_file() or args.batch_size < 1 or args.ocr_timeout <= 0:
        parser.error('matrix/inspector must exist; batch-size and timeout must be positive')
    manifest, manifest_error = read_json(matrix / 'manifest.json')
    named = [r.get('case') for r in manifest.get('cases', []) if isinstance(r, dict) and r.get('case')]
    cases = [matrix / name for name in named if (matrix / name).is_dir()]
    cases += [p for p in sorted(matrix.iterdir()) if p.is_dir() and p not in cases and ((p / 'capture').is_dir() or (p / 'run.json').exists())]
    if not cases:
        parser.error('no capture cases found')
    paths = sorted({p for case in cases for p in list((case / 'capture').glob('*.png')) + list((case / 'capture').glob('sck-stream-*/*.png'))})
    ocr, ocr_info = ocr_all(matrix, paths, inspector, args.batch_size, args.ocr_timeout)
    analyzed = [analyze_case(case, matrix, ocr) for case in cases]
    comparisons = cross_case_controls(analyzed)
    summary = {'schemaVersion': 1, 'analyzedAtUTC': datetime.now(timezone.utc).isoformat(),
               'matrix': str(matrix), 'manifestError': manifest_error, 'library': manifest.get('library'),
               'librarySHA256': manifest.get('librarySHA256'), 'ocr': ocr_info, 'cases': analyzed,
               'blockComparisons': comparisons,
               'limits': ['OCR misses can occur; an absent marker is not an exhaustive information-leak proof.',
                          'Only saved frames are analyzed; finite sampling cannot exclude between-frame flashes.',
                          'Programmatic auto-type updates are not physical keyboard or Chinese IME validation.',
                          'No result here proves hook deployment inside UU or ToDesk; these are independent controlled captures.']}
    write_json(matrix / 'summary.json', summary)
    (matrix / 'summary.md').write_text(markdown(summary))
    counts = collections.Counter(g.get('finalVerdict', g['observationVerdict']) for c in analyzed for g in c['groups'])
    print(json.dumps({'matrix': str(matrix), 'cases': len(cases), 'images': len(paths), 'verdictCounts': dict(counts),
                      'summary': str(matrix / 'summary.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
