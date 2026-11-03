# UU 连线后的实际取屏路径验证

更新日期：2026-11-01。属于独立 Hook 新方案的后续运行验证。此前交付的 Word 1.0、加载负结果报告及原始证据均保留；本次新增证据不覆盖旧记录。

## 1. 新增结论

**用户已确认 UU 远端连接正常，原生题目可见，公共 LIVE-TICK 持续变化。连接期间的实际采样显示：UURemoteServer PID 84053 使用 ScreenCaptureKit / SCStream 接收视频样本，并进入 libstreamer 的 SCK 捕获与帧处理函数。** 同一进程的其他队列还采样到 VideoToolbox 编码活动。

这把“UU 当前实际捕获后端”从上一版的未确认，推进为“此次会话已观察到 SCK”。**UU 仍未加载本项目 hook，也没有实现遮蔽。** 找到了实际路径，不等于已经取得在该进程中安装拦截器的能力。

| 问题 | 更新后的状态 |
|---|---|
| 原定义恢复后 UU 能否连接并正常显示 | 用户已确认此次连接题目可见、公共计数变化；不等于全部远程功能验收 |
| 本次捕获宿主 | UURemoteServer PID 84053，有真实捕获调用栈 |
| 本次捕获后端 | 已观察到 ScreenCaptureKit / SCStream 的视频接收路径 |
| 帧处理及编码 | libstreamer 帧处理与 VideoToolbox 编码活动均在该进程被采样到，未取得端到端同一帧追踪 |
| 原版 UU 启动加载限制 | 先前 GUI / Service / 新 Server 最小库未加载的结果保持不变 |
| UU 远端遮蔽 | 尚未实现；本次正常可见是未 hook 的运行对照 |
| UU 是否只用 SCK、是否会回退传统 CG | 未验证；有限样本不能排除其他后端 |

## 2. 用户观察、时点与原始资料

用户原始反馈：**“已连接 UU，题目可见，计数在变化”**。

反馈于 UTC 14:41:07（Asia/Calcutta：20:11:07，UTC+05:30）保存到 [human-observation.json](../artifacts/uu-live-connected-20261101T144107Z/human-observation.json)。这是记录时间，不将其当作远端连接建立的精确时刻。没有提供接收端截图或录像，不能把本地截图替代为远端证据。

随后对三个当前用户进程同时各采样 4 秒，三个 sample 命令均返回 0：

| 对象 | PID / 父 PID | 观察到的特定捕获栈 |
|---|---|---|
| UURemoteServer | 84053 / 84016 | SCK 视频接收、libstreamer 帧处理；另有编码队列 |
| UU GUI | 84593 / 1 | 本采样窗未命中；有通用 libstreamer 后台函数，不能称为 GUI 正在取屏 |
| UURemoteService | 84016 / 1 | 本采样窗未命中 |

资料目录：[uu-live-connected-20261101T144107Z](../artifacts/uu-live-connected-20261101T144107Z/)。三份原始 sample、进程身份快照、人工反馈、结构化提取及独立复核均保存于该目录。取样期间没有重启服务、切换模式、修改应用文件或向进程安装库。

## 3. 实际调用栈能支持什么

[Server 原始采样](../artifacts/uu-live-connected-20261101T144107Z/server-sample.txt) 的 1429–1436 行所在分支，包含以下祖先/后代关系；中间存在未符号化桥接函数，箭头不表示每一项都是紧邻的直接调用：

```text
SCStream(SCContentSharing) startRemoteVideoReceiveQueue: 的回调
  → streamer::capture::ScreenCapturerSck::OnReceiveVideoSampleBuffer
    → streamer::capture::DesktopScreenCapturer::OnFrameCallback
      → streamer::VideoPreprocessSource::OnFrame
        → streamer::IOSurfaceFrame::CopyFrom
```

这是活跃调用栈中的函数，而不是文件字符串或 Binary Images 里加载框架的名字。因此可以支持“此时 UU Server 实际走了 SCK 视频接收及帧处理路径”。原始系统内部方法名只是采样证据，本项目没有把它当作公开 API 主动调用。

同一 Server 的其他队列还出现 `streamer::IOSurfaceFrame::CopyTo`、`Texture` 与 `VTCompressionSessionEncodeFrame`。编码活动分别位于 EncoderQueue 和 compressionQueue 的采样分支，**不能与上面的接收分支拼成一条同步、逐帧确认的完整调用链**。本次没有视频帧身份关联、像素格式断言、帧率或端到端延迟测量。

统计采样前的数字表示采样统计，不能当成帧数、接口调用次数或每秒帧率。结构化提取中的“9 条捕获匹配行、15 条帧处理匹配行、3 条编码匹配行”同样只是文本行数，不是处理数量。

- [精简结构化证据及原始文件 SHA-256](../artifacts/uu-live-connected-20261101T144107Z/specific-evidence.json)
- [带原始行号的接收栈摘录](../artifacts/uu-live-connected-20261101T144107Z/capture-stack-excerpt.txt)
- [独立证据复核](../artifacts/uu-live-connected-20261101T144107Z/review.json)

本窗口没有命中 CGDisplayStream 或传统 CG 单帧接口，不能推断它们永不使用。GUI 和 Service 的空匹配也只适用于这 4 秒采样窗，不能排除其他操作、其他时刻或其他版本的捕获路径。

## 4. 正常启动状态与 Hook 结论

[连接期间任务检查](../artifacts/uu-live-connected-20261101T144107Z/job-during-connection.json)确认 `gui/501/com.netease.uuremote.agent` 仍从原 `/Library/LaunchAgents/com.netease.uuremote.agent.plist` 运行，Service PID 84016，状态 running，实验 DYLD / HOOK_DEMO 环境键为空。

[当前库映射检查](../artifacts/uu-live-connected-20261101T144107Z/current-library-mapping-check.json)确认当前三个 PID 的 vmmap 均返回 0，均未找到 libCaptureHook 或 libLoadWitness 映射，不使用先前 PID 的结果冒充当前状态。

此前 [UU 加载验证](UU加载验证.md)记录的是启动时安装最小库的两个入口均未成功；本次连接是在恢复原定义之后。这是两个独立实验条件，没有因为正常连通就撤销加载负结果，也没有在连接中重新执行加载实验。

先前目标 Server 72316 与当前 Server 84053 的 PID 不同，不能把某次采样写到另一进程上。加载负结果回答“该原版启动方式能否加载库”；当前运行栈回答“此次正常连接正在使用什么捕获路径”。两者共同说明：后续若继续开发 UU hook，应以实际 Server/SCK 为重点，同时先解决受支持的加载或厂商集成条件。

## 5. 对当前新方案的影响

ToDesk 的实机三阶段遮蔽结果保持不变。UU 现在具备“原生目标真实可见、动态对照变化、实际 SCK 捕获宿主确认”的运行基线，仍缺少“库实际进入宿主、捕获回调受控、输出改变、远端遮蔽及恢复”的闭环。

当前不需要因发现 SCK 就扩大系统权限或改签 UU；捕获接口已经定位，但本项目未实现跨越宿主签名限制的通用加载能力。报告 v1.1 更新这项事实，保留 v1.0 便于审阅比较。
