S=json.loads((DEEP/'deep-analysis-summary.json').read_text())
C={c['case']:c for c in S['cases']}
def streamstat(name,scope):return C[name]['streams'][scope]['summary']
def imageobs(name,suffix):
    return next((i for i in C[name]['images'] if i['path'].endswith(suffix)),None)
def outcome(name,suffix):
    row=imageobs(name,suffix)
    if not row:return '无有效图/未分析'
    if row.get('error') or not row.get('ocr'):return '无效/待复核'
    if row['ocr'].get('secretDetected'):return '秘密命中'
    if row['ocr'].get('nativeLeakDetected'):return '秘密无；原生有'
    return '秘密未检出'
def ratio(name,scope,kind='secretOCRPositive'):
    r=streamstat(name,scope);return f'{r[kind]}/{r["frames"]}'
def stage_ratio(name,scope,fragment):
    rows=[a for k,a in C[name]['streams'][scope]['stages'].items() if k.startswith('stable:') and fragment in k]
    if not rows:return '无该阶段PNG'
    return str(sum(a['secretOCRPositive'] for a in rows))+'/'+str(sum(a['frames'] for a in rows))

page('12  本轮扩展入口与同进程对照')
ptext(f'本轮12个case已完成采集和有效性记录，流检查覆盖{S["streamSamples"]}张已保存PNG。新增入口采用baseline、protected、mixed三组；API返回、实际图像和文件数分别核验。下表静图/视频项是有效代表图的内容观察，流项是秘密检出数/保存数。')
rows=[]
for label,suffix in [('CGDisplayCreateImage','cg-direct-display.png'),('SCK屏幕矩形','sck-screenshot-rectangle.png'),('同进程SCK窗口','self-sck-window.png'),('系统区域录屏代表帧','system-recording.decoded.png')]:
    rows.append([label]+[outcome('extended-'+m,suffix) for m in ['baseline','protected','mixed']])
for label,scope in [('SCK按应用流','application'),('SCK显示器流','display'),('SCK窗口流','window')]:
    rows.append([label]+[ratio('extended-'+m,scope) for m in ['baseline','protected','mixed']])
table(['新增路径','baseline','protected','mixed'],rows,[5.3,4,4,4.1],9)
h2('同进程也没有当前SCK回采豁免')
ptext('currentProcess + SCScreenshotManager在baseline取到试题，在protected的视频区域未取得试题；与此同时原始帧MP4可读。由此，本机“自己录制”应使用源帧分流；不能靠给同一进程调用SCK来绕过保护。mixed同进程回采仍可读普通overlay。')
h2('按应用捕获不会自动修复普通控件泄露')
a=streamstat('extended-mixed','application');b=streamstat('extended-mixed','display')
ptext(f'mixed的应用流{a["nativeOCRPositive"]}/{a["frames"]}帧、显示器流{b["nativeOCRPositive"]}/{b["frames"]}帧可读NATIVE-LEAK。窗口流则全透明；这正说明不同filter的遮蔽粒度不同，不能只选择最有利的结果。')
note('新增CGDisplayCreateImage为历史公开符号的运行时兼容实验；矩形版SCK是15.2+公开入口。系统录屏是screencapture -v -V 3 -R，不等于已经逐个测试QuickTime或所有快捷键UI。')

page('13  运行中切换保护：时间轴与正对照')
ptext('同一窗口和同一捕获流持续运行。约第4秒切baseline，第8秒切回protected，第12秒改mixed，第16秒回protected；每次写入唯一PHASE token，并记录操作前后hostTime。样本PTS对应默认host时钟。每次边界前后±0.5秒单独分组，所有边界帧仍保留。')
rows=[]
for label,part in [('初始protected','00-initial'),('关闭保护baseline','01-baseline'),('重新protected','02-protected'),('mixed','03-mixed'),('最终protected','04-protected')]:
    rows.append([label,stage_ratio('protection-toggle-window','window',part),stage_ratio('protection-toggle-display','display',part)])
table(['稳态阶段','窗口流秘密/PNG','显示器流秘密/PNG'],rows,[6.8,5.3,5.3],9.5)
for scope in ['window','display']:
    frames=C['protection-toggle-'+scope]['streams'][scope]['frames']
    boundary=[f for f in frames if f.get('boundaryFrame')]
    positive=sum(bool((f.get('ocr') or {}).get('secretDetected')) for f in boundary)
    ptext(f'{scope}边界组：{len(boundary)}张PNG，其中{positive}张秘密OCR阳性；这些样本未从统计中删除。',9.5)
ptext('显示器边界的10张阳性均含PHASE-01-BASELINE，按样本PTS对应的记录状态，保护当时处于关闭。未在开启保护的新阶段采样中检出秘密；这不排除采样间隙的闪帧。',9.5)
h2('必须降级解读的窗口流')
ptext('窗口流从protected开始后，连中途baseline也保持整图透明。因此它缺少本条持续流中的可见内容正对照，不能据此声称每次切换都得到了成功验证。显示器流在baseline阶段恢复可读，并可用PHASE-01-BASELINE定位内容；保护恢复后稳态未检出秘密。')
h2('时间分辨率限制')
ptext('捕获目标约10fps，PNG在回调队列中编码，调度和负载可能使间隔扩大。有限采样不能排除短于间隔的闪帧；±0.5秒分组只是分析标签，不是允许泄漏的宽限期。API调用结束也不等于物理显示已完成变化。')

page('14  动态 sharingType 与窗口生命周期')
h2('仅.none在本机动态测试仍影响输出')
rows=[]
for label,part in [('初始baseline','00-initial'),('第一次none','01-window-none'),('恢复baseline','02-baseline'),('第二次none','03-window-none'),('最终baseline','04-baseline')]:
    rows.append([label,stage_ratio('sharing-toggle-window','window',part),stage_ratio('sharing-toggle-display','display',part)])
table(['稳态阶段','窗口流秘密/PNG','显示器流秘密/PNG'],rows,[6.8,5.3,5.3],9)
ptext('窗口流frame-028的PTS比after-window-none日志晚约1.05ms，仍含旧baseline画面与PHASE-00-INITIAL；随后.none稳态均未检出。这是边界收到旧画面的观察，不是稳态新题泄露，也不能声称属性调用返回即撤回全部历史帧。时间差按两份日志相减，不是端到端延迟测量。')
imagefile(DEEP/'sharing-toggle-window/capture/sck-stream-window/frame-028.png','图6  边界旧帧局部：保留旧PHASE-00-INITIAL。裁自实际窗口流PNG；完整原图及PTS/事件日志归档。',6.1,crop=(0,264,1800,575))
h2('最小化 / 恢复 / 隐藏 / 显示有对照')
rows=[]
for mode,name in [('protected','window-lifecycle-'),('baseline','window-lifecycle-baseline-')]:
    for scope in ['window','display']:
        a=streamstat(name+scope,scope)
        rows.append([mode,scope,a['frames'],a['secretOCRPositive'],a['allTransparentFrames']])
table(['模式','路径','有效PNG','秘密阳性','全透明'],rows,[4,3.7,3.2,3.2,3.3],9)
ptext('捕获针对同一windowID，约第4秒最小化、第8秒恢复、第12秒隐藏、第16秒显示。未产生complete图像或窗口本来不可见的阶段，只能说明场景与捕获状态；不能算作保护增强。未保存回调的blank/idle/suspended等状态及无回调区间须和PNG分开审阅。')
note('这组操作不是全屏、Spaces、睡眠、锁屏或显示器热插拔测试。被遮挡的独立窗口捕获语义与整屏合成也不同，不能互相替代。[R08,R27]')

page('15  性能、录像完整性与实验异常')
rows=[]
for name in ['extended-baseline','extended-protected','render-4x-60fps']:
    c=C[name];s=c['finalState'];cpu=c['resourceSamples']['cpuPercentReportedByPS'];rss=c['resourceSamples']['rssKiB']
    rows.append([name.replace('extended-',''),f'{s["pixelWidth"]}×{s["pixelHeight"]}',s['targetFPS'],f'{s.get("recordedFrames")}/{s.get("recordingDroppedFrames")}',f'{s["renderMeanMS"]:.2f}/{s["renderP95MS"]:.2f}',f'{cpu["mean"]:.1f}/{cpu["max"]:.1f}',f'{rss["max"]/1024:.1f}'])
table(['条件','像素','目标fps','录入/拒收','提交均/P95 ms','ps CPU均/峰 %','RSS峰MiB'],rows,[2.6,2.7,1.5,2.5,3,2.8,2.3],8.5)
ptext('高分辨率案为3600×2000，不是3840×2160。20秒内的录入数量只证明编码器接受了这些源帧，不是物理显示60fps认证。不同case的其它系统负载与捕获负担不同，不能根据耗时大小断言高分辨率更快或做严格横向基准。')
h2('录像检查的两层含义')
vi=json.loads((DEEP/'video-integrity.json').read_text())
errors=sum(x['fullDecodeReturnCode']!=0 or bool(x['decodeErrors']) for x in vi['files'])
ptext(f'本轮{len(vi["files"])}个MP4/MOV已对完整文件执行解码检查，错误记录数为{errors}。此外对代表帧做OCR和图像核查。完整解码证明码流可读；它不等于对每帧题目、答案和遮挡语义逐一验收。各自录文件的完成状态、记录帧数与错误均归档。')
h2('保留的无效实验与修复')
ptext('首轮扩展探针在JSON写出时崩溃：系统附件presenterOverlayContentRect为CGRect.null，包含无穷坐标。该次目录保留为无效实验，不计入成功样本。新版将非finite值保留为显式字符串/字段并记录路径，写出前校验JSON；嵌套NaN/Inf/Bool回归检查通过，再以新目录重跑全部12组。')
ptext('实验设计审阅还促成了ready gate、每阶段唯一token、baseline窗口生命周期对照、逐帧OCR和结果有效性记录。审阅原文与修正说明一并保留，供复核者区分仪器缺陷与被测API行为。')
note('ps只采本应用进程，不含WindowServer或GPU；本测试没有测输入到光子的延迟、精确GPU耗时、功耗或两小时考试稳定性。')
