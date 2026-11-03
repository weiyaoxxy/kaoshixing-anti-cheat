# Clear Key 有效媒体与捕获行为实测

实验日期：2026-11-01。系统：macOS 26.6.2（25G83），Apple Silicon；构建 SDK：macOS 26.5，Swift 以 macOS 14 为部署目标，并在运行时检查 macOS 26.4。本文是新增的独立实验，不改写此前 SampleBuffer Demo 的证据。

**本机结果：真正的 SAMPLE-AES identity HLS 在 `allowsCaptureOfClearKeyVideo=false` 时，所测外部截图／SCK 流没有取得视频内容；改为 true 后，各路径均取得同一素材。与此同时，false 时同进程 `AVPlayerItemVideoOutput` 仍取得清晰像素。后一个现象与 Apple 文档的广义描述不一致，必须保留为待解释的实测差异，不能依赖它设计稳定的自录豁免。**

## 媒体有效性与控制变量

媒体来自本项目此前自行生成的合成试题录像：`../artifacts/matrix-20261101T082724Z/baseline/self-recording-A1C86017.mp4`。源为 H.264、1800×1000、约 17.993 秒；并未使用真实考试题目或第三方受 DRM 保护作品。

用 Bento4 官方仓库 `axiomatic-systems/Bento4`，commit `b8c50a078356a1c3444ce0a8744634ed488424a4` 构建 `mp42hls`。生成参数为 `--hls-version 5 --segment-duration 3 --audio-track-id 0`；加密组另加 `--encryption-mode SAMPLE-AES --encryption-key ... --encryption-iv-mode random --encryption-key-uri key.bin --encryption-key-format identity`。manifest 包含 `METHOD=SAMPLE-AES`、匹配 IV 和 `KEYFORMAT="identity"`，密钥为固定的 16 字节测试数据。因此这不是只改 m3u8 标签，也不是整段 AES-128 加密冒充 SAMPLE-AES。

原始文件 SHA256、工具 commit、完整命令与全部输出哈希见 [media-generation.json](../research/clearkey/media-generation.json)。FFmpeg 使用匹配密钥成功离线解密，输出 [encrypted-offline-decoded.png](../research/clearkey/encrypted-offline-decoded.png)。该图只验证媒体，不代表 AVPlayer 捕获行为。

原生 ClearKeyDemo 采用普通 NSWindow（`sharingType=readOnly`）、AVPlayerLayer，不启用 `preventsCapture`。播放器分别运行明文 false、SAMPLE-AES false、SAMPLE-AES true；HLS 服务仅绑定 `127.0.0.1:8766`，实验结束已停止。未申请 FPS 生产资格、AAC entitlement 或特殊权限；捕获进程已有屏幕录制权限。identity 测试流及明文 key 不应作为生产 DRM 安全设计。

本轮未通过 `AVContentKeySession(.clearKey)` 手动响应 key request；使用 HLS identity URI 交付 key。不能把这项实验覆盖范围扩展为所有 Clear Key 的交付方式。

## 三组主矩阵

完整目录：[clearkey-20261101T085500Z](../artifacts/clearkey-20261101T085500Z)。每组播放器约运行 24 秒并完成一次循环，捕获在 readyForDisplay 且时间已推进超过 1 秒后开始。明文／false／true 捕获前时间分别为 1.770／1.819／1.819 秒，`itemStatus=readyToPlay`、rate=1、无播放器／媒体错误，三个 `isOutputObscuredDueToInsufficientExternalProtection` 都为 false。这个属性不是防截图成功指示器。

| 组别 | player PID | 捕获 PID | window ID | VideoOutput 检查／复制 | 落盘像素 PNG 命中秘密 |
|---|---:|---:|---:|---:|---:|
| 明文，false | 70589 | 70607 | 184169 | 239／237 | 8／8 |
| SAMPLE-AES，false | 71182 | 71220 | 184185 | 240／239 | 8／8 |
| SAMPLE-AES，true | 71738 | 71777 | 184201 | 240／239 | 8／8 |

捕获 PID 来自各组 `capture/report.json`，播放器 PID 来自 `player-state.json`，两者不同。`permissionBefore` 与 `permissionAfter` 三组均 true。精确状态及时间保存在 `state-before-capture.json`、`playback-observations.json` 和 `video-output-samples.json`。

下表数字为“识别到合成秘密标记的图片数／已保存且可读取的图片数”。OCR 与预先定义的洋红色标记区域逐张统计一致；所有流的报告帧数、实际文件数相符，SCFrameStatus 为 complete，无流错误。没有用缺图作为保护通过。

| 捕获路径 | 明文 false | SAMPLE-AES false | SAMPLE-AES true |
|---|---:|---:|---:|
| 系统 `screencapture -l windowID` | 1／1 | 0／1 | 1／1 |
| 旧 CGWindowListCreateImage：窗口 | 1／1 | 0／1 | 1／1 |
| 旧 CGWindowListCreateImage：显示器合成 | 1／1 | 0／1 | 1／1 |
| SCScreenshotManager：窗口 | 1／1 | 0／1 | 1／1 |
| SCScreenshotManager：显示器 | 1／1 | 0／1 | 1／1 |
| SCStream：窗口，约 2 秒 | 21／21 | 0／22 | 21／21 |
| SCStream：显示器，约 2 秒 | 21／21 | 0／22 | 21／21 |
| 同进程 AVPlayerItemVideoOutput 采样落盘 | 8／8 | **8／8** | 8／8 |

注意旧 CoreGraphics 测试由 `dlsym` 调用仍存在的公开旧符号，仅为兼容观察；当前 SDK 已不允许直接以该声明构建现代应用。不把该运行现象写成受支持的新产品部署路线。名为 `cg-display.png` 的文件实际也来自 `CGWindowListCreateImage`，不是 `CGDisplayCreateImage`。

三组共 **167 张 PNG**，其中 **128 张连续流采样图、15 张外部单帧图、24 张同进程像素图**。全部解码并逐图 OCR 和 marker 检查：明文组 55／55、加密 false 8／57、加密 true 55／55 命中。false 的全部 49 张外部图片均未检出；原生 `CLEARKEY-PUBLIC` 标签仍可见，视频区域变黑，不能把它写成整个窗口消失。

标记检查使用 R≥190、G≤90、B≥190、A≥200；在预定 176×128 源矩形中，阳性图有 22,225 像素符合阈值，false 外部图均为 0。归档 [analysis.json](../artifacts/clearkey-20261101T085500Z/analysis.json) 和 [analysis.csv](../artifacts/clearkey-20261101T085500Z/analysis.csv) 记录每一张图的 SHA256、ROI、OCR、marker 计数；复核脚本是 [analyze-clearkey-results.py](../scripts/analyze-clearkey-results.py)。

## 供审阅的原始截图

以下均为生成的原始窗口截图；只含合成试题和 Demo 自身，不是对用户当前显示器是否可见的人工确认。

SAMPLE-AES + false：系统窗口截图只保留原生标签，视频区域不可见。

![SAMPLE-AES false 外部系统截图](../artifacts/clearkey-20261101T085500Z/sample-aes-false/system-window.png)

SAMPLE-AES + true：相同媒体、相同窗口布局的外部系统截图可读取题目。

![SAMPLE-AES true 外部系统截图](../artifacts/clearkey-20261101T085500Z/sample-aes-true/system-window.png)

SAMPLE-AES + false：同进程 VideoOutput 的第一张有效像素图仍可读取题目。

![SAMPLE-AES false VideoOutput 像素](../artifacts/clearkey-20261101T085500Z/sample-aes-false/video-output-001.png)

## 初始化顺序和不挂接 VideoOutput 的补充对照

为排除最直接的初始化顺序解释，另运行两组约 11 秒实验，媒体及 false 保持相同：

| 变体 | 操作顺序／状态 | 外部单帧命中 | SCK 窗口／显示器流命中 | 同进程像素 |
|---|---|---:|---:|---|
| after | 先创建 player 并设置 false，再 `item.add(VideoOutput)` | 0／5 | 0／6、0／6 | 检查 110 次、复制 107 次；4 张落盘均命中 |
| none | 不把 VideoOutput 加到 player item；仍通过 AVPlayerLayer 显示 | 0／5 | 0／6、0／6 | 未挂接，无复制；不能把 0 视为属性拦截 |

两组均 readyForDisplay、时间推进（结束时约 10.597／10.841 秒）、无播放器错误、属性回读 false；约 0.5 秒 SCK 采样的全部帧有效完整，所有预期 PNG 到齐。全部 **38 张 PNG** 完成 OCR 与 marker 复核；after 4 张像素图为阳性，其余 34 张外部图 marker 均为 0。

证据目录：[clearkey-order-20261101T090226Z](../artifacts/clearkey-order-20261101T090226Z)，逐图数据：[analysis.json](../artifacts/clearkey-order-20261101T090226Z/analysis.json)，复现脚本：[run-clearkey-order-controls.py](../scripts/run-clearkey-order-controls.py)。两次运行的源码快照分别保留在其 artifacts 根目录 `main.swift.snapshot`，后续源码变更不会覆盖已运行版本。

由此，当前现象**没有被简单的“flag 设置在 add(output) 之后”解释掉**；不挂接 VideoOutput 时也观察到外部隐藏。仍不能据此说明内部原因，更不能宣布已证明所有初始化顺序等价。五组累计 **205 张图：152 张连续流、25 张外部单帧、28 张同进程像素采样**；这不是在每个物理刷新时刻读取全部帧的证明。

## 为什么不能直接宣布满足最终目标

- 已有有效解密、时间推进、外部黑图、true 阳性对照，但此次 AVPlayer 路径没有新的用户肉眼确认。此前用户确认的是 SampleBuffer Demo，不能借用到这个播放器。
- 这是本地 VOD 播放，未实现将交互式试卷低延迟编码、加密、分片再播放的实时流水线。分片大小为 3 秒；没有进行文字阅读延迟或端到端交互延迟验收。
- 视频区可被隐藏，原生 AppKit 标签仍可被读取；普通题干、输入法候选框、菜单或辅助窗口若落在视频区之外，需单独分析。
- `true` 让外部截图和 SCK 同时读到内容，不能用它来只放行自己。
- false 时 VideoOutput 出现明文是当前系统／媒体／初始化顺序的观察。文档明确把 VideoOutput 包括在受控 API 中，故不能凭本机一次现象承诺长期同进程豁免。
- 只有一个 OS build、设备、短时视频和已列出的捕获配置，未覆盖所有远程桌面、外接显示器、屏幕镜像、AirPlay、HDR、DRM、滤镜切换或所有第三方录制器。

## 官方依据与复现

Apple [allowsCaptureOfClearKeyVideo](https://developer.apple.com/documentation/avfoundation/avplayer/allowscaptureofclearkeyvideo) 从 macOS 26.4 开始，默认 false，列出截图、录屏、AVPlayerItemVideoOutput 和 ScreenCaptureKit；明确不影响 FairPlay Streaming。文档快照：[D04-clear-key-capture.md](../research/deep-review-20261101/D04-clear-key-capture.md)。

Apple [Using content protection systems with HLS](https://developer.apple.com/documentation/http-live-streaming/using-content-protection-systems-with-hls) 说明 key format／URI，归档 [TN2454](https://developer.apple.com/library/archive/technotes/tn2454/_index.html) 给出 identity、SAMPLE-AES、16 字节 key／IV 的测试方法。Bento4 [mp42hls](https://www.bento4.com/documentation/mp42hls/) 与 [源码](https://github.com/axiomatic-systems/Bento4) 是生成工具依据。以上访问日期 2026-11-01。文档支持测试素材构造，不能替代本机实测。

在本轮文件夹中运行：

```sh
bash scripts/build-clearkey-demo.sh
python3 scripts/prepare-clearkey-media.py
python3 -m http.server 8766 --bind 127.0.0.1 --directory research/clearkey/media
# 另一个终端；运行完停止上面的服务
python3 scripts/run-clearkey-matrix.py
python3 scripts/analyze-clearkey-results.py artifacts/clearkey-实际时间戳
```

Bento4 已在 research 中构建；生成器记录随机 IV，因此重新生成时媒体哈希会变化。三组 GUI 按顺序运行，避免同时改变桌面。使用父目录原有 CaptureProbe／InspectMedia；若拷贝此文件夹单独使用，需要一并提供父目录工具或重新构建它们。
