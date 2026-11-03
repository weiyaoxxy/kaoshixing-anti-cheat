# CaptureHook：按捕获进程安装的实验性取屏拦截器

本库属于独立 Hook 新方案，不依赖考试窗口的 `preventsCapture` 或 `sharingType = .none`。它只影响实际加载了本 dylib 的进程；另一个未加载库的捕获程序不受影响。

## 构建和配置

```bash
bash scripts/build-hook.sh build/libCaptureHook-v1.4.dylib
```

构建为 arm64、最低部署 macOS 14，使用 Foundation / AppKit / ScreenCaptureKit / CoreGraphics / CoreMedia / CoreVideo / IOSurface / QuartzCore。库采用本地 ad-hoc 签名；没有修改或重签任何第三方 `.app`。链接 ScreenCaptureKit 会使该框架随库加载，所以“某进程加载了 ScreenCaptureKit”本身不是它实际取屏的证据，必须看 `capture_call` 和真实帧回调。

省略输出参数时默认生成 `build/libCaptureHook-v1.4.dylib`。构建脚本拒绝覆盖任何已有输出文件或符号链接；重复构建请选择新文件名，保留旧版及已有实验产物。

由主控脚本在**新启动的受测进程**中指定：

- `DYLD_INSERT_LIBRARIES`：本 dylib 的绝对路径。
- `HOOK_DEMO_LOG`：可写 JSONL 路径，父目录需预先存在。v1.3 支持 `%p` 展开为当前 PID，建议每个进程独立新日志；已有同名文件会追加，混合历史会被严格分析器拒绝。
- `HOOK_DEMO_SESSION_ID`：由实验控制器在启动前生成的新会话标识；缺省为空，不可用来证明某次实际调用。
- `HOOK_DEMO_MODE=audit|block`：默认 audit；其他值也按 audit 处理。
- `HOOK_DEMO_CONFIG`：block 时读取的目标 JSON 路径。

这不是向已运行进程注入的工具，不会自行获取 task port、关闭 SIP、修改 TCC 或持久安装启动项。正式签名目标是否允许 dylib 加载，需要在其原始配置下单独验证。

目标配置：

```json
{
  "schemaVersion": 1,
  "enabled": true,
  "windowID": 12345,
  "ownerPID": 1234,
  "bounds": {"x": 100, "y": 100, "width": 900, "height": 600}
}
```

`bounds` 是 CoreGraphics 屏幕坐标，单位 point、原点在屏幕左上方向约定中，必须由原生考试 Demo 实时更新。`ownerPID` 是审计字段；当前遮蔽匹配使用 windowID / bounds，尚未用 ownerPID 校验 windowID 重用。截图/帧生成与配置读取不同步，移动窗口的时序和旧帧不能据此获得原子保证。

## 实际挂接位置

| 路径 | audit | block 实现 |
|---|---|---|
| `CGWindowListCreateImage` | 记录窗口 ID 与 list options | 对目标单窗口将返回图像全部变黑；对可识别的桌面范围遮蔽目标矩形 |
| `CGDisplayCreateImage` | 记录显示器 ID | 复制 CGImage 后按显示器 bounds 映射目标矩形并填黑 |
| `CGDisplayStreamCreate` / `...WithDispatchQueue` | 创建调用；首帧和每 60 次回调记录状态、尺寸、像素格式 | 仅完整、非平面 BGRA surface；新建 IOSurface、复制像素后填黑，再传给原 handler |
| `CGDisplayStreamStart` / `Stop`（v1.4） | 启停调用、原始 CGError 返回值；只算诊断 | 原参数调用原函数，原样返回 |
| `SCShareableContent.getShareableContentExcludingDesktopWindows:onScreenWindowsOnly:completionHandler:`（v1.4） | 请求及结果，仅成功、错误域/码、显示器/窗口/应用数量 | 原参数、结果对象和错误原样转发，不枚举或记录对象内容 |
| `SCScreenshotManager.captureImage(contentFilter:configuration:)` | 记录实际调用和已知范围 | 回调中复制 CGImage 后遮蔽 |
| `SCScreenshotManager.captureImage(in:)` | 记录矩形 | 回调中按矩形映射遮蔽 |
| `SCScreenshotManager.captureSampleBuffer(...)` | 记录实际调用 | 仅 BGRA CVPixelBuffer，复制并重建样本，保留时间戳与附件 |
| `SCStream` | init / add output / start / stop / 更新 filter/config；首帧及每 60 帧元数据 | 以输出代理接收屏幕帧，只复制 BGRA 样本，遮蔽后转发给原接收者 |

C 入口使用 dyld 的 `__interpose` 机制；ObjC 入口使用公开 Objective-C runtime 替换方法实现。filter 的原始窗口或显示器范围来自公开 initializer 参数及公开属性，不读取私有 ivar、不修改 WindowServer 或 SkyLight。

单窗口范围匹配到目标 windowID 时将整张输出变黑；显示器/应用过滤器沿用其原始捕获范围，在图像里遮蔽目标窗口矩形。应用过滤器的这个实现不会重建排除规则，也不会自动排除新产生的其他敏感弹窗。

## 明确的实验边界

**这是 fail-open 实验，不能据此承诺生产防泄漏。** 以下条件下将原始结果继续传给调用者，并记录 unsupported / passthrough：

- 配置缺失、无效或 `enabled=false`。
- 无法识别捕获范围，或样本不是 BGRA / 是平面格式。
- `SCStreamConfiguration.sourceRect` 为非空裁剪区域。
- CGDisplayStream properties 显式包含 sourceRect / destinationRect；当前不处理它们的坐标变换。
- 输出长宽比与完整捕获范围不一致，无法按当前简单模型精确映射。
- 像素或样本分配、锁定失败。

不能把上述原样放行、API 报错、进程崩溃或没有回调当成保护成功。正确验收必须同时看到：真实目标原生窗口本机可用、基线可读、audit 与基线一致、block 目标不可读、非目标公共对照仍可读、停用后恢复。

其他限制：

- CGDisplayStream 拷贝后保留原 dirty-region metadata，没有扩大为包含本次遮蔽区域；若消费方仅处理 dirty region，特别是窗口移动后，遮蔽的端到端效果需另测。它目前只适合静态目标实验。
- SCK 输出代理保留时间戳、CV attachments 和 sample attachments，但不保证所有 HDR、缩放、裁剪、阴影、缓存帧和多屏组合。
- 更新 filter / configuration 的完成回调与已经排队的帧可能跨越边界；这里没有实现帧级状态事务。
- 未 hook 新版 `captureScreenshot(...)`、SCRecordingOutput 写文件路径、其他框架、私有取屏路径及尚未安装拦截时已创建的捕获流。
- `audit` 也包装帧回调以记录元数据，会增加执行开销；必须通过对照测试确认没有改变真实捕获内容和生命周期。
- 本库只改变加载它的捕获进程交付给其接收者的帧。未加载它的进程仍能获取普通原生考试窗口。

## 日志与证据级别

`image_loaded` 仅证明 dylib 执行了初始化；`hook_installed` 仅证明方法替换已安装；`capture_call` 才证明被挂接入口实际被调用；`sck_stream_frame` / `display_stream_frame` 证明到了帧回调。`image_redacted` 或 `...result=redacted` 只是代码处理记录，最终还必须解码和检查输出图片 / 远程接收端画面。

日志只记录调用、尺寸、ID、状态、帧计数、目标矩形和错误码，不记录捕获内容、远程连接 ID、密码或输入文字。v1.1 起递归清理 NaN / Infinity 为显式字符串，并记录 `sanitizedFields`；序列化异常有兜底，不允许日志异常直接抛入宿主。

## 版本与已知失败保留

- v1.0：纯加载 smoke 成功；真实 CG 捕获测试发生递归并崩溃，**无效实验**。原因是 C wrapper 内 `dlsym(RTLD_NEXT, ...)` 在本机重入了同一个 interposed wrapper。
- v1.1：增加日志非有限数防御和 CGDisplayStream 裁剪条件，但尚含旧 C 解析问题，不能用于捕获实验。
- v1.2：C wrapper 改为本 interposing image 内对原始 alias 的直接绑定，消除上述 `RTLD_NEXT` 解析路线；是否完整通过实际矩阵以主目录 artifacts 和报告为准。

`LoadSmoke.m` 是自有加载测试程序；v1.1 的 `load-smoke-v1.1.jsonl` 含递归 NaN / Infinity 日志自检。该测试没有取屏，不能替代捕获功能测试。


## v1.3：验证实际调用的关联证据

每条日志新增 `schemaVersion=2`、`hookVersion`、`sessionID`、`hookInstanceID`、PID/UID、微秒级进程启动身份、实际可执行路径、单调 `sequence` / `hostTime` 以及 `priorLogWriteFailures`。`image_loaded` 还记录库路径。身份查询失败不会伪造身份；fork 后没有 exec 的子进程不支持本协议，不沿用父进程身份写日志。

采集入口以 `callID` 关联请求和结果。`SCStream.init`、添加输出、更新配置和停止不单独作为“开始取屏”的证据。截图返回记录图像/样本是否有效、尺寸、错误；单纯 API 被调用和实际收到图像分开。

采集流使用独立 `streamID`，输出使用 `outputID`，采样帧使用 `frameID`，不使用对象地址作为唯一身份。SCK 有效帧要求屏幕输出、有效且 ready 的样本、图像存在、正尺寸、`SCFrameStatusComplete`；缺失 status、不完整/idle/blank 回调不冒充画面。CGDisplayStream 使用其自身的 complete 状态、surface 和尺寸。首个有效帧一定额外记录，之后继续按计数采样。

`frame_forwarded` 在原接收回调返回后记录同一帧身份。这只支持“原回调已返回”，不证明编码、发送、远端显示或遮蔽成功。帧日志记录处理前的有效性；改变画面仍需独立验证输出。

序号与写入由同一进程锁排序。每条 JSON 与换行一起写，并使用非阻塞文件锁避免多个 v1.3 进程把共享日志写坏；竞争/写入失败会增加失败计数，序号可能有缺口，分析器必须降级。共享日志即使语法完整，也不是单进程分析器的合法输入；优先 `%p` 独立日志。日志必须是普通文件，不跟随末级符号链接。

调用证据分析和测试：

```bash
python3 scripts/test-hook-invocations.py --help
python3 scripts/analyze-hook-invocations.py --help
python3 -m unittest discover -s tests -p test_hook_invocations.py
python3 scripts/test-hook-logging.py "$PWD/build/libCaptureHook-v1.3.dylib" /tmp/hook-logging-new-run
```

详见 [调用证据分析器](../../scripts/analyze-hook-invocations.README.md)。它要求独立期望清单与完整会话日志，不自动消费旧文件，不根据任意一个 `capture_call` 字符串确认当前 UU。v1.3 同时修复同一输出对象移除音频时误删屏幕代理映射的问题；重复屏幕注册复用原代理以保留 SDK 的重复注册拒绝语义。

这些日志和清单是本机可修改证据，不是远程证明；未提供独立终止序号时，不能检测日志末尾完整行被删除。已经建立且未经过当前 Hook 创建路径的采集流，无法补造创建关系。只在自有宿主验证通过，不能宣称真实 UU 已命中，更不能宣称考试画面已隐藏。

## v1.4：有静态引用依据的准备与启停诊断

本版仍使用 schema 2，所有记录的 `hookVersion` 和加载事件 `version` 为 `1.4`。只新增原版 UU `libstreamer` 静态导入/公开选择器中已确认的三个入口，不增加其他采集 API，也不改变已有遮蔽逻辑。

- `shareable_content_request/result` 以独立 `callID+api` 配对。结果记录 `success`、`errorDomain/errorCode`、`displayCount/windowCount/applicationCount`；成功要求内容对象非空且无错误。不记录窗口标题、应用名称、账号或画面。结果对象和 NSError 原样传给调用者；原调用传入 nil completion 时仍把 nil 交给原实现，不补造完成回调。
- `display_stream_control_call/result` 的 `api` 为 `CGDisplayStreamStart` 或 `CGDisplayStreamStop`，以 `callID` 配对；记录 `streamProvided`、原始 `returnCode` 及其是否等于 `kCGErrorSuccess`。不保存原生流指针，不根据对象地址建立持久身份关系，也不补造已有流的创建记录。
- 这些事件仅提供诊断，分析器不因此设置 `captureEntryObserved` 或任何有效帧标志。它们没有解决 UU 的加载权限、组件信任或正常连接问题。

不采屏的包装函数对照：

```bash
python3 scripts/test-hook-diagnostics.py \
  --library build/libCaptureHook-v1.4.dylib \
  --output artifacts/hook-v1.4-diagnostics-new-run
```

该测试只运行自有宿主：共享内容方法在加载 Hook 前替换为合成对象返回器，验证成功/失败、参数、对象及错误身份、nil completion 的透传；CG 启停只传 NULL，未创建捕获流。测试不枚举真实窗口、不采屏、不操作 UU。它不验证有效流的启动成功路径或真实 UU 调用；这些边界不能被 `passed=true` 覆盖。
