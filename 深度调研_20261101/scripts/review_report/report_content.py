# Report content. All evidence references are relative to the two preserved research folders.
OLDM=OLD/'artifacts/matrix-20261101T082724Z'
DEEP=Path((ROOT/'artifacts/latest-deep-matrix.txt').read_text().strip())

page('macOS 考试窗口防截屏\n深度技术预研与验证报告','公开 API · 受保护渲染 · 自身录制 · DRM · 系统扩展')
ptext('评审版 v2.0   |   2026 年 11 月 1 日   |   本机实验 + 官方资料复核',10.5,bold=True,color=BLUE)
h2('供评审者先读的结论')
ptext('在本机 M4 / macOS 26.6.2 上，已实现并复测“考试内容通过受保护视频 Layer 显示、独立捕获无法取得已测区域、自身从原始帧保存录像”的原型。它要求改变敏感 UI 的呈现和录像架构，不能据此宣称任意现有窗口、任意系统版本或所有第三方录屏软件都受到同等保护。')
table(['决策项','建议'],[
 ('公开 API 主线','以 AVSampleBufferDisplayLayer.preventsCapture + 原始帧分流编码继续原型，限定支持范围后再做产品验收。'),
 ('保留普通 UI 的考试路线','优先评估 AutomaticAssessmentConfiguration（AAC）；需 Apple entitlement，运行与自录兼容性尚未验证。'),
 ('旧窗口属性','NSWindow.sharingType = .none 仅保留作兼容对照；官方当前文档不提供现代全路径保护承诺。'),
 ('系统扩展','未找到公开窗口级、按捕获进程授权的策略扩展点；不建议以 Kext 或私有 WindowServer 补丁作为常规产品方案。')],[3.4,14],9.5)
h2('这份报告的边界')
ptext('本报告整合上一轮保留证据与本轮新增实验。上一轮资料不覆盖、不改写；本轮源码、原始帧、截图和审阅产物单独保存在“深度调研_20261101”。截图全部来自合成试题，图下注明取得方式；原始渲染帧、录像解码帧与系统截图不混称为同一类证据。')
note('用途：架构评审、技术选型和后续验证排期。不是全平台安全认证，也不是已完成的考试客户端产品。')

page('01  评审导航与需求拆解')
ptext('建议先审阅目标映射、关键截图和本轮结果，再决定是否接受渲染改造或申请 AAC。对负向结论，重点核查捕获权限、阳性对照和实际像素，避免把失败、全透明或无窗口误写成防护通过。')
table(['用户目标','本报告如何验证','尚不能推导的结论'],[
 ('本机正常显示考试','上一轮用户明确确认 protected 模式题目、点击和输入正常；保存人工记录。','截图本身不能证明物理屏幕可见；本轮新增所有显示场景未逐项再获人眼确认。'),
 ('其他进程不能捕获','独立 PID 的 CaptureProbe、系统 screencapture；单帧与流分别检查，baseline 为阳性对照。','单台机器的有限采样不证明所有刷新、入口、系统和软件版本。'),
 ('自身仍可录制','对原始帧编码，完成 MP4 并实际解码；新增同进程 SCK 回采对照。','原始帧录像不自动包含桌面遮挡、系统弹窗、标题栏、IME 候选或声音。'),
 ('优先 Apple 公共能力','核对官方文档、SDK availability；对特殊 entitlement 和 legacy API 单独标识。','公共符号仍可动态调用，不等于仍属于支持的新部署 API。')],[2.7,7.3,7.4],9)
h2('证据分级')
table(['标记','含义','审阅要求'],[
 ('E1 本机实测','存在原始日志、图像/视频、独立过程与对照','结果必须限定设备、OS、参数和已保存采样。'),
 ('E2 官方依据','Apple 文档、SDK 声明或官方技术资料','分别记录公开语义、最低版本和弃用，不补造未公开内部机制。'),
 ('E3 架构推断','由已知机制提出的实现或风险判断','必须进一步试验，不能冒充已实现。'),
 ('U 未验证','缺设备/资格/媒体，或尚未执行有效实验','保留空白边界，给出补测条件与判据。')],[2.7,7.3,7.4],9)
note('所有图均有来源说明。文末提供可点击官方参考文献、复现命令及原始证据目录索引。')

page('02  威胁模型与保护边界')
h2('本次研究的对手与资产')
ptext('资产是合成考试题目、选项和作答回显的视觉内容。主要对手是同一登录会话中、拥有正常系统屏幕捕获授权的独立应用进程。探针与考试进程 PID 不同，避免由考试应用自行过滤自己的流而制造“保护”。本次不构造进程注入、管理员内存读取、内核攻击或系统完整性绕过。')
table(['渠道','本次覆盖','边界'],[
 ('屏幕像素捕获','CG 兼容接口、SCK 窗口/屏幕/应用/矩形、系统截图和录屏','覆盖具体测试入口；不等同全部录屏产品。'),
 ('同进程屏幕回采','新增 currentProcess + SCScreenshotManager','验证本机行为；不建立公开进程白名单。'),
 ('客户端明文模型/原始帧','为显示与编码必须存在；测试保存参考 PNG、MP4','Layer 捕获保护不是内存 DRM，也不保护已经输出的文件副本。'),
 ('辅助功能 / AX / 剪贴板','作为架构风险分析','像素画布不自动提供完整语义；公开语义可能被获授权辅助进程读取。'),
 ('外接采集 / 远程 / 相机','未完整实测','HDCP、AirPlay、VNC、采集卡和外部摄像是不同渠道，须分别定义需求。')],[3.3,6.9,7.2],9)
h2('不能用来证明成功的信号')
ptext('属性设置成功、preventsCapture 回读 true、renderer ready、SCStream 返回 complete、文件生成或单次 OCR 未命中，均不是充分证据。完整判断至少需要：本地可见、有效 baseline、捕获方有权限、目标窗口身份准确、实际图像可解码，以及敏感区和公开对照区的分别检查。')
h2('产品必须提前做出的取舍')
ptext('若要求保护普通 Web/AppKit 控件、完整无障碍语义与所有系统浮层，同时禁止任何其他进程取得题目，则当前像素保护 PoC 无法直接完成。应确定考试便利措施、辅助输入、允许应用及录像审计范围；这些是架构和产品约束，不能交给一个窗口属性解决。')

page('03  推荐架构与自身录制语义')
h2('最小受保护渲染链')
table(['步骤','实现','职责'],[
 ('1','鼠标 / 键盘 → 考试状态','维护选择、文本和焦点；保护前必须避免明文控件先显示。'),
 ('2','CoreGraphics → IOSurface-backed CVPixelBuffer','按画布实际像素分辨率绘制题目和答案；本 PoC 是 CPU 绘制。'),
 ('3A','CMSampleBuffer → AVSampleBufferDisplayLayer','设置 preventsCapture；在 macOS 14+ 使用 sampleBufferRenderer.enqueue。'),
 ('3B','同一原始帧 → AVAssetWriter','生成 H.264 MP4；无需再从屏幕抓取已显示像素。'),
 ('4','独立进程 → 系统捕获 → 验证','检查实际输出；不由考试进程创建“自愿排除自己”的外部流。')],[1.2,7.1,9.1],9.5)
h2('“自身能录制”有两种不同含义')
ptext('自有内容录像：客户端本来就拥有原始帧，把它们分流给编码器。这是本方案已经验证的主线。系统屏幕回采：客户端通过 SCK/CG 再抓取自己的窗口；没有文档说明 preventsCapture 对本进程自动豁免，本轮专门加以对照。')
ptext('两条视频路径在渲染源处分叉。录制成功不是突破保护，也不是为指定进程开白名单。系统标题栏、普通工具栏、叠加 NSTextField、光标和系统弹窗不会自动出现在自有帧录像中。正式产品若需要这些元素，必须纳入同一渲染/事件模型，并明确审计语义。[R01–R03]')
h2('设计含义')
ptext('保护面越集中，越容易审计；但需要自行承担命中测试、输入法、文字编辑、布局、无障碍和跨显示器缩放。现有 WebView 截图再上屏不应被默认为完整方案：原窗口首次显示、视频子层、原生弹窗和候选框都可能绕出保护面。')
note('本页是依据公开机制的概念架构，不是 WindowServer、SkyLight 或 ScreenCaptureKit 的逆向内部调用图。')

page('04  核心公开 API 核验','版本来自 macOS 26.5 SDK 与 Apple 文档；不是 Demo 的构建最低版本。')
table(['API / 最低 macOS','官方语义','结论与限制'],[
 ('preventsCapture\n10.15','保护 AVSampleBufferDisplayLayer 的视频图像免于捕获。','主候选；作用于显示 Layer，普通相邻控件不自动保护，没有捕获进程白名单。[R01]'),
 ('sampleBufferRenderer\n14.0','接收并渲染视频 sample buffer。旧 layer.enqueue 从15.0弃用。','PoC 14+ 使用新 renderer，较旧版本走兼容方法；捕获保护效果仍要测。[R02]'),
 ('NSWindow.sharingType.none\n10.5','历史窗口共享状态；当前在线文档称为系统不再使用的旧常量。','本机仍有输出变化，但不是现代全路径保证；文档与现象应同时保留。[R04]'),
 ('allowsCaptureOf\nClearKeyVideo\n26.4','允许/禁止 AVPlayer 的 Clear Key 加密视频进入截图、录屏、VideoOutput 等；默认false。','只管相应加密视频，不管普通UI，也不影响 FPS。本轮以有效 SAMPLE-AES 媒体补测。[R05]'),
 ('AVPlayer 外部保护状态\n10.12','isOutputObscuredDueToInsufficientExternalProtection，只读。','反映内容要求与外部保护条件，不是启用保护开关或系统录屏检测。[R06]'),
 ('DisplayLayer 外部保护状态\n11.3','同名只读状态及通知，针对解码输出。','false 不能推出没有人在捕获；本机普通画布可以一直为false。[R07]'),
 ('AVAssetWriter\n10.7','将应用提供的媒体样本编码并写文件。','原始帧分流所需工具；须等待finish并解码验证，不只检查文件存在。[R03]')],[4.8,5.8,6.8],9)
note('上述普通显示/编码 API 没有文档化的专用“防截图 entitlement”。应用沙盒文件访问、签名公证和捕获权限是不同层面的部署事项。')

page('05  捕获 API、权限与官方考试模式')
table(['对象 / 最低 macOS','用途与权限','与防护的关系'],[
 ('SCStream / SCContentFilter\n12.3','捕获方配置窗口、显示器或应用；普通跨应用枚举/捕获受屏幕录制 TCC 控制。','filter只约束创建者自己的流，不能让被捕获应用给所有别人设拒绝规则。[R08]'),
 ('SCScreenshotManager\n14.0；矩形版15.2','窗口/显示器filter单帧；captureImage(in:)按屏幕矩形获取。','同一框架不同入口仍须分别测试。[R09]'),
 ('SCShareableContent.currentProcess\n14.4','获取当前进程可访问的内容信息，文档允许无需TCC同意的该范围。','不是受保护像素的回采豁免；本轮同进程实测。[R10]'),
 ('CGWindowListCreateImage\n10.5 / 14弃用 / 15废止','旧窗口截图与显示器合成；本机动态符号兼容实验。','现代SDK不支持普通直接调用；返回NULL或全透明应分别记录。[R11]'),
 ('CGDisplayCreateImage\n10.6 / 14.4弃用 / 15废止','旧显示器截图；本轮单独调用，不再混称为cg-display。','动态调用仍导出的公开旧符号不等于受支持的新产品API。[R12]'),
 ('AutomaticAssessmentConfiguration\n10.15.4','Apple官方考试会话，可限制截屏/录屏和其他应用；需专用 entitlement。','公开但受限；不是窗口策略扩展，也不保证自己的SCK可绕过。[R13–R14]'),
 ('AAC allowsScreenshots\n26.1','配置是否允许考试期间指定的复制到剪贴板截图；默认禁止。','不是按应用录屏白名单；会话结束清理剪贴板。不能一概说所有AAC配置都绝对禁截屏。[R15]')],[5,6.3,6.1],9)
note('本次 CLI 捕获运行于已有 TCC 授权的宿主环境。新打包应用在其他电脑上的权限归属、提示和首次运行需要重新验证，不能自动继承本机结论。')

page('06  DRM、图形资源与系统路线')
table(['路线','可提供的能力','部署限制 / 评级'],[
 ('FairPlay Streaming','受保护加密媒体、密钥交付和播放链；非普通UI保护开关。','生产凭据需Apple审核；服务资格、KSM、证书与媒体管线。需要Apple支持+架构改造。[R16]'),
 ('HDCP','保护数字显示输出链路，与内容要求、显示器和转接器相关。','不能单独禁止软件截图，不能给任意NSWindow启用。需硬件链路补测。[R17]'),
 ('Protected Media Pipeline','系统内部受保护媒体机制的概念。','没有找到任意第三方UI可用的通用受保护缓冲区分配/授权契约；内部能力不能代替公共API。'),
 ('IOSurface','跨进程共享硬件加速图像缓冲，Mach port控制引用传递。','不是捕获排除策略；原始buffer仍是明文。本PoC用它满足视频显示输入要求。[R18]'),
 ('Metal private / memoryless','控制CPU/GPU访问及临时资源存储。','GPU-only不等于DRM；private自10.11，memoryless自11且硬件受限。[R19]'),
 ('System Extension / DriverKit','公开受支持的网络、安全与驱动家族。','macOS10.15+；签名、相应entitlement、激活/用户或MDM批准；无通用合成器拦截家族。[R20–R21]'),
 ('Endpoint Security','进程/文件授权事件；macOS13起有Screen Sharing附加/脱离通知。','Apple entitlement与FDA等条件；通知不是逐帧/逐窗口AUTH_SCREEN_CAPTURE。[R22]'),
 ('Kext / SkyLight / WindowServer','未公开稳定的第三方窗口捕获策略挂钩。','Apple Silicon Kext需启动安全配置、批准和重启；私有补丁无稳定契约。常规分发路线不成立。[R23]')],[3.5,6.8,7.1],9)
note('“未找到公开扩展点”是对本次官方文档和公开 SDK 的检索结论，不是声称 Apple 内部不存在更强能力；没有开发或加载 Kext，也没有修改 SIP/TCC/启动安全。')

page('07  实验设计、数据与判定')
table(['项目','条件'],[
 ('设备 / 软件','Apple M4，内置屏幕，macOS26.6.2（25G83），SDK26.5，Swift6.3.3；本地ad-hoc签名、无特殊受限 entitlement。'),
 ('尺寸 / 视频','1512×982 point屏幕，2×；考试画布900×500 point，默认1800×1000 pixel、20fps、H.264 8Mbps。'),
 ('独立性','Demo与CaptureProbe是不同PID；新增同进程回采另行标记；本地媒体服务仅127.0.0.1。'),
 ('阳性对照','baseline暴露相同合成试题；EXAM-SECRET-7K9Q秘密标记、紫色色块、PUBLIC-CONTROL普通区。'),
 ('泄露对照','mixed在受保护Layer上放普通NSTextField，标记NATIVE-LEAK-8R3T。'),
 ('像素检查','PNG真实解码；alpha/标记色统计；Vision OCR；动态实验不套用静态窗口ROI作为唯一判据。'),
 ('状态与异常','保存权限、windowID/PID、sampleValid、SCFrameStatus、PTS、attachments、错误及文件数量；透明/黑色/失败分开。'),
 ('录像有效性','writer结束状态+实际MP4/MOV解码；ClearKey另查媒体加密结构、播放状态/时间推进及VideoOutput。')],[3.4,14],9.5)
h2('上一轮证据如何使用')
ptext('上一轮五模式+两组filter更新/重建，共463张流PNG逐帧检查；该数字包含baseline及多个模式，不代表463张受保护帧。原始记录位于旧目录artifacts，本轮报告只引用并复制必要截图，原文件未覆盖。')
h2('负向样本不能过度解释')
ptext('OCR漏识别可以发生，上一轮公开区publicDetected在baseline也为false，证明不能靠这个字段独立判断公开UI是否消失。保护流整窗透明和截图局部黑色也是不同现象。生命周期分析按PTS与操作日志对齐，边界附近单列，不将统计窗口排除当成安全豁免。')

# Remaining pages use test results and figures; appended after deep experiment analysis.
page('08  已保留的五模式基础矩阵')
ptext('下表摘自上一轮原始证据，用于建立本轮新增测试的参照。命中表示秘密文字与预定标记在有效图像中出现；未检出只描述采样结果。黑色、透明和错误各有不同含义，不合并计为“通过”。')
table(['路径','baseline','仅 .none','Layer保护','两者','混合 UI'],[
 ('系统全屏截图','命中','未检出','未检出','未检出','秘密无；原生有'),
 ('系统窗口截图','命中','无有效图','未检出','无有效图','秘密无；原生有'),
 ('旧 CG 窗口截图','命中','全透明','未检出','全透明','秘密无；原生有'),
 ('SCK 窗口截图','命中','全透明','未检出','全透明','秘密无；原生有'),
 ('SCK 显示器流','21/21','0/21','0/22','0/21','秘密0/22；原生22/22'),
 ('SCK 窗口流','22/22','21透明','21透明','22透明','21透明'),
 ('原始帧 MP4 解码','命中','命中','命中','命中','命中')],[4.3,2.2,2.5,2.5,2.3,3.6],8.5)
note('Layer保护指preventsCapture=true。SCK 流数字是检出帧数/保存帧数；“透明”是透明图数量，不能与检出比例混读。')
h2('证据链')
ptext('主矩阵214帧，加上protected同filter更新/重建126帧和window-none补测123帧，共463张PNG。每张都实际解码、做像素统计与OCR，文件数与捕获报告相符；各组捕获权限为true。五段约18秒自录MP4均完成并解码得到试题。')
h2('本机显示与输入')
ptext('用户在2026-11-01确认：“本机可见完整题目，点击和输入正常”。确认的是SampleBuffer protected实例。后续定向自动事件计数0→6，372.573秒录像尾部出现xyz1，佐证ASCII输入与退格；自动鼠标点击未确认，人工陈述与自动日志分开保留。')
h2('不能被抹平的差异')
ptext('窗口流可能整图透明，而相同模式单帧截图仅视频区黑。仅.none的窗口命令截图返回错误，无图样本不计为保护成功。.none本机生效并不改变Apple当前不建议据此保证防捕获的结论。')

page('09  关键截图：同样内容的正反对照')
imagefile(OLDM/'baseline/capture/sck-screenshot-window.png','图1  baseline：独立SCScreenshotManager窗口截图可读到合成试题。原图1800×1264；此处裁去底部输入行，保留顶部公开区和全部选项。来源：上一轮matrix / baseline。',6.3,crop=(0,0,1800,1080))
imagefile(OLDM/'protected/capture/sck-screenshot-window.png','图2  protected：同接口、同窗口布局，公开控件仍可见，考试画布为黑色。来源：上一轮matrix / protected。图像不能单独证明物理显示正常；物理显示另有用户确认。',6.3,crop=(0,0,1800,1080))

page('10  关键截图：原生控件可绕出保护面')
imagefile(OLDM/'mixed/capture/sck-screenshot-window.png','图3  mixed：黄色NATIVE-LEAK控件是普通NSTextField，外部截图仍可读；背后的考试画布为黑色。原始独立SCK窗口截图，未叠加报告中的“示意黑块”。',6.4)
table(['观察','产品含义'],[
 ('六条单帧入口可读原生标记；显示器流22/22帧可读','只保护视频Layer不足以保护全部敏感UI。'),
 ('普通工具栏、原生提示仍存在','工具栏只能放非敏感信息；题干、答案、输入回显及提示应统一审计。'),
 ('窗口流此配置整窗透明','某一条路径更强的遮蔽结果不能替其它路径背书。')],[6.3,11.1],9.5)
ptext('原生输入框、tooltip、菜单、独立弹窗和输入法候选框属于同类审阅重点。正式产品要么将必要视觉元素合成到受保护帧，要么通过有文档支持的考试会话能力限制系统行为，并逐项验证。')

page('11  自身录像与系统回采必须区分')
imagefile(next((OLDM/'protected').glob('*.decoded.png')),'图4  自身MP4实际解码帧。来源：上一轮protected自录，约第1秒。它证明编码器保存了应用原始考试画布，不是系统截图，也不是对外部捕获的豁免。',6.1)
selfcase=DEEP/'extended-protected'
if (selfcase/'self-sck-window.png').exists():
    imagefile(selfcase/'self-sck-window.png','图5  本轮同进程SCK窗口回采。调用者就是考试进程，使用currentProcess来源；应与图4原始帧录像分别解读。仅裁去底部黑色区域；结果与有效性见下一页。',6.1,crop=(0,0,1800,900))
else:
    ptext('本轮同进程SCK未生成有效图片，不能据此判为保护通过；错误/跳过状态保存在self-capture.json。')
note('录像覆盖900×500 point考试画布，不含普通工具栏、桌面遮挡、系统光标、IME浮层及声音。生产录像需要定义明确的内容和审计范围。')
# Deep experiment result pages are generated from actual completed observations.
exec((ROOT/'scripts/review_report/report_deep_results.py').read_text(),globals())
exec((ROOT/'scripts/review_report/report_clearkey.py').read_text(),globals())

page('20  系统级路线为何不能直接替代改造')
h2('没有发现通用窗口捕获授权回调')
ptext('本次公开文档和SDK检索未找到类似AUTH_SCREEN_CAPTURE(window,capturer)的第三方策略接口。WindowServer / Quartz Compositor承担系统窗口合成；SCK向捕获客户端交付表面/帧。Apple没有公开完整内部调用链或可安装第三方窗口保护插件的契约，不能从模块名字或系统进程权限推导扩展能力。')
table(['技术','授权/部署','本需求缺口'],[
 ('System Extension','宿主需system-extension.install；扩展还需对应能力、签名、激活与批准。','安装机制不等于拥有合成器访问或捕获拦截权限。'),
 ('Endpoint Security','endpoint-security.client需Apple批准，另有FDA等运行条件。','Screen Sharing attach/detach为notify，不覆盖每次截图；限制进程运行也不是逐窗口授权。'),
 ('DriverKit','driverkit及family/transport等entitlement；对应驱动支持范围。','未找到WindowServer捕获策略driver family；虚拟显示器不自动覆盖全部窗口/系统路径。'),
 ('Kext','签名、用户批准、AuxKC及重启；Apple Silicon有启动安全要求。','没有稳定的捕获语义接口；root/Kext不等于任意改写受保护系统进程。'),
 ('私有SkyLight/注入','无公开稳定ABI，受系统完整性、签名与运行环境制约。','只能列为隔离研究假说；本次未实现，不能对正常分发产品作覆盖保证。')],[3.6,6.8,7],9)
ptext('受管机房可将应用白名单、MDM配置和考试会话限制作为分层措施，但应准确说明它们限制的是可运行环境。对于允许的浏览器、已有进程和系统捕获入口，仍不能用进程名单替代窗口内容保护。[R20–R23]')
note('报告中的“不可行”限定为单独依赖该技术、按公开支持契约完成要求；并不否认Apple内部媒体保护或考试会话拥有更强控制。')

page('21  产品化改造、性能与质量边界')
h2('从可用画布到真实考试引擎')
table(['模块','必须补齐的工作','验收重点'],[
 ('题目/答案呈现','统一文字、图片、公式、选区、滚动与焦点状态；禁止普通控件先暴露明文。','首帧、切题、弹窗和异常时不出现未受保护内容。'),
 ('输入与IME','实现文本编辑模型、NSTextInputClient或等价方案，处理组合文本、候选与定位。','中文输入、光标、退格、复制粘贴和跨行选择；PoC仅ASCII。'),
 ('无障碍','定义可访问语义、VoiceOver、缩放、辅助输入及考试便利措施。','像素保护与获授权辅助进程可读语义的边界需产品批准。'),
 ('录像审计','定义题目、答案、焦点、必要鼠标、时间戳、声音范围；保护输出文件。','录像既可播放，又真实反映需要审计的状态；原始帧不是完整桌面录像。'),
 ('生命周期','renderer失败、切屏、休眠、最小化、窗口重建、热插拔与不同scale恢复。','故障时先隐藏题目再恢复；属性回读不足以允许考试继续。'),
 ('分发与运维','Developer ID、Hardened Runtime、公证、沙盒保存目录、首次TCC与更新流程。','签名与公证不会提升捕获策略；明确受支持OS/设备清单。')],[3.2,7.1,7.1],9)
ptext('默认1800×1000 BGRA每帧约7.2MB，20fps理论像素写入约144MB/s；3600×2000每帧约28.8MB。它们只是像素数据量，不含池、编码器、GPU及系统合成成本。CPU提交时间和ps点采样不能当作端到端延迟或真实呈现帧率。')
ptext('文字清晰度应按原生backingScale绘制，再分别测试编码后的细字体、低对比文字、公式和缩放。本报告的代表帧能读取合成试题，但没有完成视觉质量评分、全视频逐帧解码或长时功耗认证。')

page('22  分级结论与后续决策')
table(['分级','路线','评审建议'],[
 ('可直接实现局部能力','受保护视频Layer；原始帧编码；独立捕获验证工具。','可以继续工程原型；测试范围内有效，不是整客户端完成。'),
 ('需要架构改造','整个考试UI转为受保护显示面；Clear Key视频化方案。','优先选择无需编码/加密/分片的SampleBuffer显示主线；Clear Key保留媒体场景候选。'),
 ('需要Apple支持','AAC资格与部署验证；FPS生产凭据；未公开的更强系统策略。','提交准确业务与自录需求；获批后做真实会话测试，不用ad-hoc加plist模拟资格。'),
 ('单独无法满足完整目标','.none、HDCP、Metal private、IOSurface、SCK过滤器、ES/DriverKit。','可做兼容、性能或环境控制辅助，不能取代完整保护策略。')],[3.7,6.6,7.1],9.5)
h2('建议的三个工程门槛')
ptext('门槛A：在真实考试引擎验证统一渲染，覆盖至少中文输入、图片/公式、切题与弹窗，并证明没有普通敏感控件漏出保护面。门槛B：对每个支持OS/设备执行发布矩阵，保存有效阳性对照、连续样本及异常恢复结果。门槛C：录像审计范围、无障碍策略、受管环境与日志/文件保护由产品和安全评审共同确认。')
h2('提交Apple的具体问题')
ptext('1. preventsCapture在不同捕获入口遮蔽粒度不同是否为预期行为？2. Clear Key false时VideoOutput仍取得明文的本机结果如何解释、是否有受支持限制条件？3. AAC默认限制下原始帧编码与辅助监考应用的受支持边界是什么？4. 能否明确公开API在外接显示、虚拟显示和故障恢复时的支持范围？')
note('以上是待提交的问题清单。本轮没有向Apple或任何第三方发送报告、申请entitlement或提交Feedback。')

page('23  复现、证据索引与审计方法')
ptext('本轮工作目录为“深度调研_20261101”。旧目录保留上一轮报告与证据。Word报告中的截图已嵌入，离开本地工作区仍可审阅；复现和逐帧复核需要对应源码及artifacts目录。')
table(['证据组','目录/文件','用途'],[
 ('A 上一轮','父目录 artifacts/matrix-20261101T082724Z；filter-update-*；interactive-validation','五模式、更新重建、人工确认及输入/录像证据。'),
 ('B 本轮渲染测试',DEEP.name,'扩展入口、同进程回采、动态阶段、窗口生命周期、资源点采样。'),
 ('C ClearKey主实验','artifacts/clearkey-20261101T085500Z','明文false、加密false、加密true；截图/流/VideoOutput。'),
 ('D ClearKey顺序控制','artifacts/clearkey-order-20261101T090226Z','先设置false再挂接输出，以及不挂接输出。'),
 ('E 官方/工具资料','research/deep-review-20261101；research/clearkey','文档快照、SDK摘录、媒体生成命令、Bento4 commit与哈希。'),
 ('F 审计与修复','docs/证据审计.md；实验设计独立审阅.md；research/evidence-audit','检查口径、局限、JSON非finite修复及自测。')],[3.2,7.1,7.1],8.8)
h2('最小复现命令')
for line in ['bash scripts/build-demo.sh','bash scripts/build-probe.sh','python3 scripts/run-deep-tests.py','python3 scripts/analyze-deep-tests.py artifacts/deep-matrix-实际时间戳']:
    ptext(line,9.5)
ptext('Clear Key另使用build-clearkey-demo.sh、prepare-clearkey-media.py、run-clearkey-matrix.py与顺序控制脚本；媒体服务只绑定127.0.0.1。测试key和明文录像用于合成内容复核，不能照搬为生产DRM密钥管理。')
note('源码、工具和媒体证据保留哈希。原文档保留清单在research/previous-delivery-preservation.json；旧源码恢复已与上一轮交付manifest核对一致。')

page('24  发布验收矩阵与未验证项')
table(['维度','本次覆盖','发布前必须补测'],[
 ('系统/硬件','单台M4、macOS26.6.2、内置Retina','最低支持版本、Intel/不同Apple芯片、每次系统更新。'),
 ('捕获入口','多种公共API、系统CLI截图和录屏','Cmd-Shift交互入口、QuickTime、OBS、会议软件、浏览器具体版本。'),
 ('显示路径','内屏、固定窗口尺寸；部分hide/minimize','外屏、HDCP链、镜像/扩展、AirPlay、Sidecar、虚拟显示器。'),
 ('生命周期','指定时间表切保护/共享状态和隐藏恢复','启动前已录制、并发捕获者、Spaces/全屏、锁屏/休眠、热插拔、崩溃。'),
 ('时间覆盖','约10fps的已保存流样本；相邻帧统计','更高采样与端到端时序，排除短于采样间隔的泄漏；多小时稳定性。'),
 ('实际UI','合成题干/选项/ASCII/一个原生overlay','真实Web/富文本/公式/视频、中文IME、候选、菜单、弹窗、多窗口。'),
 ('录像','原始帧MP4、系统短MOV代表帧','整段内容一致性、音频/同步、磁盘满、加密保存、长时中断恢复。'),
 ('AAC / FPS','官方核验；AAC示例仅静态检查','Apple批准后实际session/许可证、失败/中断/退出、自录兼容。'),
 ('权限与部署','现有TCC、本地ad-hoc签名','新用户、沙盒、DeveloperID/公证、MDM、升级后的权限归属。'),
 ('辅助功能/安全范围','公开边界分析','VoiceOver/AX、便利措施、原始帧与录像副本保护，明确不覆盖的对手。')],[3,6.3,8.1],9)
ptext('验收不以“没有截图文件”为通过。每一条路径必须先有可读baseline、正常显示和正确权限，再检查有效输出。任何不确定状态应记录为未验证或无效样本；新增系统/显示配置不能借用相邻格子的结果。')
note('这些样本高度相关，不能把“零检出/总帧数”解释为统计置信度、逃逸概率或产品安全等级。')

references=[
 ('R01','AVSampleBufferDisplayLayer.preventsCapture','https://developer.apple.com/documentation/avfoundation/avsamplebufferdisplaylayer/preventscapture','显示Layer捕获保护；最低macOS10.15。'),
 ('R02','AVSampleBufferDisplayLayer.sampleBufferRenderer','https://developer.apple.com/documentation/avfoundation/avsamplebufferdisplaylayer/samplebufferrenderer','macOS14起渲染入队对象；旧enqueue弃用见SDK。'),
 ('R03','AVAssetWriter','https://developer.apple.com/documentation/avfoundation/avassetwriter','应用提供媒体样本的编码写文件路径。'),
 ('R04','NSWindow.SharingType.none','https://developer.apple.com/documentation/appkit/nswindow/sharingtype-swift.enum/none','现行legacy说明与防捕获限制；不能外推旧契约。'),
 ('R05','AVPlayer.allowsCaptureOfClearKeyVideo','https://developer.apple.com/documentation/avfoundation/avplayer/allowscaptureofclearkeyvideo','macOS26.4、默认false，明确涉及VideoOutput/SCK；与本机现象对照。'),
 ('R06','AVPlayer外部保护不足状态','https://developer.apple.com/documentation/avfoundation/avplayer/isoutputobscuredduetoinsufficientexternalprotection','只读状态；不是全局录屏检测。'),
 ('R07','DisplayLayer外部保护不足状态','https://developer.apple.com/documentation/avfoundation/avsamplebufferdisplaylayer/isoutputobscuredduetoinsufficientexternalprotection','只读状态及相关通知。'),
 ('R08','Capturing screen content in macOS','https://developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos','SCK过滤、配置、样本处理与WindowServer资源相关说明。'),
 ('R09','SCScreenshotManager','https://developer.apple.com/documentation/screencapturekit/scscreenshotmanager','单帧捕获入口；矩形入口版本另由SDK核对。'),
 ('R10','SCShareableContent.currentProcess','https://developer.apple.com/documentation/screencapturekit/scshareablecontent/currentprocess','当前进程内容范围与TCC语义。'),
 ('R11','CGWindowListCreateImage','https://developer.apple.com/documentation/coregraphics/cgwindowlistcreateimage','历史窗口截图，14弃用、15废止由SDK核对。'),
 ('R12','CGDisplayCreateImage','https://developer.apple.com/documentation/coregraphics/cgdisplaycreateimage','历史显示器截图，14.4弃用、15废止由SDK核对。'),
 ('R13','AutomaticAssessmentConfiguration','https://developer.apple.com/documentation/automaticassessmentconfiguration','官方考试会话、资源限制与生命周期。'),
 ('R14','Automatic Assessment Configuration entitlement','https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.automatic-assessment-configuration','受限entitlement申请与部署要求。'),
 ('R15','AEAssessmentConfiguration.allowsScreenshots','https://developer.apple.com/documentation/automaticassessmentconfiguration/aeassessmentconfiguration/allowsscreenshots','macOS26.1剪贴板截图例外；辅助配置见同框架。'),
 ('R16','FairPlay Streaming','https://developer.apple.com/streaming/fps/','生产资格、SDK与受保护媒体体系。'),
 ('R17','HLS Authoring Specification for Apple Devices','https://developer.apple.com/streaming/hls-authoring-specification-for-apple-devices.html','SAMPLE-AES、输出保护与HDCP媒体要求。'),
 ('R18','IOSurface','https://developer.apple.com/documentation/iosurface','图像表面共享；并非普通UI防捕获策略。'),
 ('R19','Setting resource storage modes','https://developer.apple.com/documentation/metal/setting-resource-storage-modes','Metal存储模式与CPU/GPU访问语义。'),
 ('R20','System Extensions','https://developer.apple.com/system-extensions/','受支持扩展范围与安装机制。'),
 ('R21','DriverKit','https://developer.apple.com/documentation/driverkit','受支持驱动能力、家族与部署。'),
 ('R22','Endpoint Security event types','https://developer.apple.com/documentation/endpointsecurity/es_event_type_t','事件与授权/通知分类；版本另核对SDK。'),
 ('R23','Securely extending the kernel in macOS','https://support.apple.com/guide/security/securely-extending-the-kernel-in-macos-sec8e454101b/web','Kext/AuxKC/Apple Silicon启动安全边界。'),
 ('R24','Technical Note TN2454: Debugging FairPlay Streaming','https://developer.apple.com/library/archive/technotes/tn2454/','identity + SAMPLE-AES + 匹配key/IV的测试方法；归档资料。'),
 ('R25','Using content protection systems with HLS','https://developer.apple.com/documentation/http-live-streaming/using-content-protection-systems-with-hls','key format、URI和内容保护系统的当前说明。'),
 ('R26','Bento4 mp42hls','https://www.bento4.com/documentation/mp42hls/','本轮媒体生成工具的第一方文档；工具commit和源码另归档。'),
 ('R27','Apple Developer Forums 808016','https://developer.apple.com/forums/thread/808016','SCK过滤更新行为报告与DTS调查回应；不是稳定行为承诺。')]
for start,end in [(0,14),(14,len(references))]:
    page('参考文献与可核查依据'+('（一）' if start==0 else '（二）'),'访问/核对日期：2026-11-01。蓝色标题可点击；所有版本同时核对本机SDK。')
    for code,title,url,desc in references[start:end]:
        p=D.add_paragraph();font(p.add_run(code+'  '),9.5,bold=True,color=INK);link(p,title,url)
        p.paragraph_format.space_after=Pt(1)
        ptext(desc,9,color=GRAY)
    if start>0:
        h2('材料优先级与引用边界')
        ptext('规范性描述优先采用当前Apple文档和SDK；Apple论坛中的发帖人观察与DTS回应分开，不等同API承诺。归档TN/FPS资料用于解释媒体格式和测试，不用于推断2026年macOS内部实现。Bento4文档只支持工具行为，不替代Apple平台的捕获保证。',9.5)
        ptext('完整官方快照与URL清单见本轮research/deep-review-20261101及旧目录research/api、research/system。若文档日后更新，应按本报告记录的访问日期和快照重审相关结论。',9.5)
