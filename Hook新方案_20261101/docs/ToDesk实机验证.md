# ToDesk 实机验证：原生考试窗口的进程内捕获拦截

本文件属于 **Hook 新方案**。测试日期为 2026-11-01；人工观察时间按用户时区 Asia/Calcutta（IST，UTC+05:30）展示，原始 JSON 保留 UTC 与主机单调时钟。

## 验证结果与适用范围

**本机 ToDesk 5.2.3.0（build 2943）已完成真实远端的三阶段人工验证：audit 时考试窗口与公共对照可见，block 时考试区域隐藏而公共计数继续变化，恢复原启动任务并重新建立正常会话后考试内容再次可见。**

当前结果支持：在本机、该 ToDesk 版本、已安装 hook 的用户级 `ToDesk_Session` 进程及此次实际命中的 SCK 显示器捕获路径中，对原生考试窗口范围做像素遮蔽可以影响真实远端画面。它不是给原生 NSWindow 设置系统级防截屏属性，也不证明所有独立进程都不能截图。

证据分为三层，必须分别解读：

- **进程内日志**：动态库加载、SCStream 调用、帧格式和处理分支。
- **用户远端观察**：用户通过 ToDesk 实际看到的可见/隐藏/恢复状态与 LIVE-TICK 动态对照。
- **本地独立捕获对照**：未安装 hook 的另一个进程仍能截到原生题目，明确证明效果按捕获进程生效。

本轮没有保存 ToDesk 接收端截图或接收端视频；用户反馈是远端证据。`redacted` 日志只说明代码走到了遮蔽分支，不能把它称为远端截图或对全部传输帧的像素检验。

## 环境与实验对象

| 项目 | 本轮配置或证据 |
|---|---|
| 主机 | Apple M4 / arm64，macOS 26.6.2（25G83） |
| 远程软件 | ToDesk 5.2.3.0，build 2943 |
| hook 库 | `build/libCaptureHook-v1.2.dylib`，日志版本 1.2 |
| 库 SHA-256 | `ce5f744bd17fb25b617f9a70eb969dcedcb2fe296e9b0c3424f647a6f3202f04` |
| 原生目标 | `NativeExamHookDemo`，真实 NSWindow、NSTextField、NSTextView、NSButton、NSScrollView、NSPopUpButton |
| 窗口共享状态 | readOnly；未使用 preventsCapture、DRM 或 sharingType.none |
| 考试标记 | `NATIVE-EXAM-SECRET-HOOK9` |
| 公共对照 | 独立窗口 `PUBLIC-CONTROL-HOOK`，LIVE-TICK 持续更新 |
| 配置文件 | `artifacts/native-session-20261101T132925Z/hook-config.json` |
| 本轮实际命中后端 | `SCStream` 显示器捕获，displayID 1，1512×982 point，图像帧 3024×1964 BGRA |
| hook 部署位置 | 当前用户 GUI 域的 Session Proxy 启动任务及其派生 Session；UID 501 |

目标应用本身不保护像素。其控件与画面说明见 [原生窗口说明](../Sources/NativeExamDemo/README.md)。本轮静态二进制与签名分析见 [远程软件静态分析](远程软件静态分析.md)。

## 真实远端三阶段观察

| 阶段 | 用户反馈记录时间（IST） | 记录的原始反馈 | 支持的结论 |
|---|---|---|---|
| audit，加载 hook 但不遮蔽 | 2026-11-01 19:20:28 IST | “两个窗口内容都能看到，LIVE-TICK 在变化” | 远程画面能正常显示考试内容，公共对照不是冻结帧 |
| block，遮蔽考试窗口范围 | 2026-11-01 19:25:01 IST | “考试区域已隐藏，右侧计数仍在变化” | 远端考试区域隐藏，公共对照继续变化 |
| restore，恢复原启动任务 | 2026-11-01 19:29:18 IST | “考试内容已恢复可见，右侧计数正常变化” | 撤销实验启动定义并恢复正常会话后，远端题目重新可见 |

人工记录分别为：

- [audit 用户观察](../artifacts/todesk-audit-20261101T134436Z/human-observation.json)
- [block 用户观察](../artifacts/todesk-block-20261101T135207Z/human-observation.json)
- [恢复后的用户观察](../artifacts/todesk-block-20261101T135207Z/human-recovery-observation.json)

这些反馈验证的是当时观察到的画面和动态对照，不能排除观察间隙内短暂的漏帧，也不能替代完整录屏逐帧检查。

## 实际捕获进程与调用

此次已从静态线索推进到真实进程内调用记录：

| 阶段 | 动态库加载记录 | 实际发生捕获调用的进程 |
|---|---|---|
| audit | Proxy PID 18912、19233；Session PID 19317 | `ToDesk_Session` PID 19317，UID 501 |
| block 成功轮次 | Proxy PID 32439；Session PID 32469 | `ToDesk_Session` PID 32469，UID 501 |

两个成功轮次都记录了 `SCStream.init`、`SCStream.addStreamOutput`、`SCStream.startCapture`、成功的启动回调、持续画面回调和最后的 `SCStream.stopCapture`。初始化记录给出了 display 类型、displayID 1 和 1512×982 的显示器范围。

因此，本次实际取屏位置不是只凭 GUI 的名字推断，而是由 Session PID 的调用日志定位。root 身份的 `ToDesk_Service` PID 78215 保持为原服务；本轮没有向该 root 服务安装 hook，也没有将用户进程实验扩大为系统级服务已受控。

完整记录：[audit hook.jsonl](../artifacts/todesk-audit-20261101T134436Z/hook.jsonl)、[block hook.jsonl](../artifacts/todesk-block-20261101T135207Z/hook.jsonl)。

## 日志数量如何解读

hook 源码只在**首次回调及每 60 次回调**写帧日志，因此下表是抽样日志条数，不是保存的视频帧总数。

| 统计项 | audit | block |
|---|---:|---:|
| JSON 日志行数 | 385 | 367 |
| sck_stream_frame 日志条数 | 332 | 165 |
| 带 3024×1964 BGRA 图像的抽样记录 | 234 | 130 |
| 没有 imageBuffer 的抽样记录 | 98 | 35 |
| redacted 处理结果日志 | 不执行遮蔽 | 130 |
| no_image_buffer 处理结果日志 | 不执行遮蔽 | 35 |
| 日志中最大回调序号 | 19860 | 9840 |

`no_image_buffer` 表示该回调没有可供修改的图像缓冲区，代码保留原样传递；这些记录不计为“遮蔽成功”。日志没有为这些条目保存完整帧状态，因此不进一步断言其全部属于某一种空闲通知。

带图像的记录使用像素格式整数 1111970369，即 BGRA。当前代码复制原始图像缓冲、遮蔽目标矩形，再把处理后的样本交给原始接收对象；没有修改原共享输入缓冲。时间戳和可传播附件被保留。本轮没有在真实 ToDesk 上完成 CPU、端到端延迟、丢帧和长期稳定性测量。

机器可读汇总见 [todesk-live-evidence-summary.json](../research/todesk-live-evidence-summary.json)。

## 独立进程仍可截图：方案范围的直接反证

在 ToDesk block 实验期间，另一个没有安装 hook 的独立捕获程序对同一个原生考试窗口执行了单帧截图。结果：

- 捕获程序返回码为 0。
- 生成 1700×1444 的窗口图像。
- OCR `secretDetected=true`，未出现 OCR 错误。
- 图中原生题目与输入框内容仍可读。

[范围验证 JSON](../artifacts/todesk-block-20261101T135207Z/independent-unhooked-check/scope-check.json)、[捕获报告](../artifacts/todesk-block-20261101T135207Z/independent-unhooked-check/report.json)、[OCR 记录](../artifacts/todesk-block-20261101T135207Z/independent-unhooked-check/ocr.jsonl)。

![未安装 hook 的独立进程仍可截取原生考试内容](../artifacts/todesk-block-20261101T135207Z/independent-unhooked-check/sck-screenshot-window.png)

图注：这是**本机未安装 hook 的独立探针截图**，不是 ToDesk 接收端截图。它证明原生窗口仍正常产生可捕获像素，本轮拦截只改变了被安装 hook 的捕获进程输出。

因此，不能将“本轮 ToDesk 远端隐藏”写成“macOS 原生窗口已经禁止所有外部捕获”。覆盖其他软件、另一实例、另一用户会话或另一捕获后端，均需要另外安装并验证相应拦截。

## 首次 block 启动失败及恢复

保留失败轮次 [todesk-block-20261101T135028Z](../artifacts/todesk-block-20261101T135028Z/instrumentation-state.json)，没有将其计为遮蔽成功：

1. 卸载原任务返回 0。
2. bootstrap 实验副本返回 **5**。
3. 后续检查发现该标签已从**原始 /Library plist 路径**加载，Proxy PID 28878。
4. 脚本判定来源不符合实验副本，触发自动恢复流程，记录 `automaticRollbackSucceeded=true`。

这说明替换启动任务时存在重新注册或启动竞争的实测边界。谁重新注册了任务未在本轮定位，不能仅凭现象断言由某个守护进程实施了“反 hook”。第二次 block 轮次在新目录中重新执行，bootstrap 返回 0，并实际命中了 Session 的捕获回调及用户远端观察。

## 原始文件与启动状态恢复

最终成功 block 轮次的 [instrumentation-state.json](../artifacts/todesk-block-20261101T135207Z/instrumentation-state.json) 记录了恢复原 job 的过程。后续 [last-status.json](../artifacts/todesk-block-20261101T135207Z/last-status.json) 确认：

- 任务标签仍为 `gui/501/com.youqu.todesk.desktop`。
- 来源恢复为 `/Library/LaunchAgents/com.youqu.todesk.session.plist`。
- Proxy 为 running，PID 36612；正常派生的 Session 为 PID 36640。
- 原 plist SHA-256 与实验前一致：`69fca72acbbcfa137a4253f583cb39f12fe76ac45b3b75272a64dfe45f200539`。

另行只读核对了 ToDesk GUI、Service、Session Proxy、Session 四个关键可执行文件，其 SHA-256 均与本轮静态审计基线一致，包含嵌入签名的文件字节未改变。证据为 [original-files-preservation-check.json](../artifacts/todesk-block-20261101T135207Z/original-files-preservation-check.json)。这是文件一致性检查，不冒充一次额外的 codesign 完整验证。

本实验未修改或重签 /Applications 中的原程序，未修改 /Library 原 plist；修改的是当前用户会话里临时加载的任务定义，实验副本保存在项目 artifacts。未安装 kext、未关闭 SIP、未注入 root ToDesk_Service。

恢复任务定义并不自动卸载仍存活的旧 Session 进程。实际操作需要检查旧 PID、处理会话退出并重新连接。原始 restore 快照曾保留已脱离 Proxy 的旧 Session；后续进程快照已显示新的正常 Proxy/Session，用户也确认远端考试内容恢复。不能仅凭 `bootstrap` 返回成功就判断全部旧 hook 已退出。

## 尚未验证与产品化限制

- 当前真实远端验证覆盖本机 ToDesk 的本次 SCK 显示器捕获路径，以及静态考试窗口范围；不覆盖所有 ToDesk 功能、版本或系统版本。
- 静态导入发现的 CGDisplayStream、传统 CoreGraphics 或其他后端，不能因这次 SCK 成功而算作 ToDesk 实机已覆盖。
- 多显示器、旋转、缩放、窗口移动/调整尺寸、最小化、遮挡、已有流切换、快速重连、睡眠唤醒、用户切换等尚无完整矩阵。
- 原生输入控件确实存在，但中文输入法候选窗、右键菜单、下拉菜单、选区和独立系统弹窗是否处于遮蔽范围，需要专项远端验证。系统独立窗口不能自动归入考试窗矩形。
- 抽样进程日志与人工观察不能排除短暂漏帧；本轮没有保存接收端视频做全帧像素检查。
- 当前实现遇到不支持的像素格式、无法确定范围或部分处理失败时可能保留原样输出。此 PoC 的“block”不等于已经实现失败即阻止输出的生产策略。
- 动态库能够加载依赖本机 ToDesk 签名中的相关运行时例外、用户级启动路径及相应子进程继承；不能推广为 UU 或任意加固应用都可以安装 hook。
- 用户级启动任务替换发生过真实 bootstrap 竞争。稳定部署必须解决任务生命周期、旧子进程、更新与恢复，而不只是提供一次成功加载命令。
- 本轮重点验证外部捕获进程拦截。新原生 Demo 的自身录像链路尚未在这里完成编码与回放验证，不能套用上一版受保护画布 Demo 的录像结果。

## 可复核入口

- [用户级代理实验脚本](../scripts/todesk-proxy-instrument.py)
- [Hook 实现](../Sources/CaptureHook/CaptureHook.m)
- [原生目标应用](../Sources/NativeExamDemo/main.swift)
- [audit 状态与恢复记录](../artifacts/todesk-audit-20261101T134436Z/instrumentation-state.json)
- [失败 block 轮次](../artifacts/todesk-block-20261101T135028Z/instrumentation-state.json)
- [成功 block 轮次](../artifacts/todesk-block-20261101T135207Z/instrumentation-state.json)

本文件根据已存在的日志、用户确认和只读哈希核验整理；编写阶段没有重新连接、启动、停止、注入或修改 ToDesk 进程，也没有重复进行捕获实验。
