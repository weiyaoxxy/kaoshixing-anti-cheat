# UU Hook 只读监测

`UUHookMonitor.swift` 独立于界面，最低目标 macOS 13，使用 Foundation/Darwin。把文件加入现有 Swift 编译输入即可。

```swift
let monitor = UUHookMonitor(output: outputDirectory.appendingPathComponent("uu-hook-status.json"))
monitor.refresh { report in
    // 保证主线程；report["summary"] 是面向界面的中文说明。
    statusLabel.stringValue = report["summary"] as? String ?? "UU 状态未知"
}
```

`output` 指向 JSON 文件。监测在后台串行队列执行，正在检查时的新请求共享同一次扫描，避免定时刷新累积。扫描工具预算为 9 秒；超时收尾至多再用约 0.6 秒。原子写入 JSON；不能写入时仍回调，并设置 `reportWriteSucceeded=false`。应用必须保持主线程 RunLoop 运行，才能收到回调。

同目录的 `uu-hook-events.jsonl` 保存状态变化历史。按角色、PID、微秒级创建时间、结果、模块文件名证据和签名元数据去重，忽略刷新时间和区域数量；进程退出、更换、由加载变为未观察到等变化会追加事件。`historyWriteSucceeded=false` 表示无法写历史。历史与快照均为本地可修改文件，不是防篡改日志或远程证明。

## 状态含义

| status | 含义 |
| --- | --- |
| `observedLoaded` | 至少一个当前进程的可执行 `__TEXT` 映射命中已知 `libCaptureHook*.dylib` 文件名。文件名可以被仿造，未证明库真实性或捕获拦截。 |
| `noKnownHookObserved` | 已成功检查的当前映射未发现已知 CaptureHook 文件名；不能排除改名模块、内存补丁或其他注入方法。 |
| `unknown` | 权限、超时、输出截断、进程身份变化、工具格式或枚举覆盖等原因导致无法确认。 |
| `notRunning` | 完成枚举后未发现对应 UU 进程；枚举不完整时不使用此状态。 |

`processes` 为每个真实 PID 提供路径、UID、父 PID、微秒级进程创建时间、模块证据和签名元数据。`components` 汇总 GUI、Service、Server、Daemon。总体状态优先报告已观测到加载；其余存在无法检查的进程时为 `unknown`。典型情况下三个用户进程可检查，root Daemon 的映射权限不足，因此总体为部分未知；这是正常、诚实的结果，不会申请提权。

枚举使用 `proc_listallpids` / `proc_name` / `proc_pidinfo` / `proc_pidpath`，从精确 UU 可执行文件名识别候选并记录实际路径；libproc 不允许读取 root 进程名称或 BSD 信息时，后备使用只读 `sysctl(KERN_PROC_PID)` 获取名称和微秒级创建身份。不把仅同名程序当作已认证的厂商应用。`codesign -d` 只提供当前磁盘文件的公开身份元数据，不验证其签名有效性，也不证明正在运行的代码可信。`launchctl print` 仅查询本用户 Service 与系统 Daemon；仅保留路径、程序、状态、PID 及实验环境键名称，不输出环境值或完整参数。

每次 `vmmap -w PID` 前后用 PID、UID、路径和微秒级创建时间约束证据，拒绝 PID 重用、退出或换进程的结果；并核对 vmmap 的进程头。工具若把临时目录头路径脱敏为 `*`，还必须从未脱敏的主程序 `__TEXT` 区域核对真实路径。仅接受可执行 `__TEXT` 区域中的准确模块文件名，不把普通文件映射、工具头或日志文本作为加载证据。`libLoadWitness` 独立记录为 witness，不等同于 CaptureHook。`knownHookIdentityVerified=false`、`moduleNameMatchOnly=true` 明确表示未认证库版本或内容。

不读取历史 hook 日志。`actualHookInvocationVerified=false` 和 `captureBlockingVerified=false` 始终明确指出：加载不等于安装成功、实际捕获调用、输出改变或远端拦截成功。

## 隐私与运行边界

模块不会启动、结束、注入、重签或重新配置 UU；不修改 launchd、网络或权限，不发送远程连接请求。超时终止的只是监测器自己创建的 `vmmap`、`codesign` 或只读 `launchctl print` 子进程。子工具环境不继承 DYLD/HOOK 实验变量。

原始命令输出只在内存短暂解析，不写入报告；没有账户、设备码、密码、完整参数、环境值或 vmmap UUID 头信息。路径中的标准 UUID 字符串会替换为占位符。报告保留可读的应用/模块路径，文件权限设置为 0600。

扫描是连续的短时观察，不是整个系统的原子快照；检查之后进程仍可能变化。该模块不是防篡改信任根，不应据此声称所有远程工具都被发现或考试内容安全。

## 验证

```bash
bash scripts/test-uu-hook-monitor.sh
bash scripts/test-uu-hook-monitor.sh --live /tmp/uu-hook-monitor-live.json
```

默认测试覆盖解析、权限失败、超时、输出截断、PID 重用、文件名误报、普通文件映射、witness 区分、JSON 格式、历史去重/状态变化及工具双管道输出。还向测试进程自己加载一个无行为的自有 fixture dylib，再用真实 vmmap 验证正例。不会向 UU 加载 fixture。

`--live` 额外只读检查本机 UU，检查主线程回调、合并刷新、预算内完成与报告写入，并报告前后 UU 进程生命期是否一致。临时测试程序和 fixture 会清理，指定 JSON 保留。
