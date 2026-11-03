#!/usr/bin/env python3
"""Analyze new-root artifacts only; stage alignment never discards boundary frames."""
from __future__ import annotations
import argparse, collections, concurrent.futures, csv, hashlib, json, math, re, statistics, subprocess
from pathlib import Path
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent

def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default

def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []

def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def ocr_images(case, paths, batch_size=24):
    destination = case/'deep-ocr.jsonl'
    cached = {row['path']:row for row in read_rows(destination) if row.get('path')}
    hashes = {str(path.resolve()):digest(path) for path in paths}
    pending = [path for path in paths if cached.get(str(path.resolve()),{}).get('inputSHA256') != hashes[str(path.resolve())]]
    with destination.open('a') as output:
        for start in range(0,len(pending),batch_size):
            batch = pending[start:start+batch_size]
            run = subprocess.run([str(ROOT/'build/InspectMedia'),*[str(p.resolve()) for p in batch]],capture_output=True,text=True,timeout=300)
            returned = {}
            for line in run.stdout.splitlines():
                try:
                    row=json.loads(line)
                    if row.get('path'): returned[str(Path(row['path']).resolve())]=row
                except json.JSONDecodeError: continue
            for path in batch:
                key=str(path.resolve())
                row=returned.get(key,{'path':key,'error':f'Inspector returned no row; exit={run.returncode}; stderr={run.stderr[-1000:]}'})
                row['inputSHA256']=hashes[key]
                output.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
                cached[key]=row
            output.flush()
    return {str(path.resolve()):cached[str(path.resolve())] for path in paths}

def timeline(events):
    points=[]
    for event in events:
        name=event.get('event','')
        if name=='window-ready' or name.startswith('after-'):
            points.append({'label':f'{len(points):02d}-'+(name.removeprefix('after-') if name!='window-ready' else 'initial'),
                'event':name,'hostTimeSeconds':event['hostTimeSeconds'],'state':event})
    return sorted(points,key=lambda x:x['hostTimeSeconds'])

def assign_stage(frame, events):
    pts=frame.get('ptsSeconds')
    source='samplePTS'
    if not isinstance(pts,(int,float)) or not math.isfinite(pts):
        pts=frame.get('callbackHostUptimeSeconds');source='callbackHostUptime'
    if not isinstance(pts,(int,float)) or not math.isfinite(pts): return {'stage':'unaligned','timeSource':'missing'}
    points=timeline(events)
    if not points: return {'stage':'static','timeSource':source,'hostTimeSeconds':pts}
    if not (points[0]['hostTimeSeconds']-5 <= pts <= points[-1]['hostTimeSeconds']+120):
        return {'stage':'unaligned','timeSource':source,'hostTimeSeconds':pts,'reason':'Frame timestamp outside plausible scenario clock range'}
    active=max((p for p in points if p['hostTimeSeconds']<=pts),key=lambda p:p['hostTimeSeconds'],default=points[0])
    transitions=[]
    for index,event in enumerate(events):
        name=event.get('event','')
        if not name.startswith('before-'):continue
        action=name.removeprefix('before-')
        after=next((e for e in events[index+1:] if e.get('event')=='after-'+action),event)
        if event['hostTimeSeconds']-0.5 <= pts <= after['hostTimeSeconds']+0.5:
            transitions.append({'action':action,'label':f"{index:02d}-{action}@{event['secondsSinceLaunch']:.2f}s"})
    boundaries=transitions
    actions=[entry['action'] for entry in transitions]
    result={'stage':('transition:'+','.join(entry['label'] for entry in transitions)) if boundaries else 'stable:'+active['label'],
        'boundaryFrame':bool(boundaries),'boundaryActions':actions,'timeSource':source,'hostTimeSeconds':pts,
        'secondsSinceWindowReady':pts-points[0]['hostTimeSeconds'],'modeAtFrame':active['state'].get('mode'),
        'preventsCaptureAtFrame':active['state'].get('preventsCapture'),'sharingTypeAtFrame':active['state'].get('sharingType'),'phaseTokenAtFrame':active['state'].get('phaseToken'),
        'windowVisibleAtLastEvent':active['state'].get('windowVisible'),'miniaturizedAtLastEvent':active['state'].get('miniaturized')}
    callback=frame.get('callbackHostUptimeSeconds')
    if isinstance(callback,(int,float)):result['callbackMinusPTSSeconds']=callback-pts
    return result

def static_roi(path,size,state,report,scope):
    """Only static extended/performance cases; no ROI verdict during lifecycle changes."""
    backing=state.get('backingScale',2)
    canvas_w=state.get('pixelWidth',1800)/backing
    canvas_h=state.get('pixelHeight',1000)/backing
    # render-scale overrides buffer pixels but the canvas remains 900x500 points.
    canvas_w,canvas_h=900,500
    x,y,w,h=canvas_w-126,42,88,64
    iw,ih=size
    if path.name=='source-reference.png' or (path.name.startswith('self-recording-') and path.name.endswith('.decoded.png')):
        return [round(x*iw/canvas_w),round(y*ih/canvas_h),round((x+w)*iw/canvas_w),round((y+h)*ih/canvas_h)]
    bounds=report.get('targetRectangle')
    if not bounds:return None
    y+=bounds['height']-canvas_h
    if scope in ('display','application'):
        did=report.get('applicationFilter',{}).get('displayID') if scope=='application' else report.get('legacyDirectDisplayID')
        display=next((d['frame'] for d in report.get('scDisplays',[]) if d['id']==did),None)
        if not display:return None
        x+=bounds['x']-display['x'];y+=bounds['y']-display['y']
        sx,sy=iw/display['width'],ih/display['height']
    else:
        sx,sy=iw/bounds['width'],ih/bounds['height']
    return [round(x*sx),round(y*sy),round((x+w)*sx),round((y+h)*sy)]

def image_observation(path,case,ocr,metadata=None,events=None,roi=None):
    item={'path':str(path.relative_to(case)),'exists':path.exists()}
    if metadata:
        item['sampleValid']=metadata.get('sampleValid');item['SCFrameStatusRaw']=metadata.get('SCFrameStatusRaw')
        item['captureAttachments']=metadata.get('attachments',{})
        item.update(assign_stage(metadata,events or []))
    observation=ocr.get(str(path.resolve()))
    item['ocr']={k:observation.get(k) for k in ['secretDetected','nativeLeakDetected','publicDetected','error','lines','textObservations','textObservationCoordinateSpace']} if observation else None
    if observation:
        known_tokens=sorted(set(e['phaseToken'] for e in (events or []) if e.get('phaseToken')))
        normalized=''.join(re.sub('[^A-Z0-9]','',line.upper()) for line in observation.get('lines',[]))
        item['phaseTokensObserved']=[token for token in known_tokens if re.sub('[^A-Z0-9]','',token.upper()) in normalized]
        item['secretTextLocations']=[entry for entry in observation.get('textObservations',[]) if 'EXAM-SECRET' in entry.get('text','') or '7K9Q' in entry.get('text','')]
        item['nativeTextLocations']=[entry for entry in observation.get('textObservations',[]) if 'NATIVE-LEAK' in entry.get('text','') or '8R3T' in entry.get('text','')]
        if item.get('phaseTokenAtFrame') and item['phaseTokensObserved']:
            item['currentPhaseTokenObserved']=item['phaseTokenAtFrame'] in item['phaseTokensObserved']
            item['otherPhaseTokensObserved']=[t for t in item['phaseTokensObserved'] if t!=item['phaseTokenAtFrame']]
    if not path.exists():item['error']='Missing reported image; inconclusive';return item
    try:
        with Image.open(path) as source:im=source.convert('RGBA')
        item['width'],item['height']=im.size
        r,g,b,a=im.split()
        mask=ImageChops.multiply(ImageChops.multiply(r.point(lambda v:255 if v>=190 else 0),g.point(lambda v:255 if v<=90 else 0)),b.point(lambda v:255 if v>=190 else 0))
        mask=ImageChops.multiply(mask,a.point(lambda v:255 if v>=200 else 0))
        item['magentaPixelsWholeImage']=mask.histogram()[255]
        item['magentaBoundingBox']=mask.getbbox()
        item['nontransparentPixels']=im.width*im.height-a.histogram()[0]
        item['allTransparent']=item['nontransparentPixels']==0
        item['rgbaExtrema']=im.getextrema()
        item['allRGBZero']=all(pair==(0,0) for pair in im.getextrema()[:3])
        if roi:
            if not(0<=roi[0]<roi[2]<=im.width and 0<=roi[1]<roi[3]<=im.height):item['roiError']='Static ROI outside image'
            else:
                item['staticMarkerROI']=roi
                item['staticMarkerPixels']=mask.crop(roi).histogram()[255]
                item['staticMarkerArea']=(roi[2]-roi[0])*(roi[3]-roi[1])
                item['staticMarkerAlphaExtrema']=a.crop(roi).getextrema()
        else:item['roiPolicy']='No fixed ROI applied; retain full-image candidates and OCR for dynamic scene.'
    except Exception as error:item['error']=str(error)
    return item

def aggregate(frames):
    valid=[f for f in frames if not f.get('error')]
    def span(key):
        values=[f[key] for f in valid if isinstance(f.get(key),(int,float))]
        return [min(values),max(values)] if values else None
    return {'frames':len(frames),'readableImages':len(valid),'imageErrors':sum(bool(f.get('error')) for f in frames),
        'ocrRows':sum(f.get('ocr') is not None for f in frames),'ocrErrors':sum(bool((f.get('ocr') or {}).get('error')) for f in frames),
        'secretOCRPositive':sum((f.get('ocr') or {}).get('secretDetected') is True for f in frames),
        'nativeOCRPositive':sum((f.get('ocr') or {}).get('nativeLeakDetected') is True for f in frames),
        'allTransparentFrames':sum(f.get('allTransparent') is True for f in valid),
        'allRGBZeroFrames':sum(f.get('allRGBZero') is True for f in valid),
        'magentaWholeImageRange':span('magentaPixelsWholeImage'),'staticMarkerPixelRange':span('staticMarkerPixels'),
        'callbackMinusPTSRangeSeconds':span('callbackMinusPTSSeconds'),'phaseTokenCounts':dict(collections.Counter(t for f in frames for t in f.get('phaseTokensObserved',[]))),'currentPhaseTokenPositiveFrames':sum(f.get('currentPhaseTokenObserved') is True for f in frames),'otherPhaseTokenFrames':sum(bool(f.get('otherPhaseTokensObserved')) for f in frames),
        'secretPositivePaths':[f['path'] for f in frames if (f.get('ocr') or {}).get('secretDetected') is True],
        'nativePositivePaths':[f['path'] for f in frames if (f.get('ocr') or {}).get('nativeLeakDetected') is True]}

def analyze_case(case):
    conf=read_json(case/'test-config.json',{}).get('config',{})
    state=read_json(case/'demo-state.json',{})
    initial=read_json(case/'initial-state.json',state)
    report=read_json(case/'capture/report.json',{})
    events=read_json(case/'scenario-events.json',{}).get('events',[])
    all_png=sorted(case.glob('*.png'))+sorted((case/'capture').glob('*.png'))+sorted((case/'capture').glob('sck-stream-*/*.png'))
    ocr=ocr_images(case,all_png)
    dynamic=conf.get('kind')=='lifecycle'
    streams={}
    for key,log in report.items():
        if not key.startswith('stream_') or not isinstance(log,dict):continue
        scope=key.removeprefix('stream_').removesuffix('_recreated')
        directory=case/'capture'/log.get('directory','sck-stream-'+scope)
        present={p.name:p for p in directory.glob('*.png')}
        metadata={f['file']:f for f in log.get('frames',[]) if f.get('file')}
        saved=[f for f in log.get('frames',[]) if f.get('saved') and f.get('file')]
        expected={f['file'] for f in saved}
        frames=[]
        for name in sorted(set(present)|expected):
            path=directory/name
            roi=None
            if not dynamic and path.exists():
                try:
                    with Image.open(path) as image:roi=static_roi(path,image.size,initial,report,scope)
                except Exception: pass
            frames.append(image_observation(path,case,ocr,metadata.get(name),events,roi))
        samples=log.get('frames',[])
        stages=collections.defaultdict(list)
        stage_samples=collections.defaultdict(list)
        planned=[]
        for point in timeline(events):planned.append((point['hostTimeSeconds'],'stable:'+point['label']))
        for index,event in enumerate(events):
            if event.get('event','').startswith('before-'):
                action=event['event'].removeprefix('before-')
                planned.append((event['hostTimeSeconds']-0.5,f"transition:{index:02d}-{action}@{event['secondsSinceLaunch']:.2f}s"))
        for _,label in sorted(planned):stages[label]  # Zero-callback/zero-PNG phases remain explicit.
        aligned_samples=[]
        for sample in samples:
            aligned={**sample, 'timeAlignment':assign_stage(sample,events)}
            aligned_samples.append(aligned)
            label=aligned['timeAlignment']['stage']
            stages[label]  # Keep stages that received only idle/blank/unsaved callbacks.
            stage_samples[label].append(aligned)
        for frame in frames:stages[frame.get('stage','unreported')].append(frame)
        stage_results={label:{**aggregate(fs),'samplesReceived':len(stage_samples[label]),'sampleStatusCounts':dict(collections.Counter(str(sample.get('SCFrameStatusRaw')) for sample in stage_samples[label]))} for label,fs in stages.items()}
        streams[scope]={'status':log.get('status'),'streamErrors':log.get('streamErrors',[]),'lifecycleError':log.get('lifecycleError'),
            'filesPresent':len(present),'framesReportedSaved':log.get('completeFramesSaved'),'savedEntries':len(saved),
            'missingFiles':sorted(expected-set(present)),'extraFiles':sorted(set(present)-expected),
            'sampleStatusCounts':dict(collections.Counter(str(f.get('SCFrameStatusRaw')) for f in samples)),
            'sampleCountAllStatuses':len(samples),'unsavedSamples':[f for f in aligned_samples if not f.get('saved')],
            'summary':aggregate(frames),'stages':stage_results,'frames':frames}
    images=[]
    for path in sorted(case.glob('*.png'))+sorted((case/'capture').glob('*.png')):
        name=path.name
        scope='display' if 'display' in name else 'window'
        # System movie is rectangle-recorded; rectangle screenshot is target bounds.
        roi=None
        try:
            with Image.open(path) as image:roi=None if dynamic else static_roi(path,image.size,initial,report,scope)
        except Exception: pass
        images.append(image_observation(path,case,ocr,roi=roi))
    resources=read_json(case/'resource-samples.json',{}).get('samples',[])
    def resource_stats(key):
        values=[s[key] for s in resources if isinstance(s.get(key),(int,float))]
        return {'min':min(values),'max':max(values),'mean':statistics.mean(values),'samples':len(values)} if values else None
    result={'case':case.name,'config':conf,'initialState':initial,'finalState':state,'scenarioEvents':events,
        'probe':{k:report.get(k) for k in ['processID','permissionBefore','permissionAfter','scope','targetWindowID','targetFoundInSCList','targetFoundInCGList','configuration_window','configuration_display','configuration_application']},
        'separateProcesses':bool(state.get('pid') and report.get('processID') and state['pid']!=report['processID']),
        'captureResults':{k:v for k,v in report.items() if k.startswith('screenshot_') or k in ['coreGraphics','applicationFilter']},
        'selfCapture':read_json(case/'self-capture.json'),'systemRecording':read_json(case/'system-recording-result.json'),
        'mediaInspection':read_rows(case/'media-inspection.jsonl'),'images':images,'streams':streams,
        'resourceSamples':{'cpuPercentReportedByPS':resource_stats('cpuPercentReportedByPS'),'rssKiB':resource_stats('rssKiB'),'method':'ps process samples, not GPU or total system/WindowServer load'},
        'limitations':['Full-image magenta counts include desktop noise. Positive OCR is retained regardless of stage.','No fixed ROI is used for lifecycle frames. Boundary ±0.5s around before/after events is reported separately, never discarded.','Scenario calls mark requested action; animations may complete later. Last logged visibility is not a per-frame observation.','Only saved complete samples have image/OCR observations; all unsaved sample statuses are preserved.','Existing MP4/MOV inspection is representative-frame decoding, not whole-video verification.']}
    write_json(case/'deep-analysis.json',result)
    fields=['path','stage','boundaryFrame','hostTimeSeconds','modeAtFrame','preventsCaptureAtFrame','sharingTypeAtFrame','phaseTokenAtFrame','phaseTokensObserved','currentPhaseTokenObserved','allTransparent','nontransparentPixels','magentaPixelsWholeImage','staticMarkerPixels','secretOCR','nativeOCR','error']
    with (case/'deep-analysis-frames.csv').open('w',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for scope,stream in streams.items():
            for frame in stream['frames']:writer.writerow({**frame,'secretOCR':(frame.get('ocr') or {}).get('secretDetected'),'nativeOCR':(frame.get('ocr') or {}).get('nativeLeakDetected')})
    print(f'{case.name}: analyzed {len(all_png)} PNGs, {sum(s["summary"]["frames"] for s in streams.values())} stream frames',flush=True)
    return result

def markdown(matrix,cases):
    lines=['# 深度测试结果','',f'本报告只分析新目录 `{matrix.name}`。逐帧数据保存在各 case 的 `deep-analysis.json`、`deep-analysis-frames.csv` 和 `deep-ocr.jsonl`。原报告与证据未改写。','',
        '所有保存的流 PNG 均逐张解码并交给本轮 InspectMedia/Vision 执行 OCR；失败、缺图和无图单独保留。全图紫色像素用于观察候选变化，包含桌面噪声，不能单独认定题目泄漏或无泄漏。生命周期不套用静态窗口 ROI。','',
        '## 流结果总表','', '| case | scope | stream状态 | 保存/报告 | 秘密 OCR 阳性 | 原生 overlay 阳性 | 整图透明 | 全图紫色像素范围 |', '|---|---|---|---:|---:|---:|---:|---|']
    for case in cases:
        for scope,stream in case['streams'].items():
            a=stream['summary'];lines.append(f'| {case["case"]} | {scope} | {stream["status"]} | {a["frames"]}/{stream["framesReportedSaved"]} | {a["secretOCRPositive"]} | {a["nativeOCRPositive"]} | {a["allTransparentFrames"]} | {a["magentaWholeImageRange"]} |')
    lines += ['', '## 动态阶段（边界样本完整保留）','', '按样本 PTS 与 scenario 的 hostTime 对齐。每次 before/after 操作前后 ±0.5 秒都归入转换边界；没有丢弃这些帧。事件只是 API 调用时刻，窗口动画的实际完成可能更晚。阶段名称后数字来自操作时间；若阶段无 complete 样本，应结合 JSON 中 unsavedSamples 看状态，不能写成“零帧泄漏”。','']
    for case in cases:
        if case['config'].get('kind')!='lifecycle':continue
        lines += [f'### {case["case"]}','', '| 阶段 | 回调/PNG | 秘密阳性 | 原生 overlay 阳性 | 整图透明 | 全图紫色范围 | phase token计数 |','|---|---:|---:|---:|---:|---|---|']
        for scope,stream in case['streams'].items():
            for stage,a in stream['stages'].items():lines.append(f'| {stage} | {a["samplesReceived"]}/{a["frames"]} | {a["secretOCRPositive"]} | {a["nativeOCRPositive"]} | {a["allTransparentFrames"]} | {a["magentaWholeImageRange"]} | {a["phaseTokenCounts"]} |')
        lines += ['']
    lines += ['', '## 扩展 API 状态（无图不计为通过）','', '| case | CGDisplayCreateImage | 矩形截图 | 同进程 SCK 截图 | 系统区域录制返回码 |','|---|---|---|---|---:|']
    for case in cases:
        if case['config'].get('kind')!='extended':continue
        r=case['captureResults'];direct=r.get('coreGraphics',{}).get('directDisplay',{});rectangle=r.get('screenshot_rectangle',{})
        lines.append(f'| {case["case"]} | {direct.get("status", "未执行")} | {rectangle.get("status", "未执行")} | {(case.get("selfCapture") or {}).get("status", "未执行")} | {(case.get("systemRecording") or {}).get("returnCode", "未执行")} |')
    lines += ['', 'nil_image、skipped、error、未产生文件和非零录制退出码均不能计为保护通过；成功输出还需要查看下面实际像素与 OCR。','']
    lines += ['## 单帧、同进程截图与视频代表帧','', '| case | 文件 | 秘密 OCR | 原生 OCR | 全图透明 | 标记 ROI 紫色像素 |','|---|---|---|---|---|---:|']
    for case in cases:
        for image in case['images']:
            o=image.get('ocr') or {};lines.append(f'| {case["case"]} | {image["path"]} | {o.get("secretDetected")} | {o.get("nativeLeakDetected")} | {image.get("allTransparent")} | {image.get("staticMarkerPixels", "未应用")} |')
    lines += ['', '## 渲染与自录记录','', '| case | 画布像素 | 目标 fps | 提交帧 | 自录接受/拒收 | writer 状态 | render mean/P95 ms | 进程 CPU 均值/峰值 | RSS峰值MiB |','|---|---|---:|---:|---:|---:|---|---|---:|']
    for case in cases:
        s=case['finalState'];cpu=case['resourceSamples']['cpuPercentReportedByPS'] or {};rss=case['resourceSamples']['rssKiB'] or {}
        lines.append(f'| {case["case"]} | {s.get("pixelWidth")}×{s.get("pixelHeight")} | {s.get("targetFPS")} | {s.get("submittedFrames")} | {s.get("recordedFrames")}/{s.get("recordingDroppedFrames")} | {s.get("writerStatus")} | {s.get("renderMeanMS",0):.2f}/{s.get("renderP95MS",0):.2f} | {cpu.get("mean",0):.1f}/{cpu.get("max",0):.1f} | {rss.get("max",0)/1024:.1f} |')
    lines += ['', '该 CPU/RSS 是每秒 ps 进程样本，不含 WindowServer/GPU，不等于端到端延迟或功耗。自录接受帧数不等于逐帧播放验证；MP4/MOV 仅解码代表帧。全透明窗口输出应描述为“无窗口内容”，不能称为只遮蔽考试区。一次短时高分辨率测试不能外推长期稳定性或真实 WebView。','',
        '## 解释边界','', '- baseline、保护关闭阶段是泄漏检测器的阳性对照。保护打开后的阳性必须保留并检查对应图片，不能被混入关闭保护阶段。','- 矩形截图、应用过滤器、窗口过滤器、显示器过滤器是不同测试路径，不能互相替代。','- 全图紫色像素可能来自桌面其它窗口；静态 case 的 ROI 数量和 OCR 用于复核。动态 case 保留原始图以便确定变化来自何处。','- 最小化、隐藏状态没有可见窗口内容属于场景状态；不能当作捕获保护强度证据。','- capture API 调用成功、输出黑/透明、writer 完成均不能单独证明完整防截图能力。','']
    rendered='\n'.join(lines)
    reviewed=read_json(ROOT/'research/evidence-audit/deep-reviewed-findings.json',{})
    if reviewed.get('matrixName')==matrix.name:
        rendered=rendered.replace('## 流结果总表\n',reviewed['reviewedMarkdown']+'## 流结果总表\n',1)
    return rendered

def main():
    parser=argparse.ArgumentParser();parser.add_argument('matrix',type=Path);parser.add_argument('--workers',type=int,default=2);args=parser.parse_args()
    matrix=args.matrix.resolve()
    if not matrix.is_relative_to(ROOT/'artifacts'):raise SystemExit('Only this deep-research root artifacts may be analyzed/written.')
    cases=sorted(p for p in matrix.iterdir() if p.is_dir() and (p/'test-config.json').exists())
    if not cases:raise SystemExit('No deep test cases found')
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(3,args.workers))) as executor:results=list(executor.map(analyze_case,cases))
    output={'matrix':str(matrix),'cases':results,'streamSamples':sum(s['summary']['frames'] for c in results for s in c['streams'].values()),'boundaryHalfWidthSeconds':0.5,'method':'Whole-frame RGBA and marker candidate counts + per-frame Vision OCR; dynamic phases aligned by sample PTS/hostTime; boundary samples retained.'}
    write_json(matrix/'deep-analysis-summary.json',output)
    (ROOT/'docs/深度测试结果.md').write_text(markdown(matrix,results))
    print(f'Finished {len(results)} cases, {output["streamSamples"]} saved stream PNGs; {matrix}/deep-analysis-summary.json',flush=True)

if __name__=='__main__':main()
