# 原生考试窗口：新 hook 路线的捕获目标

此应用使用真实 `NSWindow`、可编辑 `NSTextField`、`NSTextView`、单选 `NSButton`、`NSPopUpButton` 和 `NSScrollView`。窗口共享类型明确为 `readOnly`，没有受保护视频图层、DRM、屏幕捕获过滤器或窗口共享禁用开关。

考试窗显示 `NATIVE-EXAM-SECRET-HOOK9`，其中包括真实原生文字输入、选择、滚动及弹出菜单。独立对照窗显示 `PUBLIC-CONTROL-HOOK`，每秒更新 `LIVE-TICK-xxxx` 和色块。对照窗用于识别全屏黑图、卡帧和断流；它不在 hook 配置的遮蔽目标中。

## 构建与运行

```bash
bash scripts/build-native-demo.sh
open -n build/NativeExamHookDemo.app --args --output /tmp/native-hook-new-run
```

`--output` 必须是新目录或空目录，拒绝覆盖历史记录。省略时自动在本项目 `artifacts` 下生成唯一目录。`--duration 15` 在 15 秒后退出；默认 `0` 保持运行。关闭考试窗或选择应用退出会结束程序，关闭对照窗只关闭该对照窗。

`--auto-type` 每两秒程序化修改短答字段，便于确认帧持续变化。**它不注入键盘事件，不能证明用户实际键入、焦点或中文输入法已验证。** 这些行为需要人工或独立事件实验。应用允许原生输入法和编辑交互，但其捕获保护表现尚需实际测试。

仅输入合成测试内容。输入文字会写入本次运行的状态文件。此应用不读取其他窗口内容，不自动录制、不自动获取屏幕捕获权限。

## 输出协议

每秒以及编辑、点击、窗口移动等事件后，应用原子更新 `state.json` 和 `hook-config.json`。`state.json` 包含两个窗口的 ID、owner PID、可见性、共享类型及通过 `CGWindowListCopyWindowInfo` 获取的屏幕坐标；以及原生输入值、选项、动态对照计数、OS、事件计数和时间。`textEditNotifications` 与程序化 `automaticTextUpdates` 分开记录。

`hook-config.json` 仅包含考试窗口目标；示例：

```json
{
  "schemaVersion": 1,
  "enabled": true,
  "windowID": 12345,
  "ownerPID": 1234,
  "bounds": {"x": 24, "y": 48, "width": 850, "height": 722},
  "windowTitle": "NativeExamHookDemo — 原生考试窗口",
  "scope": "single_exam_window",
  "timestamp": "2026-11-01T12:00:00Z"
}
```

`bounds` 是 CoreGraphics 窗口边界坐标（桌面 point 坐标，含窗口装饰），不是 Retina 像素数或 AppKit 左下角坐标。捕获端必须正确处理显示器原点、采样尺寸、缩放和坐标转换。窗口移动会更新配置；最小化、不可见、取不到有效坐标和正常退出会将 `enabled` 设为 `false`。该字段只是测试目标状态，不能把它当作生产保护策略的可靠性保证。

本目标自身不实施保护。只有独立捕获进程中 hook 实际改变其输出，并且原生秘密消失、公共对照继续更新，才能支持某个捕获入口的拦截结论。`state.json` 成功生成和应用正常启动本身不证明防捕获成功。


## 客户端完整性与 UU Hook 检测

新增 `RuntimeIntegrityMonitor.swift`、`RuntimeImages.c` 和 `UUHookMonitor.swift`，应用启动后、每 5 秒发起一轮检查。检查使用独立定时器，不依赖被监测的 `tick()`。耗时检查在后台串行执行；已有扫描未完成时不堆积新扫描。界面更新会等待扫描完成。UU 单轮预算约 9 秒，可能跨过一个刷新周期；时间戳表示最近一次结果，不能当成实时保证。

构建到独立目录，避免覆盖正在运行的旧 Demo：

```bash
bash scripts/build-native-demo.sh "$PWD/build/NativeExamIntegrityDemo.app"
open -n "$PWD/build/NativeExamIntegrityDemo.app" --args --output /tmp/exam-integrity-new-run
```

无窗口检查（仍会只读检查运行中的 UU）：

```bash
build/NativeExamIntegrityDemo.app/Contents/MacOS/NativeExamHookDemo \
  --integrity-probe --duration 12 --output /tmp/exam-integrity-probe-new-run
```

`--integrity-probe` 最后向 stdout 输出一份 JSON，便于在输出目录不可写时检查回调结果；提前结束可能仍有 `checking` 项，不代表检查通过。完整自测仅注入自己的临时 Demo 副本，包含正常启动、测试库注入、方法替换后恢复、动态库加载后卸载、应用资源修改后恢复、修改后重新临时签名、日志写入失败、原生窗口更新和界面 tick 被替换后独立检测继续运行：

```bash
python3 scripts/test-runtime-integrity.py "$PWD/build/NativeExamIntegrityDemo.app" /tmp/integrity-scenarios-new
```

### 自身检测

- 通过 dyld 加载回调保存已观测模块路径，包括监测启动后已卸载的模块；此 Demo 不支持第三方插件，非预期模块标为待复核。系统目录依赖系统完整性边界，不是对已攻破系统的证明。
- 检查影响加载的环境变量，只记录变量名；存在变量说明配置异常，不单独证明注入已执行。
- 检查应用运行签名及磁盘 bundle 的严格签名封装，签名相关信息、校验失败和查询失败分别记录。
- 监测 `persist`、`tick`、`submitAnswer:`、`NSApplication.sendEvent:` 的 ObjC 实现归属、IMP 和入口前 32 字节的变化。其他方法、纯 Swift 调用、任意内存补丁不在完整覆盖范围内；启动前的同映像修改也可能逃过本地基线。
- `integrity-status.json` 保存当前状态；`integrity-events.jsonl` 保存带 sessionID、PID、时间和序号的检查变化及异常。异常一旦发现会持续标记到本次进程结束，恢复原方法/文件不会清除记录。正常退出仍将检测结果保存在 `state.json`。

状态有 `anomalyObserved`（需复核）、`incomplete`（部分检查不能确认）、`noAnomalyObserved`（本轮没有发现已覆盖异常）。这些状态不等于作弊裁决。输出失败通过回调/UI状态标记为不完整；磁盘不可写时无法保证持久化该失败。

**默认构建仍为 ad-hoc 开发签名，没有可信发行身份，`releaseIdentity` 为 unknown。** 修改后重新 ad-hoc 签名可能通过本地签名校验，不能将其宣称为原版。构建时可同时设置 `EXAM_SIGN_IDENTITY` 和 `EXAM_EXPECTED_TEAM_ID`，后者会编译入 Apple 签名链、bundle ID 和 Team ID 要求；它不接受运行参数覆盖。这个要求本身仍可被替换客户端的攻击者移除。本脚本未自动开启 Hardened Runtime，生产发行需要另行配置、签名与验证；不要把注入测试用权限带入生产。

### UU 检测

只读识别 GUI、Service、Server、Daemon，记录真实路径、PID 和启动时间，并用 `vmmap` 检查当时的可执行模块映射。名称匹配 `libCaptureHook*.dylib` 的结果为 `observedLoaded`；`libLoadWitness*.dylib` 单独记录，不能当成保护 Hook。库名匹配不能证明库内容可信，也不能检测所有改名库或其他注入方法。

`noKnownHookObserved` 只表示成功读取的映射中未发现已知名称。权限不足、进程退出/换代、输出截断、超时或枚举失败均为 `unknown`。`notRunning` 需要成功枚举后未找到相应组件。`uu-hook-status.json` 和 `state.json.uuHook` 保存结果，`uu-hook-events.jsonl` 追加进程身份/状态/模块证据变化历史；实际调用/遮蔽效果始终单独标为未验证。不会从历史日志推断当前进程已加载 Hook。

检测器不启动、停止、注入、重新签名或恢复 UU，不改变 launchd、网络和隐私权限。仅检查本地内存映射不能证明远程连接正常或考试画面已被遮蔽。

所有记录仅在本机。拥有最高权限或已控制客户端的人可能修改检测器、伪造或删除日志。目前没有服务端事件接收、心跳、远程证明或可信存证。接入服务端后可保留已经收到的记录、标记心跳缺口，但不能由缺口直接认定作弊。
