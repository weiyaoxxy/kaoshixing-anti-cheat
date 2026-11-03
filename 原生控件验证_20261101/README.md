# 原生控件保护专项验证

日期：2026-11-01。本目录独立保存原生控件验证，不替换此前两轮 Demo、文档和原始证据。

本项目已经实现“真实 AppKit 控件的编辑状态 → 离屏绘图 → 原始视频帧 → 受保护显示”的 PoC。它不是给任意现成 `NSWindow` 添加通用防截屏开关。已保存的实验同时包含成功的基本交互，以及必须保留的反例：系统拼音候选文字可出现在外部显示器/矩形截图中；原生源窗口一旦上屏，再隐藏后，已测 SCK 路径仍可能返回其此前内容。完整结论以专项报告及相应证据批次为准。

当前按用户要求暂停主动桌面测试。本 README 与复现文档仅作离线整理；未来运行示例会打开窗口、可能注入合成输入或改变本 App 的前台状态，不能在用户通过 ToDesk/UU 操作桌面时直接执行。

## 审阅入口

- [专项验证报告（Word）](交付报告/原生控件保护_专项验证报告_v1.0.docx)
- [专项验证报告（Markdown）](docs/原生控件验证报告.md)
- [构建与复现](docs/构建与复现.md)
- [离线分析索引](research/offline-analysis-index-20261101.json)
- [中文候选区域核验](research/ime-roi-analysis-20261101T134127Z/README.md)
- [验证设计与边界](docs/验证设计与边界.md)
- [中文输入法验证结果](docs/中文输入法验证结果.md)
- [AX 验证结果](docs/AX验证结果.md)
- [捕获探针异常与修复](docs/捕获探针异常与修复.md)
- [输入与图像分析工具](docs/输入与图像分析工具.md)
- [Apple API 依据](research/native-api-evidence.md)

## 实现结构

`NativeControlDemo` 使用真实 `NSTextField`、`NSButton`、`NSScrollView` 和 `NSTextView`。两个 raster 模式把这些控件放在从未 `orderFront` 的源 `NSWindow` 中，以 `NSView.cacheDisplay(in:to:)` 获得控件树的位图，再转换成 `CVPixelBuffer` 和 `CMSampleBuffer`。可见呈现窗口由 `AVSampleBufferDisplayLayer` 显示帧；保护模式将 `preventsCapture` 设为 `true`。

呈现端 `ProxyView` 接收事件，并把编辑操作转发给真实控件及 `NSTextField` 的 `NSTextView` field editor。Tab 焦点循环、按钮键盘激活及坐标映射由代理实现。原生控件的内容、文字选区等来自控件绘制；插入光标和按钮焦点轮廓有明确记录的代理辅助绘制，不应描述成完整原生窗口行为自动保留。

自身录像直接把原始像素帧交给 `AVAssetWriter`，生成 H.264/MP4。它不重新截取受保护屏幕，也不包含系统输入法候选窗、普通顶栏或桌面其他窗口。

| 模式 | 原生控件位置 | 可见考试画面 | 保护设置 |
|---|---|---|---|
| `direct` | 直接位于可见窗口 | 原生 AppKit 绘制 | 普通窗口对照 |
| `raster-baseline` | 隐藏源窗口 | 原生控件绘制得到的视频帧 | `preventsCapture=false` |
| `raster-protected` | 隐藏源窗口 | 相同绘制链的视频帧 | `preventsCapture=true` |
| `mixed` | 隐藏源窗口，另有可见普通标签 | 受保护视频＋普通原生覆盖标签 | 用来观察普通覆盖内容是否仍泄露 |

源窗口与呈现窗口均使用 `.readOnly` sharing type，没有以 `.none` 掩盖主路线。隐藏源窗口可能被系统枚举；“隐藏”与“受捕获保护”不是同义词。

## 已测版本识别

App 的 bundle 标识为 `local.examcapture.nativecontrols`。构建脚本中的 `CFBundleShortVersionString` 仍为 **0.1**、`CFBundleVersion` 为 **1**；本轮后期源码状态字段使用 **`native-controls-v0.3`** 表示内部修订。这几个字段没有被强行改成一致，以免改动已经测试的二进制。

本次 v0.3 锁定文件的 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `Sources/NativeControlDemo/main.swift` | `b256ce232aeba98257de5b87d6061f516fe910eb6c5bfd91eac1b2fd9cf72c77` |
| `build/NativeControlDemo.app/Contents/MacOS/NativeControlDemo` | `0cbe3e4fafc0cc30b2877940f7c4f814815d2e2748365a5e571f79020a6b4aa1` |

各样本的 `run-config.json` 与 `source-snapshot.swift` 保留其实际源码/二进制版本。请依据这些哈希区分 v0.1、v0.2 和 v0.3 样本，不按应用 Finder 显示版本混算。

## 证据目录

| 目录 | 用途及边界 |
|---|---|
| `artifacts/native-final-v03-20261101T133147Z/` | v0.3 基本交互与独立捕获；mixed 后续输入被工具拒绝，须按记录降级解读 |
| `artifacts/native-keyboard-20261101T133448Z/` | 双击、拖选、Tab/Shift-Tab、Space/Return 的附加交互 |
| `artifacts/native-ime-20261101T134127Z/` | 系统简体拼音组合/提交，以及候选窗泄露反例 |
| `artifacts/source-exposure-control-20261101T132024Z/` | 源窗口从未上屏、主动上屏、再隐藏的独立对照 |
| `artifacts/source-probe-diagnostic-20261101T131705Z/` | 隐藏源窗口捕获诊断，返回错误/无图不能计为保护成功 |
| `artifacts/native-matrix-20261101T132323Z/` | 早期矩阵，保留旧版本及焦点异常；不能替代最终版本结果 |
| `research/video-integrity.json` | 已选录像的全解码、输入时间戳与代表帧检查 |

`source-reference.png`、`*-source.png` 是应用内部生成的像素证据；`capture/` 和系统截图才是外部捕获；MP4 代表帧与完整解码检查也分开记录。没有输出、权限不足、窗口失去可捕获前置条件或仅 OCR 未命中，都不能单独判为安全。

默认定时器目标为 20 fps；输入事件、状态变化及控制命令也会触发绘制。这个数字不是严格固定帧率，更不是显示器实际刷新率。文件平均帧率、渲染耗时和端到端输入延迟应分别解释，详见复现文档。

源码、构建与操作说明均在本目录。当前已测能力仅属于合成控件 PoC，不能据此承诺自动保护任意 AppKit/WebView/Electron 窗口、所有系统菜单、所有输入法、所有 AX 客户端或所有 macOS 版本。
