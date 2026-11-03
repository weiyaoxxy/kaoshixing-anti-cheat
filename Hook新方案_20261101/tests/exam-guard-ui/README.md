# 考试门禁 UI 与管道协议验证

这些测试仅操作新构建的自有 AppKit Demo 与模拟守护进程，不枚举、终止或恢复真实远控。模拟结果不能作为管理员处置、真实上报或实际远端遮蔽的证据。

默认构建只显示准备页，未收到对应会话的新鲜、递增且合格的守护状态前，不创建题目控件。只有用户明确开始/继续后，才允许后续合格的 `exam` 状态显示合成试题。坏消息、会话不符、重复序号、心跳断流和子进程退出都会收起题目；断流后的新状态也不自动恢复旧考试。

## 构建和运行

构建脚本默认使用唯一新目录，拒绝覆盖已有 app。下列命令在 `Hook新方案_20261101` 下运行：

```bash
bash scripts/build-native-demo.sh
```

真实守护集成运行需要指定实际产物：

```text
NativeExamHookDemo --output NEW_DIRECTORY
  --guard-runner /absolute/scripts/exam-guard.py
  --guard-inventory /absolute/RemoteProcessInventory
  --guard-policy /absolute/policy.json
  --guard-worker /absolute/ExamGuardService
  --guard-vendors uu,todesk,sunlogin
  --guard-worker-lease 180
```

`--guard-python` 默认 `/usr/bin/python3`。产品选择仅用于本机开发验证，准备页始终显示范围；管理员服务仍需独立核验策略。父进程不给 GUI root 权限。没有可用守护或检查不合格时保持准备/暂停。

模拟测试需单独编译：

```bash
EXAM_ENABLE_GUARD_TESTING=1 bash scripts/build-native-demo.sh
python3 tests/exam-guard-ui/run-ui-tests.py --app NEW_TEST_APP --output NEW_REPORT_DIRECTORY
```

仅此测试构建接受 `--guard-test-mode` 和 `--guard-test-auto-start`，并醒目标注模拟模式。普通构建拒绝这些选项。历史 Hook 对照若确需重建，需另设 `EXAM_ENABLE_LEGACY_HOOK_DEMO=1` 才接受 `--legacy-hook-demo`；普通构建不提供此绕过门禁入口，既有历史二进制不被替换。

纯协议测试可以单独编译，不启动 GUI：

```bash
xcrun swiftc -swift-version 5 Sources/NativeExamDemo/ExamGuardClient.swift tests/exam-guard-ui/ProtocolTests.swift -o /tmp/NEW_UNIQUE_TEST_BINARY
/tmp/NEW_UNIQUE_TEST_BINARY
```

## 管道契约

GUI 以普通用户启动 `exam-guard.py --ui-protocol --ui-session-id UUID --session-dir NEW_DIRECTORY --inventory PATH --policy PATH`。可附加 worker、vendors、worker-lease。stdin 每行一个命令对象，包含 `protocolVersion=1`、`sessionID`、`requestID` 和 `command`；允许命令为 `inspect/requestAuthorization/start/resume/pause/end`，无任意命令执行接口。

stdout 仅接受 JSON 行状态：

```json
{
  "protocolVersion": 1,
  "type": "status",
  "sessionID": "the-gui-generated-session-id",
  "sequence": 1,
  "state": "ready",
  "canStart": true,
  "examAllowed": false,
  "health": "healthy",
  "message": "检查通过，等待开始考试"
}
```

序号须为正整数并递增；布尔值必须是 JSON 布尔类型，不能用数字或字符串替代。`examAllowed=true` 只在 `state=exam, health=healthy` 时可接受；`canStart=true` 只在健康的 ready 状态接受。单帧限制 64 KiB，状态消息最多 8 KiB，3 秒无新鲜状态则暂停；该计时使用包含休眠的 `mach_continuous_time`。休眠/唤醒/用户会话切换通知立即暂停，不自动续考。命令管道非阻塞且单个写入限制在管道原子写入上限内，失败不冻结主线程。

结束先隐藏试题，发 `end` 并通过 AppKit 延迟退出等待 `finished`；15 秒未确认则取消退出，保持恢复未确认状态。用户可明确选择“退出界面（恢复未确认）”，此操作关闭普通 GUI 管道，不 kill 恢复进程，也不把未知结果写为成功。守护进程必须独立处理 EOF、有限租约和恢复。

guard 模式的 `state.json` 不含短答或长答；旧实验的答案保存仅存在于显式历史模式。输出目录权限为 0700。状态文件是本机测试观察，不是可信的服务端证明。

## 覆盖的测试方向

纯协议测试覆盖初始拒绝、ready 不显示题、未经用户开始的 exam、正常开考、过期、重新连接不自动续考、重复消息、跨会话、错误字段类型、无效状态组合、暂停、结束不可逆和倒退时钟。

AppKit 模拟集成测试覆盖 ready-only、正常开考/结束、暂停、断流、坏 JSON、重复序号、错误 session、超长帧、守护退出、进程内模拟休眠通知和结束无回执。模拟通知不使实际 Mac 休眠，不代替真实休眠/唤醒验收。每轮保存 UI 状态采样与子进程输出，断开后的测试 GUI 仅在断言完成后由测试控制器终止自身子进程；不会向第三方程序发送信号。

## 官方依据及边界

- [Apple mach_continuous_time](https://developer.apple.com/documentation/kernel/1646199-mach_continuous_time)：使用包含休眠的单调时钟核验心跳，避免休眠后继续复用旧许可；同时核对本机 SDK `mach/mach_time.h`。

- [Apple applicationShouldTerminate](https://developer.apple.com/documentation/appkit/nsapplicationdelegate/applicationshouldterminate(_:)) 与 [reply(toApplicationShouldTerminate:)](https://developer.apple.com/documentation/appkit/nsapplication/reply(toapplicationshouldterminate:))：延迟退出必须明确回复；仅在 `applicationWillTerminate` 中保存状态不足以等待异步恢复。
- [Apple orderOut](https://developer.apple.com/documentation/appkit/nswindow/orderout(_:))：从屏幕移除窗口不等于释放内容，更不能收回已被传出的画面。本实现同时禁用编辑、隐藏题目视图并收起本 App 的其他题目相关窗口；不声称能控制系统输入法窗口或已缓存画面。

该 GUI/runner 协议属于本机开发验证。允许开发者指定本地 runner 路径、私有管道和本地代码完整性检查，都不能提供对拥有本机高权限对手的远程可信证明。正式发布还需要受控签名、固定可信配置、真实后台服务部署与服务端准入。
