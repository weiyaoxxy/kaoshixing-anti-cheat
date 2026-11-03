# 原版 UU 外部采集路径验证

该工具对原版当前用户的 UU GUI / Service / Server 作短时运行栈诊断，用于确认已知的 ScreenCaptureKit 视频回调与 libstreamer 接收处理是否出现在同一调用分支。它不加载 Hook，不重签或重启 UU，不改变 launchd，不记录进程参数、凭据或屏幕像素。

`sample` 会短暂挂起/恢复线程，因此不是完全无干预的观察。默认每次 3 秒、5 毫秒间隔；采样可能漏掉短调用，也可能影响时间行为。结果不能用于声称零漏检、有效帧、已建立远控或 Hook 已命中。

## 构建

从 `Hook新方案_20261101` 目录执行：

```sh
swiftc -O Sources/UUProcessInventory/main.swift Sources/NativeExamDemo/UUHookMonitor.swift -o build/UUProcessInventory
swiftc -O tests/uu-capture-path/RemoteProbe.swift -framework AppKit -o build/UUCapturePathRemoteProbe
```

Inventory 复用现有原生进程身份读取器；采样器仅允许固定 `/Applications/UURemote.app` 下的当前用户目标，并在执行前验证磁盘签名及厂商 Team ID。root Daemon 只列为清单信息，不采样、不自动申请提权。

## 三阶段对照

```sh
python3 scripts/observe-uu-capture-path.py --phase idle --roles gui service server --rounds 2 --output artifacts/NEW-RUN-idle
python3 scripts/observe-uu-capture-path.py --phase connected --roles gui service server --rounds 2 --output artifacts/NEW-RUN-connected
python3 scripts/observe-uu-capture-path.py --phase disconnected --roles gui service server --rounds 2 --output artifacts/NEW-RUN-disconnected
```

每次输出目录必须不存在。`--phase` 只是由操作者填写的标签，不会自动连接或判断 UU 状态：必须由真实第二台设备确认未连接、连接并看到动态内容、断开三个条件。远端看到的测试编号、计数变化和按钮操作另外记为人工观察；不能从运行栈反推出这些事实。

`--phase preflight` 仅记录原始程序/库/启动 plist 哈希、运行进程和用户任务状态，不调用 sample。第一次实验应保存完整基线；阶段间也检查这些原始文件和任务未改变。

可用 `build/UUCapturePathRemoteProbe NEW_STATE_JSON` 显示只含合成编号、动态计数和按钮的测试窗口。它不读屏；状态中的点击次数不自行认定输入来自远端。窗口置前显示，可手动关闭，3600 次每秒计时更新后自动退出。首轮窗口的旧 1200 次期限在等待人工反馈时已到期，因此本轮延长并另用新状态文件保留旧记录。

## 证据与失败处理

- 每次采样前后核对 PID、UID、实际路径和微秒级出生时间；磁盘可执行文件摘要也必须一致。身份不符时分析为无效，不复用旧进程证据。
- 原始 sample 报告只在 0700 临时目录中短暂存在；完成后删除。永久保存原文摘要、外部身份清单和只包含固定类别/必要符号的分析结果。新样本原文未保留，因此后续不能重新对整份原文运行不同解析器；摘要也不是独立的真实性证明。
- `path_observed` 要求同一调用分支中的 SCK 视频接收回调和 libstreamer 的 `ScreenCapturerSck::OnReceiveVideoSampleBuffer`。Binary Images 的加载列表、兄弟分支、不同线程、泛型编码栈均不能代替这条链。
- `path_not_observed` 只表示本窗口没有采到这条已知路径；其他采集后端和瞬时事件仍可能存在。
- 采样次数/栈权重不是帧数。编码与 IOSurface 路径另列为旁证，不能拼成同一帧的端到端证据。
- `captureHookHitVerified`、`validFrameVerified`、`remoteSessionVerified` 始终为 false；人工远端反馈单独存储。
- SIGINT/SIGTERM 请求停止采集器时，让当前有限时采样自然完成，再停止后续采样。工具超时才向我们启动的 sample 子进程发 SIGINT，停止后续工作并要求检查连续性；不向 UU 发 SIGCONT，也不直接 SIGKILL sample。子工具未确认退出时报告 `sampleToolCleanupUnconfirmed`。
- 有关“正常退出后身份/哈希仍一致”的结果不代表远端会话从未被短暂影响，必须结合远端反馈。工具超时后的行为尤其不能只靠进程存在判断。
- 每次尝试先写入结果占位，后续更新；末尾各项核验独立执行，不能把核验失败变成 `unchanged=true`。磁盘完全不可写时无法保证报告落盘，应保留控制台失败并停止使用该结果。

`summary.json` 中检查 `collectionComplete`、`error`、`finalCheckErrors`、逐样本状态及外部连续性。较早的本轮 idle 采集发生在增加 `collectionComplete` 字段之前，该字段缺失不能当 true，需按逐项证据判断。CLI 退出码 0 仅代表执行未发生致命错误，不代表发现了采集或某种防护成功。

## 验证

```sh
python3 -m unittest discover -s tests -p test_uu_capture_sample.py -v
python3 -m unittest discover -s tests -p test_uu_capture_collector.py -v
```

解析器测试含真实历史样本和跨线程/跨分支/错误身份等负例；采集器测试使用合成输出，验证身份变化、权限前置条件和失败记录，均不接触实时 UU。独立自有 heartbeat fixture 的 sample 中断测试位于 `tests/uu-capture-path/test_sample_cleanup.py`，只验证其具体本机测试路径，不能外推为任何异常中断都安全。
