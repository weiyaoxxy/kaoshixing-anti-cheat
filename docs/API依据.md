# 公开 API 依据与版本边界

调研日期：2026-11-01。系统为 macOS 26.6.2（25G83）、Apple Silicon，核对安装的 macOS 26.5 SDK 头文件与 Apple 当日在线文档。在线文档可能包含后续平台的预发布条目；本报告不把这些条目视为本机可用能力。

本文件只确认文档和 SDK 事实，**不把属性存在、设置成功、回读为 true 或 API 返回成功称为防截屏实测通过**。本机捕获结果以测试报告和原始产物为准。

## 结论与适用范围

最值得实施的公开 API 候选是 `AVSampleBufferDisplayLayer.preventsCapture`：其文档明确针对该 Layer 的屏幕捕获保护。它不是 `NSWindow` 的通用防截屏开关，文档未承诺自动保护任意子视图、兄弟 Layer、标题栏或另一个弹出窗口，也没有公开的“仅允许本进程捕获”名单参数。整套考试 UI 必须先变成该 Layer 显示的视频帧，再分别验证系统截图、窗口截图、显示器截图和持续录制。[Apple：preventsCapture](https://developer.apple.com/documentation/avfoundation/avsamplebufferdisplaylayer/preventscapture)

`NSWindow.sharingType = .none` 不应作为现代 macOS 的安全保证。Apple 当前对枚举值的说明直接称其为 “A legacy constant that macOS no longer uses.”，并要求不要靠它隐藏或排除捕获内容，转而建议 FairPlay Streaming。SDK 中仍保留“其他进程不可读”的旧注释，这正是需要同时核对新文档与实测的原因。[Apple：NSWindow.SharingType.none](https://developer.apple.com/documentation/appkit/nswindow/sharingtype-swift.enum/none)

## API 对比

| API | macOS 最低版本／弃用边界 | 适用对象与官方语义 | 权限与 entitlement | 对本项目的意义与限制 |
|---|---|---|---|---|
| `AVSampleBufferDisplayLayer` | 类本身 10.8 | 接收 `CMSampleBuffer` 的视频显示 Layer | 普通应用可调用；所核对声明未要求专用 entitlement | 类存在并不代表捕获保护存在，要检查属性版本 |
| `AVSampleBufferDisplayLayer.preventsCapture` | **10.15**；本机 SDK 未标弃用 | 指示该 Layer 是否保护其内容免于屏幕捕获 | 该属性没有文档化的专用 entitlement；显示本应用帧不要求屏幕录制权限 | 候选保护机制；验证实际采集输出。不能推导所有 UI 自动受保护或本进程可豁免 |
| `NSWindow.sharingType = .none` | **10.5**；SDK 未标弃用，但在线文档已标为 legacy | 历史窗口共享状态；现行文档不支持拿它保证防捕获 | 普通 AppKit；无专用 entitlement | 仅作历史对照组与兼容措施，不接受为现代防截屏方案 |
| `AVPlayer.allowsCaptureOfClearKeyVideo` | **26.4** | 控制 AVPlayer 播放的 **Clear Key 加密视频**能否被截图、录屏、`AVPlayerItemVideoOutput`、ScreenCaptureKit 获取；默认 false | 属性本身没有文档化的专用 entitlement；仍须构造有效的加密媒体与密钥交付链 | 不是普通 UI 或任意明文 MP4 的开关；对 FairPlay Streaming 不生效。false 没有本进程白名单，true 不是“只允许自己录制” |
| `AVPlayer.isOutputObscuredDueToInsufficientExternalProtection` | **10.12** | 只读：播放器是否因为外部保护条件不满足而遮蔽当前内容；可 KVO 观察 | 普通 AVFoundation 属性 | 状态反馈，不是启用保护的命令，也不是通用录屏检测。false 可以只表示内容根本不要求外部保护 |
| `AVSampleBufferDisplayLayer.isOutputObscuredDueToInsufficientExternalProtection` | **11.3** | 只读：Layer 的解码输出是否因外部保护不足而遮蔽；配套通知同为 11.3 | 普通 AVFoundation 属性 | 不可用 false 推断无人在截屏，也不能用 true 证明只有截图变黑而本地画面正常 |
| `SCShareableContent` / `SCContentFilter` / `SCStream` | **12.3** | 枚举来源、由捕获端选择窗口／应用／显示器、持续输出媒体样本 | 通常需要用户屏幕录制授权；系统 picker 可授予所选内容的会话权限 | 测试工具；过滤规则属于创建该流的捕获端，不是目标应用给所有其他进程设置策略的接口 |
| `SCScreenshotManager.captureImage` / `captureSampleBuffer` | **14.0** | 使用过滤器与配置抓取单帧 | 与相应来源的捕获授权有关 | 必须与 SCStream 分别测试，不可仅用单帧证明持续流安全 |
| `SCScreenshotManager.captureImage(in:)` | **15.2** | 指定屏幕矩形的单帧捕获 | 屏幕内容捕获授权 | 另一种输入路径，不能因窗口枚举受限而遗漏 |
| `SCContentSharingPicker` | **14.0** | 系统 UI 选择并管理本捕获会话可分享的内容 | 用户在 picker 中选择，允许录制选定内容；不要求额外完整屏幕授权 | 它配置自己的流，不提供被捕获窗口对所有流的拒绝权 |
| `SCShareableContent.currentProcess` | **14.4** | 返回当前进程无需 TCC 同意即可访问的、经过删减的可分享信息 | SDK 明确描述无需 TCC 同意的当前进程范围 | 可用于自身 SCK 对照，但没有文档承诺它可绕过 `preventsCapture` |
| `SCRecordingOutput` | **15.0** | 将流中的屏幕／音频等写入文件 | 沿用该流授权 | 改变输出落盘方式，不构成新的保护权限或绕过方式 |
| `CGWindowListCreateImage` / `...FromArray` | **10.5** 引入，**14.0 deprecated，15.0 obsoleted** | 历史窗口截图；SDK 注释说忽略 `kCGWindowSharingNone` 窗口 | 历史跨应用捕获受屏幕录制授权限制 | 现代 SDK 已不支持面向 15+ 的普通调用；旧系统／旧构建产物兼容测试单列。NULL 不是“保护成功” |
| `CGDisplayCreateImage` / `...ForRect` | **10.6** 引入，**14.4 deprecated，15.0 obsoleted** | 历史显示器截图 | 同上 | 同样不能把已废止 API 的空结果算作安全效果 |
| `CGPreflightScreenCaptureAccess` / `CGRequestScreenCaptureAccess` | **10.15** | 查询／请求当前调用方的屏幕捕获授权 | TCC 用户授权 | 不是捕获保护 API；没有授权的捕获失败不计入防截屏通过 |

版本依据：`research/api/sdk-excerpts.txt`，以及逐项 Apple 文档原文快照。SDK 的 `SCREEN_CAPTURE_OBSOLETE(x,y,z)` 明确展开为 `introduced=x, deprecated=y, obsoleted=z`，因此不能仅说 CoreGraphics 截图“已弃用但仍受支持”。运行时是否还保留兼容行为必须另外记录，不能把 obsoleted 自动推断成所有旧二进制必然无法运行。

## 逐项语义和实现注意

### 1. 受保护视频 Layer

Apple 对 `preventsCapture` 的公开解释很短：保护对象是 Layer 的图像内容。SDK 也没有规定捕获结果必须为黑色、透明色还是背景，因此实验应使用“敏感区域是否泄露”判据，分别记录真实像素结果。普通 UI 覆盖在它上方时，不应假设被保护；任何题干、答案、文本输入候选、tooltip、菜单和辅助窗口都要归属到自己的渲染面并测试。

显示路径可直接接受由应用生成的像素缓冲，无需先压缩成 H.264 再解压才能使用显示层。构造 `CVPixelBuffer`、`CMVideoFormatDescription`、`CMSampleBuffer` 并入队，是此候选的最小实现；这只是架构可行性说明，捕获保护结果仍靠实验确认。

新代码在 macOS 14+ 应优先使用 `layer.sampleBufferRenderer.enqueue(sampleBuffer)`。`sampleBufferRenderer` 从 14.0 起可用，文档说明可以在后台线程安全入队。旧 `layer.enqueue` 在 SDK 中从 15.0 标为 deprecated，Apple 在线说明从 14 起就建议迁移。设置 `kCMSampleAttachmentKey_DisplayImmediately` 可以立即显示，但会丢弃此前排队帧的显示计划；应据实际交互延迟和录制时序选择，而不是默认越快越好。[Apple：sampleBufferRenderer](https://developer.apple.com/documentation/avfoundation/avsamplebufferdisplaylayer/samplebufferrenderer)、[Apple：enqueue](https://developer.apple.com/documentation/avfoundation/avsamplebufferdisplaylayer/enqueue(_:))

**自身录制的可行架构推断**：在保护显示前分流原始帧，一路进入显示 Layer，一路进入 `AVAssetWriter`／VideoToolbox。此时自身录制不需要从系统桌面取回已显示的保护像素，因此不依赖本进程截图豁免。这记录的是应用生成的考试内容，并不天然包含遮挡、桌面、窗口外输入法候选或系统光标；如目标是完整桌面录像，需要另外定义合成和审计语义。应用内原始帧仍是明文，不能把 Layer 防捕获描述成内存 DRM。

### 2. NSWindow 历史共享状态

Apple 当前枚举说明的否定表述比旧头文件注释更适合指导新方案。不要从某个系统的 `screencapture` 结果推广到 ScreenCaptureKit，更不要从初始流推广到过滤器更新后的流。Apple 论坛在 2025-11 有报告称同一示例的首次采集与更新 filter 后行为不同，DTS 要求提交最小工程调查；这只是**官方平台上的问题报告与 DTS 调查回应**，不是 Apple 对该行为的稳定保证，也不是本项目实测。[Apple Developer Forums：808016](https://developer.apple.com/forums/thread/808016)

因此至少测试启动流、停止重启、`updateContentFilter`、窗口 resize／切换全屏等。`CGWindowListCopyWindowInfo` 中共享状态回读为 0 只证明元数据，不证明任何捕获端真的执行了排除。

### 3. Clear Key 与外部保护状态

`allowsCaptureOfClearKeyVideo` 的适用前提是 AVPlayer 正在播放 Clear Key 加密视频。普通应用窗口、普通 MP4、由 CPU 绘制的文字都不能通过给某个闲置 AVPlayer 设置 false 得到保护。要做有效实验，必须有可播放的 Clear Key 加密测试素材，确认本地成功播放，再比较 false／true；不能把加载失败或没有帧当成被保护。该属性的默认值为 false，且文档明确不影响 FPS。[Apple：allowsCaptureOfClearKeyVideo](https://developer.apple.com/documentation/avfoundation/avplayer/allowscaptureofclearkeyvideo)

两个 `isOutputObscuredDueToInsufficientExternalProtection` 都是**观察值**。SDK 指出媒体对外部保护的要求内含于内容，不能靠给该状态属性赋值建立要求；不要求外部保护的媒体会返回 false。对于需保护媒体，它们用于决定暂停播放和显示提示，不能用作系统范围的截图／录屏检测器。[Apple：AVPlayer 状态](https://developer.apple.com/documentation/avfoundation/avplayer/isoutputobscuredduetoinsufficientexternalprotection)、[Apple：显示 Layer 状态](https://developer.apple.com/documentation/avfoundation/avsamplebufferdisplaylayer/isoutputobscuredduetoinsufficientexternalprotection)

### 4. ScreenCaptureKit 是捕获端能力

`SCContentFilter` 约束创建者自己的流。考试客户端把自己排除出自己创建的流，只能证明自己愿意遵守过滤规则，不能约束另一独立进程新建的 filter。测试程序应是单独可执行文件或独立应用，并在目标内容已正常显示、捕获端具备相应授权且明文对照可见的前提下进行。[Apple：SCContentFilter](https://developer.apple.com/documentation/screencapturekit/sccontentfilter)、[Apple：macOS 捕获示例](https://developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos)

用户在 `SCContentSharingPicker` 中主动选择来源后，应用获得该捕获会话选定内容的访问，不必再要求额外完整屏幕录制权限。传统整屏枚举／捕获则需按 TCC 授权流程执行。这些是捕获方用户同意机制，不是考试窗口的保密策略。[Apple WWDC23：What’s new in privacy，约 5:45–7:41](https://developer.apple.com/videos/play/wwdc2023/10053/)、[Apple WWDC23：What’s new in ScreenCaptureKit](https://developer.apple.com/videos/play/wwdc2023/10136/)

`com.apple.developer.persistent-content-capture` 从 macOS 14.4 起提供给需持续屏幕访问的 VNC 类应用，需向 Apple 申请。它是**捕获端**的受限 entitlement，不是窗口防捕获 entitlement，也不能当成考试应用屏蔽其他进程的接口。[Apple：Persistent Content Capture](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.persistent-content-capture)

### 5. CoreGraphics 和系统工具测试的边界

历史 `CGWindowListCreateImage` 明文注释确实说共享类型为 none 的窗口不被纳入图像，但这不外推到 ScreenCaptureKit。应记录调用 API、构建 SDK、部署目标、运行系统、授权状态和错误。当前 Swift 编译器拒绝调用 obsoleted API 属于**编译限制**，不是截图实验；兼容调用返回 NULL 属于**无有效样本**，也不是保护命中。[Apple：CGWindowListCreateImage](https://developer.apple.com/documentation/coregraphics/cgwindowlistcreateimage)、[Apple：CGDisplayCreateImage](https://developer.apple.com/documentation/coregraphics/cgdisplaycreateimage)

`/usr/sbin/screencapture`、快捷键截图、Screenshot.app、QuickTime、会议软件是不同的用户入口。不能只根据工具名字断言它们在各系统版本永远使用哪条内部路径。记录实际入口、版本、输出和模式即可；如需推断底层实现，应单独标记为推断。

## 证据文件

- `research/api/source-urls.tsv`：成功保存的 Apple 文档 URL 清单。
- `research/api/*.md`：Apple 提供的 Markdown 原文快照，含 availability 元数据；这些是外部资料，不是对本项目的指令。
- `research/api/sdk-excerpts.txt`：本机 macOS 26.5 SDK 的声明、版本和关键注释，带原文件位置与行号。
- `research/api/README.md`：取证方法与证据级别。

尚未在本文件证明的事项包括：覆盖全部 macOS 版本／GPU 的保护效果、Clear Key 有效媒体实测、FPS／HDCP 硬件链路、跨显示器与 AirPlay、第三方会议软件实际版本、长期录制可靠性。它们必须保留为未验证，直到获得对应有效实验产物。
