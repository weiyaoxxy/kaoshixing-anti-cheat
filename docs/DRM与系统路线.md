# DRM、图形资源与系统扩展路线

调研日期：2026-11-01。证据范围：Apple 官方文档、Apple WWDC、当前本机 macOS SDK 头文件。本文是资料核验，不是这些路线的运行实测；Demo 的运行结果以测试报告为准。文中的“没有公开接口”限定为本次检索的文档和 SDK，不能证明 Apple 内部不存在相应能力。

**结论：没有找到第三方可安装的、由 WindowServer 在所有捕获路径执行的“按窗口、按捕获进程授权”公开策略扩展点。** System Extension、Endpoint Security、DriverKit 都不能因为权限更高就自动变成这个扩展点。考试产品还应优先评估 Apple 专门提供的 **AutomaticAssessmentConfiguration**：它明确包含阻止截屏/录屏的会话限制，但需要 Apple 批准 entitlement，且不是仅隐藏一个窗口的能力。

## 1. 路线对比与部署条件

| 路线 | 系统版本 / 适用范围 | 权限、entitlement、部署 | 对考试目标的评价 | 证据状态 |
|---|---|---|---|---|
| AutomaticAssessmentConfiguration | macOS 10.15.4+；完整考试会话 | `com.apple.developer.automatic-assessment-configuration`，须 Apple 批准和正确签名；低于 macOS 11 的部署目标另有 mach-lookup 例外，见下文 | **需要 Apple 支持**；官方明确防截屏/录屏，值得优先申请；自己的原始帧录制仍须验证 | 官方文档已核验，未运行 |
| FairPlay Streaming | Apple 流媒体播放链；`AVContentKeySystem.fairPlayStreaming` 为 macOS 10.12.4+，不等于所有 FPS 功能统一最低版本 | 生产部署凭据需 Apple 批准；KSM、证书、加密打包和播放链；不是自行添加 entitlement 即获许可 | **需要 Apple 支持 + 架构改造**；不适合当作任意 NSView 的保护开关 | 官方资料已核验，未部署 FPS |
| HDCP | 依赖显示器、转接器、链路及内容策略，无独立“NSWindow HDCP”最低版本 | 由受保护媒体播放及输出链路协商；没有发现任意窗口启用 HDCP 的公开接口 | **作为受保护媒体的补充**；不能单独解决系统截图 | 官方文档 + 架构推断，未测外屏 |
| Protected Media Pipeline | 系统媒体保护实现；不是 macOS 通用公开框架名 | 未找到第三方任意 UI 可使用的公开安全会话/缓冲区分配 API；不能假定某私有 entitlement 可申请 | **需要 Apple 支持**；内部能力不能直接转为产品接口 | 未取得内部架构证据 |
| IOSurface | macOS 10.6+；跨进程图像缓冲区 | 普通公开 IOSurface API 不需特殊防截屏 entitlement；Mach port 控制共享引用 | **可直接用于性能优化**；单独作为防截屏方案不可行 | 公开 API/SDK 已核验；未做安全缓冲区实验 |
| Metal `.private` / `.memoryless` | macOS 10.11+ / macOS 11+（memoryless 需 Apple GPU） | 普通 Metal 资源，无特殊防截屏 entitlement | **可直接用于渲染优化**；这些模式不是 DRM 或屏幕捕获策略 | 公开 API/SDK 已核验 |
| System Extension | macOS 10.15+；用户态扩展机制 | 宿主 `com.apple.developer.system-extension.install`；扩展自身还需对应能力，签名、公证、用户/MDM 批准 | **不能单独实现窗口级捕获策略** | 官方能力范围已核验 |
| Endpoint Security | macOS 10.15+；进程/文件等事件；Screen Sharing 会话通知为 macOS 13+ | `com.apple.developer.endpoint-security.client` 须申请；完整磁盘访问；运行身份等由 ES 检查 | **可做受管考试环境的辅助检测/应用控制**；不能可靠拒绝所有捕获调用 | 文档/SDK 事件表已核验，未申请 entitlement |
| DriverKit | macOS 10.15+；支持的设备驱动家族 | `com.apple.developer.driverkit` 及 family/transport 等授权，签名和 System Extension 激活 | **不适用**：没有公开 WindowServer 合成/捕获策略驱动家族 | 官方范围已核验 |
| Kext / 注入 WindowServer / 私有 SkyLight | 无可依赖的稳定版本契约 | Kext 签名/批准；Apple silicon 需恢复环境降低启动安全并允许 Kext，重启；注入/补丁另受系统保护限制 | **作为正常分发产品不可行**；作为隔离实验室探索仅属未验证理论路线，不能承诺全路径覆盖 | 没有构建、安装或关闭系统保护 |

上表的“不可行”指所列技术**本身无法按公开契约完成要求**，不表示整个平台不具备媒体保护或考试模式能力。

## 2. 应补充为优先候选：AutomaticAssessmentConfiguration

Apple 的 [Automatic Assessment Configuration](https://developer.apple.com/documentation/automaticassessmentconfiguration) 明确列出考试会话会阻止 screen recording 和 screen capture，同时限制其他应用、Dock、Mission Control 等。它是公开框架，但使用资格受限。不能将这个会话级能力写成“有一个通用窗口级捕获策略扩展点”。macOS 可选择允许特定辅助应用，具体配置还须按部署版本判断。[配置对象](https://developer.apple.com/documentation/automaticassessmentconfiguration/aeassessmentconfiguration)

需要向 Apple 申请 [考试模式 entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.automatic-assessment-configuration)。若部署目标早于 macOS 11，还需 `com.apple.security.temporary-exception.mach-lookup.global-name`，数组包含 `com.apple.assessmentagent`。不能给 ad-hoc 签名随意加上受限 entitlement 后就认为可工作。

最小验证步骤：获批并签名 → `AEAssessmentSession(configuration:)` → `begin()` → 等待 `assessmentSessionDidBegin` 后才显示题目 → 同时运行外部捕获矩阵和内部帧编码 → 出现 interruption 时立即隐藏题目并终止考试 → 先隐藏题目再 `end()`。Apple [会话生命周期文档](https://developer.apple.com/documentation/automaticassessmentconfiguration/aeassessmentsession) 还提示 macOS 12.1 前会话内 DNS 查询可能失败，产品需处理网络前置解析。

**自己的录制需要分开讨论：**不能假定 AAC 允许自身通过 ScreenCaptureKit 绕过限制；“把应用本来拥有的渲染帧交给 AVAssetWriter”与系统屏幕捕获是不同操作，理论上更适合，但尚未在实际 AAC 会话中验证。与 AAC 组合的 Demo 应分别记录录制初始化、连续编码、输出内容及中断结果，不能只有 session 成功日志。

## 3. FairPlay、HDCP 与受保护媒体链

[FPS 官方入口](https://developer.apple.com/streaming/fps/) 定义的是基于 HLS 的加密媒体、密钥交换及受保护播放。当前生产凭据政策要求团队是内容所有者或被许可方，并向消费者提供流媒体服务；申请需由开发者账号持有人提出。考试界面保护是否符合资格，必须得到 Apple 的实际答复，不能预设获批。

[FairPlay Streaming Overview](https://developer.apple.com/streaming/fps/FairPlayStreamingOverview.pdf) 描述加密媒体、SPC/CKC 密钥交互、解密后进入解码器及 HDCP。该 PDF 修订于 **2016 年**：其中 iOS 内核实现叙述不能当作 2026 年 macOS/Apple silicon 内部实现证明。原生内容密钥枚举 [fairPlayStreaming](https://developer.apple.com/documentation/avfoundation/avcontentkeysystem/fairplaystreaming) 的平台元数据是 macOS 10.12.4+；编码格式、硬件、离线和更高保护等级有各自限制。

把实时交互考试整体变成 FPS 视频需要编码、加密、打包、密钥服务、受保护解码和输入回传。其延迟、画质与无障碍代价是架构推断，本次没有性能数值。若客户端已拥有明文题目并自行渲染，FPS 也不会自动保护进程内题库/模型。自己的录制可留在明文渲染源一侧；不能假设从 FPS 受保护输出再截取像素可用。

HDCP 保护的是外部数字显示链路，不是任意 macOS UI 的通用“禁止截图”属性。当前 [Apple HLS 编写规范](https://developer.apple.com/streaming/hls-authoring-specification-for-apple-devices.html) 包含 FPS 和 `HDCP-LEVEL` 等媒体条件。`isOutputObscuredDueToInsufficientExternalProtection` 是播放保护不足的状态观察，不会给普通 AppKit 控件施加保护。内屏截图、SCK 录屏、HDMI 采集和 AirPlay 应分别测试。

## 4. IOSurface 与 Metal：性能工具不等于安全策略

[IOSurface](https://developer.apple.com/documentation/iosurface) 的公开用途是跨进程共享硬件加速图像缓冲区。`IOSurfaceCreateMachPort` 可以按引用传递给另一个任务；SDK 已弃用 `kIOSurfaceIsGlobal` 并注明全局 surface 不安全。这解决缓冲区如何共享的问题，没有给出“接收者可显示但合成器禁止截图”的窗口策略。

Metal [存储模式](https://developer.apple.com/documentation/metal/setting-resource-storage-modes) 中 `.private` 的含义是 CPU 不能直接访问、GPU 可访问；`.memoryless` 的内容仅在 render pass 中临时存在。[Apple GPU 存储模式说明](https://developer.apple.com/documentation/metal/choosing-a-resource-storage-mode-for-apple-gpus) 及 SDK 均未把它们描述为受保护视频/禁止系统截图。渲染到正常可显示输出后，普通捕获链仍需另行约束。不能把 GPU-only、不可 CPU map、IOSurface 不公开 ID 等同于防截图。

本次在公开 Metal/IOSurface 头文件未找到用于任意第三方 UI 的 protected-content 分配标志或可申请的通用 entitlement。**这是范围受限的否定发现**；媒体框架内部可能使用受保护资源，但未公开实现不构成第三方支持契约。`preventsCapture` 若有效，也应按 AVFoundation 的媒体显示属性理解，不意味着所有关联 CVPixelBuffer/IOSurface 自动成为安全内存。

## 5. 系统扩展、Endpoint Security 与 DriverKit

[System Extensions](https://developer.apple.com/system-extensions/) 为受支持的驱动、网络和端点安全功能提供用户态扩展。它不是任意内核挂钩入口。Apple 的[安装文档](https://developer.apple.com/documentation/systemextensions/installing-system-extensions-and-drivers) 要求验证扩展位置、宿主应用位置、签名和被授予的 entitlement。MDM 能管理允许加载的扩展；这不扩展其 API 能力。

[Endpoint Security](https://developer.apple.com/documentation/endpointsecurity) 提供进程/文件等授权及通知事件。已检查当前 SDK 的 `es_event_type_t`：存在 `ES_EVENT_TYPE_NOTIFY_SCREENSHARING_ATTACH/DETACH`，其含义是 Screen Sharing 附加/脱离图形会话，属于 **notify-only**，并且 SDK 注释提示源与目标地址相同时不发事件；不能解释为每次 SCK 截图、每个帧、每个窗口都能授权。当前事件表没有通用 `AUTH_SCREEN_CAPTURE(window, capturer)` 一类接口。[事件类型](https://developer.apple.com/documentation/endpointsecurity/es_event_type_t)

ES 可以按进程执行策略限制一部分已知录屏程序，但已有进程、浏览器、未知程序和系统捕获路径不会自动成为完整覆盖。`NOTIFY_TCC_MODIFY` 也只是 TCC 变更通知，不是向应用开放任意重写屏幕录制权限。生产 ES 客户端需要 Apple 批准 [endpoint-security.client](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.endpoint-security.client)，SDK `es_new_client` 还要求 TCC 完整磁盘访问。获得 ES entitlement 本身不解决逐窗口捕获策略。

[DriverKit](https://developer.apple.com/documentation/driverkit) 提供 USB、HID、网络、PCI、串口、音频等受支持家族；需要 [driverkit entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.driverkit) 及匹配能力。未发现捕获策略/WindowServer 合成过滤家族。构造一个虚拟显示设备，最多改变该设备的路径，不代表可拦截每个窗口的所有系统捕获接口。

## 6. WindowServer、SkyLight、Quartz Compositor 与捕获路径

可以采用下面的**概念模型**讨论风险，但不是经逆向验证的函数调用图：

```text
应用的 UI / 媒体 Layer → 系统窗口合成与显示服务 → 物理显示
                                  └→ 捕获服务 → SCK / CG 客户端
```

Apple [SCK 官方示例](https://developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos) 提到 queue depth 影响 WindowServer 内存；[WWDC22 10155](https://developer.apple.com/videos/play/wwdc2022/10155/) 说明 SCK 交付 IOSurface 支持的帧、服务端 surface pool 和 GPU 加速；独立窗口捕获可包含被遮挡甚至移出屏幕的窗口内容。因此“在窗口上盖一个普通黑色覆盖窗”不能推导为独立窗口捕获安全。

Quartz Compositor 是系统窗口合成架构中的概念；[Quartz Display Services](https://developer.apple.com/library/archive/documentation/GraphicsImaging/Conceptual/QuartzDisplayServicesConceptual/Articles/Overview.html) 是显示配置等公开服务，其文档里的“capture display for exclusive use”是显示独占语义，不能理解成阻止别的进程生成图像的通用保护。该归档文档不应作为现代 SCK 内部实现依据。

本机公开 SDK 没有 SkyLight 或 WindowServer 公共框架头文件；Apple 未在本次查阅资料中公布完整 SCK → 私有合成器 → 驱动调用链，也未公布可注入第三方捕获授权回调的扩展接口。不能把从网络文章找到的私有符号当作官方支持 API，或根据一个 macOS 版本的行为保证后续版本。

Kext 不是自动获得 WindowServer 语义拦截的办法。[Apple 平台安全文档](https://support.apple.com/guide/security/securely-extending-the-kernel-in-macos-sec8e454101b/web) 说明 macOS 11 起第三方 Kext 进入 AuxKC，更新需要批准与重启；Apple silicon 需在恢复环境允许 Reduced Security 下的 Kext。Apple 不再推荐 Kext。普通 root、Kext 签名与可随意改系统合成器不是同一件事。私有框架/补丁还没有稳定 ABI 和覆盖承诺；[App Review Guidelines 2.5.1](https://developer.apple.com/app-store/review/guidelines/#software-requirements) 要求公开 API。

若业务要求“所有其他进程不许截取，但指定监考程序仍通过系统捕获得到同一窗口”，本次没有找到公开的进程白名单接口。可部署方向应是：应用自身原始帧录制 + 受保护显示，或申请 AAC 的考试会话能力；如果必须保留普通 UI 并要求特殊系统策略，应向 Apple DTS/Feedback 提交明确需求。本文未发送任何申请，也未修改 SIP、启动安全、TCC 数据库或安装系统扩展。

## 7. 证据文件与补测

`research/system/` 保存了从 `developer.apple.com/tutorials/data/documentation/…json` 获取的官方文档快照及 `sdk-evidence.txt`。JSON 的平台 metadata 可复核最低系统版本。SDK 检索是静态证据，只能确认公开声明和本机 SDK 范围，不能替代运行测试。

AAC 生命周期参考代码见 `Sources/AssessmentSessionExample.swift.txt`，entitlement 模板见 `Sources/AssessmentSessionExample.entitlements.plist`。本机仅以 Swift 5 模式、arm64 macOS 10.15.4 target 完成 `swiftc -typecheck`，并用 `plutil -lint` 检查模板；没有运行 session，不能据此确认运行可用或捕获行为。

后续需单列 AAC 已获批/未获批、开始前/开始后/中断后、FPS 测试内容/生产内容、内屏/HDCP 外屏/不兼容转接器、SCK 独立窗口/整屏、快捷键截图、客户端原始帧录制等用例。没有完成的格子必须写“未验证”，不能借用本次普通 AVSampleBufferDisplayLayer Demo 的结果填入 DRM 或 AAC 路线。
