#!/usr/bin/env python3
"""OCR saved PNGs and validate all four controls for each legacy API."""
from pathlib import Path
import argparse, hashlib, json, re, subprocess
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('matrix', type=Path)
a = p.parse_args()
matrix = a.matrix.resolve()
inspector = ROOT / 'build/InspectMedia'
ihash = hashlib.sha256(inspector.read_bytes()).hexdigest()
cache_path = matrix / 'ocr.jsonl'
cache = {}
if cache_path.exists():
    for line in cache_path.read_text().splitlines():
        row = json.loads(line)
        cache[(row['path'], row.get('sha256'), row.get('inspectorSHA256'))] = row
images = sorted(matrix.glob('*/capture/*.png'))
all_rows = []
for path in images:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    key = (str(path), digest, ihash)
    row = cache.get(key)
    if row is None or row.get('error'):
        run = subprocess.run([str(inspector), str(path)], capture_output=True, text=True, timeout=60)
        try:
            row = json.loads(run.stdout.strip())
        except Exception:
            row = {'path': str(path), 'error': 'Inspector output missing or invalid', 'inspectorReturnCode': run.returncode}
        row.update(sha256=digest, inspectorSHA256=ihash)
        if run.returncode:
            row['error'] = row.get('error', 'Inspector failed')
    try:
        with Image.open(path) as image:
            image.load()
            extrema = image.convert('RGBA').getextrema()
            row['decodedDimensions'] = list(image.size)
            row['rgbaExtrema'] = extrema
            row['allTransparent'] = extrema[3][1] == 0
            row['allOpaqueBlack'] = all(e[1] == 0 for e in extrema[:3]) and extrema[3][0] == 255
    except Exception as exc:
        row['error'] = 'PNG decode: ' + str(exc)
    joined = re.sub(r'[^A-Z0-9]', '', ' '.join(row.get('lines', [])).upper())
    row['examMarkerDetected'] = 'NATIVEEXAMSECRET' in joined or 'HOOK9' in joined
    row['publicMarkerDetected'] = 'PUBLICCONTROLHOOK' in joined
    row['liveTicks'] = sorted({int(m) for line in row.get('lines', []) for m in re.findall(r'LIVE\s*[-_–—]?\s*TICK\s*[-_:–—]?\s*(\d+)', line, re.I)})
    all_rows.append(row)
    # Preserve completed OCR even if a subsequent file fails.
    cache_path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in all_rows))

cases = []
for api in ['queue', 'runloop']:
    for mode in ['baseline', 'audit', 'block', 'recovery']:
        case = matrix / (api + '-' + mode)
        errors = []
        def read(name):
            try:
                return json.loads((case / name).read_text())
            except Exception as exc:
                errors.append('missing/invalid ' + name + ': ' + str(exc))
                return {}
        report, run, target = read('capture/report.json'), read('run.json'), read('target-before.json')
        rows = [r for r in all_rows if Path(r['path']).parent.parent == case]
        pid = report.get('pid')
        if run.get('returnCode') != 0 or run.get('timedOut'):
            errors.append('probe did not exit normally')
        if run.get('targetActivationReturnCode') != 0:
            errors.append('target activation failed')
        if not report.get('screenCapturePermissionPreflight'):
            errors.append('permission preflight not true')
        if not report.get('createCalled') or report.get('createReturnedNull', True):
            errors.append('stream not created')
        if report.get('startReturnCode') != 0 or report.get('stopReturnCode') != 0 or not report.get('stopCallbackObserved'):
            errors.append('start/stop lifecycle failed')
        errors.extend(report.get('errors', []))
        if not rows or report.get('savedPNGCount') != len(rows):
            errors.append('missing PNG or saved count mismatch')
        saved = [r for r in report.get('frames', []) if r.get('saved')]
        if {r.get('file') for r in saved} != {Path(r['path']).name for r in rows}:
            errors.append('report and file inventory mismatch')
        if sum(r.get('status') == 0 for r in report.get('frames', [])) != report.get('completeFrameCount'):
            errors.append('complete frame count mismatch')
        if report.get('callbackCount') != len(report.get('frames', [])):
            errors.append('callback count mismatch')
        if target.get('nativeUI') is not True or target.get('captureProtectionEnabled') is not False or target.get('ownerPID') == pid:
            errors.append('not an independent native target capture')
        for kind in ['exam', 'control']:
            if not target.get(kind, {}).get('visible') or target.get(kind, {}).get('sharingType') != 1:
                errors.append(kind + ' not visible/plain shared')
        for row in rows:
            if row.get('error') or row.get('allTransparent') or row.get('allOpaqueBlack'):
                errors.append(Path(row['path']).name + ' invalid/error/whole-screen blank')
            if row.get('decodedDimensions') != [report.get('outputWidth'), report.get('outputHeight')]:
                errors.append(Path(row['path']).name + ' size mismatch')
        logs = []
        logpath = case / 'hook.jsonl'
        if logpath.exists():
            for line in logpath.read_text().splitlines():
                try:
                    logs.append(json.loads(line))
                except Exception:
                    errors.append('malformed hook log')
        expected_symbol = 'CGDisplayStreamCreateWithDispatchQueue' if api == 'queue' else 'CGDisplayStreamCreate'
        if mode in ['audit', 'block']:
            if not any(r.get('event') == 'image_loaded' and r.get('pid') == pid and r.get('mode') == mode for r in logs):
                errors.append('no matching image_loaded')
            if not any(r.get('event') == 'capture_call' and r.get('api') == expected_symbol and r.get('pid') == pid and r.get('mode') == mode for r in logs):
                errors.append('selected create API not observed by hook')
            if mode == 'block' and not any(r.get('event') == 'display_stream_redacted' and r.get('pid') == pid for r in logs):
                errors.append('no hook redaction event')
            if any(r.get('event') in ['redaction_failed', 'display_stream_passthrough'] for r in logs):
                errors.append('hook reported failure/passthrough')
        elif logs:
            errors.append('unexpected hook log in no-hook control')
        secret = sum(r['examMarkerDetected'] for r in rows)
        public = sum(r['publicMarkerDetected'] for r in rows)
        ticks = sorted({v for r in rows for v in r['liveTicks']})
        if public != len(rows) or len(ticks) < 2:
            errors.append('public control missing or fewer than two observed LIVE-TICK values')
        if mode == 'block' and secret:
            errors.append('secret visible in block samples')
        if mode != 'block' and secret != len(rows):
            errors.append('secret not visible in every control sample')
        cases.append({'case': case.name, 'api': api, 'mode': mode, 'pid': pid, 'targetPID': target.get('ownerPID'), 'windowID': target.get('windowID'),
                      'completeFrameCount': report.get('completeFrameCount'), 'callbackCount': report.get('callbackCount'), 'frameStatusCounts': report.get('frameStatusCounts'),
                      'PNGCount': len(rows), 'secretPositive': secret, 'publicPositive': public, 'liveTicks': ticks,
                      'sampleChecksPass': not errors, 'errors': errors})
api_results = []
for api in ['queue', 'runloop']:
    groups = [r for r in cases if r['api'] == api]
    paired = len(groups) == 4 and all(r['sampleChecksPass'] for r in groups) and len({(r['targetPID'], r['windowID']) for r in groups}) == 1
    api_results.append({'api': api, 'result': 'redaction-supported-in-sampled-static-full-display-path' if paired else 'inconclusive-or-failed', 'allFourControlsValid': paired})
summary = {'matrix': str(matrix), 'scope': 'independent self-owned capture process only; not actual UU/ToDesk remote output',
           'totalPNGCount': len(all_rows), 'totalCompleteFrameCount': sum(r.get('completeFrameCount') or 0 for r in cases),
           'inspectorSHA256': ihash, 'cases': cases, 'apiResults': api_results,
           'limitations': ['Only saved samples were OCRed, not every complete callback.', 'Static single-screen BGRA; no source/destination rect.', 'Probe consumes full IOSurface; dirty-region-only consumers not tested.', 'Legacy unavailable SDK API accessed via historical exported symbols; not a supported current deployment guarantee.']}
(matrix / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
lines = ['# CGDisplayStream 独立探针结果', '', '范围：自有独立进程，不是 UU 或 ToDesk 远端画面。', '',
         '| case | PID | 完整帧 | 保存 PNG | 秘密/PNG | 公共/PNG | LIVE-TICK | 检查 |', '|---|---:|---:|---:|---:|---:|---|---|']
for r in cases:
    lines.append(f"| {r['case']} | {r['pid']} | {r['completeFrameCount']} | {r['PNGCount']} | {r['secretPositive']}/{r['PNGCount']} | {r['publicPositive']}/{r['PNGCount']} | {','.join(map(str,r['liveTicks']))} | {'有效' if r['sampleChecksPass'] else '无效/需检查'} |")
lines += ['', f"总计 {summary['totalCompleteFrameCount']} 个完整帧回调，保存并 OCR {len(all_rows)} 张 PNG。不是全部回调逐帧 OCR。", '']
for r in api_results:
    lines.append(f"- {r['api']}: {r['result']}")
for r in cases:
    if r['errors']:
        lines.extend(['', r['case'] + ': ' + '; '.join(r['errors'])])
lines += ['', '边界：单屏、静止目标、完整 BGRA IOSurface 消费；未验证只消费 dirty region 的客户端。旧 API 通过历史符号调用，不能推广为当前系统正式支持的部署接口。']
(matrix / 'summary.md').write_text('\n'.join(lines) + '\n')
print(json.dumps({'matrix': str(matrix), 'PNGs': len(all_rows), 'apiResults': api_results}, ensure_ascii=False))
