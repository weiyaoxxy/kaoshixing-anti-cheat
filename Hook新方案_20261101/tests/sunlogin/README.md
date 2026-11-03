# 向日葵合成双窗口目标

独立 AppKit 目标，不检查 UU，不采屏、不读取其他应用内容。测试区域显示随机编号、动态计数和按钮；公共窗口显示相同编号及独立可见的动态计数。两个窗口默认置前，公共窗口不纳入遮蔽配置。

```bash
xcrun swiftc -swift-version 5 -O -target arm64-apple-macos13.0 \
  -framework AppKit -framework CoreGraphics \
  tests/sunlogin/RemoteProbe.swift -o build/SunloginRemoteProbe
build/SunloginRemoteProbe /absolute/path/to/new-output-directory
```

构建输出应使用不存在的新路径，避免替换运行中的历史产物。运行输出目录必须不存在，父目录必须存在。默认 3600 秒后自动退出；短时自检可加 `--duration 3`，接受 1–3600 秒。关闭测试区域或应用退出会停止整个探针。

- `state.json`：schema 1；PID、随机 marker、tick、clicks、时间、active、两窗口 ID/ownerPID/可见状态及 CoreGraphics 屏幕 point 坐标。`inputOriginVerified=false`，按钮计数不证明输入来自远端。`screenPixelsCollected=false`。
- `hook-config.json`：schema 1；仅测试窗口的 windowID、ownerPID、bounds、enabled。退出、不可见或无法取得有效范围时 enabled=false。正常退出最终状态仍保留供复核。

文件原子更新，目录权限 0700，JSON 文件权限 0600。只从 CoreGraphics 请求这两个已知自有窗口的元数据。配置更新时间与捕获帧不同步，因此只作为固定范围实验目标，不构成无泄露保证。退出时关闭自己的窗口，不负责恢复任何第三方注入配置；调用方必须单独完成远控环境恢复。

## 独立只读进程身份读取器

```bash
xcrun swiftc -swift-version 5 -O -target arm64-apple-macos13.0 \
  -framework Foundation -framework QuartzCore \
  Sources/SunloginProcessInventory/main.swift -o build/SunloginProcessInventory
build/SunloginProcessInventory
build/SunloginProcessInventory --pid 12345
```

默认通过 libproc 的真实可执行路径，仅输出 `/Applications/AweSun.app/` 和 `/Library/Application Support/Oray/AweSun/AweSun.app/` 内进程。读不到路径的向日葵候选或无法辨认的 PID 保留为 unresolved；其他已辨认名称用于排除无关候选，不当作可执行路径证据。`--pid` 只读取指定 PID，可用于控制器自己启动的合成窗口；调用方仍须检查精确路径、UID 和出生身份再决定任何后续动作。

stdout 单行 JSON，schemaVersion=1：`mode`、`observedAtUTC`、`observedHostTime`（CACurrentMediaTime）、`complete`/`enumerationComplete`、`processes`、`unresolved`、`systemMutationPerformed=false`。每项进程包含 `pid`、`parentPID`、`uid`、`executable`、`startTimeSeconds`、`startTimeMicroseconds`、`role`。role 只是路径分类，不证明正在取屏或远控。

出生身份优先来自 `PROC_PIDTBSDINFO`，受限时使用只读 `KERN_PROC_PID`。每项会重复查询并比对路径、UID 和出生时间；不把 parentPID 变化当作进程换代。读不到、进程消失/变化和枚举容量不足分别保留未知，不作缺席证明。返回码 0 为检查完整，2 为不完整，64 为参数错误；既不读取命令行参数或环境，也不采集进程内存或进行任何终止/启动操作。两次快照仍不能提供跨任意操作的原子身份保证。
