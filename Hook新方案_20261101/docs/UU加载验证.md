# UU 原版进程加载验证与恢复记录

证据日期：2026-11-01。对象为本机 `/Applications/UURemote.app`，UU 4.40.0（build 621）。本文件属于独立的 **Hook 新方案**，不沿用此前视频层保护 Demo 的结论。

## 1. 结论与验证状态

本轮没有在 UU 原版 GUI、用户级 Service 或其新派生的 Server 中观察到最小见证库 `libLoadWitness.dylib` 的加载。三个受查 PID 均没有 `image_loaded` 事件，且 `vmmap` 成功完成后也没有该库映射。**本轮“通过启动环境给 UU 加载实验库”的方式未得到加载成功证据，因而没有实现 UU 的捕获 hook 或远端遮蔽验证。**

这个负结果限于本机版本、原版签名和本次两个启动入口；不能写成“macOS 上所有注入技术均不可能”或“UU 所有版本都无法 hook”。本轮没有定位 dyld 每个阶段的具体拒绝原因，不能把某一个缺少的 entitlement 单独认定为唯一原因。

| 问题 | 状态 | 证据含义 |
|---|---|---|
| 最小见证库自身能否正常加载与写日志 | **已验证** | 自有宿主正对照通过；不是取屏测试 |
| UU GUI 启动时是否加载见证库 | **本轮未见加载** | PID 56546；0 事件、成功 vmmap 后 0 映射 |
| UU 用户 Service 是否加载见证库 | **本轮未见加载** | PID 72311；临时 job 确实启动，但 0 事件、成功 vmmap 后 0 映射 |
| 新 Server 是否加载见证库 | **本轮未见加载** | PID 72316，父 PID 72311；0 事件、成功 vmmap 后 0 映射 |
| UU 当前实际取屏入口 | **未验证** | 2 秒 sample 未捕获匹配调用栈；Binary Images 仅证明框架已装载 |
| UU 远端是否连接并收到遮蔽画面 | **未验证** | 尚未收到本轮人工远端连接确认，没有对应远端截图证据 |
| 临时用户 job、GUI 启动环境是否恢复 | **已验证元数据** | 原 `/Library` 定义运行、实验环境键为空；GUI 正常重开 |
| UU 恢复后远程功能是否完整可用 | **未验证** | 进程存在、启动返回 0 都不能代替实际连线 |

## 2. 先验证最小加载工具

[`LoadWitness`](../Sources/LoadWitness/README.md) 是纯 C 构造器动态库，只依赖 `libSystem.B.dylib`。它读取 `HOOK_DEMO_LOG`，尝试追加自己的 PID、UID、可执行路径与单调时钟；没有 AppKit、ScreenCaptureKit、CoreGraphics 依赖，没有 interpose / swizzle，不取屏、不修改帧、不访问网络。使用它可以减少完整 CaptureHook 的框架依赖、初始化或包装代码对“库到底有没有加载”的干扰。

库 SHA-256：

```text
27b1ed3b8136d2f260b09397cf2c04eaf4966293635d21e2fd5068b064f291ba
```

[`自测摘要`](../artifacts/load-witness-selftest-20261101T135819Z/summary.json)记载 5 项检查均通过，且自测没有启动第三方应用。关键正负对照为：

| 自有宿主条件 | 实际结果 | 原始记录 |
|---|---|---|
| 不设置 DYLD 注入，只有日志路径 | 宿主 PID 43908 正常退出，0 条日志 | [baseline.json](../artifacts/load-witness-selftest-20261101T135819Z/baseline.json) |
| 设置 DYLD 注入和有效日志路径 | PID 43932 正常退出，恰好 1 条与宿主 PID 匹配的 `image_loaded` | [injected.json](../artifacts/load-witness-selftest-20261101T135819Z/injected.json) |
| 缺少日志环境、日志父目录不存在 | 宿主均正常退出；见证器安静返回 | [missing-log-env.json](../artifacts/load-witness-selftest-20261101T135819Z/missing-log-env.json)、[unwritable-log-path.json](../artifacts/load-witness-selftest-20261101T135819Z/unwritable-log-path.json) |
| 宿主路径含中文、空格、引号和反斜杠 | 日志 JSON 可解析，路径正确还原 | [escaped-executable-path.json](../artifacts/load-witness-selftest-20261101T135819Z/escaped-executable-path.json) |

**没有日志本身不足以证明没加载**：日志路径不可写、环境未到达或进程很快退出也可能产生同样现象。因此本轮另核查了实际新 PID、进程存活状态和成功执行的 `vmmap` 库映射结果。正对照也不证明 UU 一定允许加载同一库。

## 3. 原版 GUI 启动环境实验

历史执行入口为 [`scripts/test-uu-load-witness.py`](../scripts/test-uu-load-witness.py)。脚本结束既有当前用户 GUI 后，以进程专属环境直接启动原版 `/Applications/UURemote.app/Contents/MacOS/UURemote`：

```text
DYLD_INSERT_LIBRARIES = 本项目 build/libLoadWitness.dylib
HOOK_DEMO_LOG = 本轮新目录中的 witness.jsonl
```

它没有改写或重签 UU 程序，也没有把实验环境设置为整个用户会话的全局环境。本次既有 GUI PID 89133 在请求正常退出后仍未结束，记录了针对该精确当前用户 PID 的 SIGTERM；随后新 GUI PID 为 **56546**。这是真实执行过的重启动作，不是单纯阅读文件。

[`result.json`](../artifacts/uu-load-witness-20261101T140503Z/result.json)显示检查时新进程尚未退出，`witnessEvents=[]`；[`mapping-check.json`](../artifacts/uu-load-witness-20261101T140503Z/mapping-check.json)显示 `vmmap` 返回 0，但 `witnessMappingLines=[]`。因此没有把“vmmap 权限失败导致空输出”误判为库未映射。

主程序前后 SHA-256 一致：

```text
235eb6415bc6828d05b87820869d40c9ebb5da268ebdd8ede8e4394c5f17f5e6
```

这只能说明本次启动环境方式没有使该 GUI 产生库加载证据。GUI 可能并非实际取屏宿主；已运行的独立 Service / Server 也不会因为 GUI 设置了环境就自动改变。因此继续单独验证用户服务入口。

## 4. Service 及新 Server 的加载检查

历史执行入口为 [`scripts/uu-service-instrument.py`](../scripts/uu-service-instrument.py)。本轮操作范围是 `gui/501/com.netease.uuremote.agent`：备份原定义，在项目目录生成临时 plist 副本，仅在副本中加入实验环境，卸载当前用户的原 job 注册并注册副本。原 `/Library/LaunchAgents/com.netease.uuremote.agent.plist` 文件没有被改写。

副本使用原 `UURemoteService -agent` 程序参数，并添加 `DYLD_INSERT_LIBRARIES`、`HOOK_DEMO_LOG`、`HOOK_DEMO_MODE=audit` 和 `HOOK_DEMO_CONFIG`。本次加载的是 **LoadWitness**，其中 mode/config 不参与逻辑，不能把 plist 里的 `audit` 当成捕获 hook 已安装。原始定义和实验定义分别见 [`original-job.plist`](../artifacts/uu-service-witness-20261101T141332Z/original-job.plist)、[`instrumented-job.plist`](../artifacts/uu-service-witness-20261101T141332Z/instrumented-job.plist)。

[`instrumentation-state.json`](../artifacts/uu-service-witness-20261101T141332Z/instrumentation-state.json)记录 UTC 14:13:32 的 bootout/bootstrap 均返回 0，实验 job 从项目副本运行，Service PID **72311**。刚启动时快照仍包含既有 Server；后续 [`load-check.json`](../artifacts/uu-service-witness-20261101T141332Z/load-check.json) 在 UTC 14:13:45 明确观察到新 Server PID **72316**、父 PID **72311**，避免仅检查旧 Server 导致归因错误。

| 组件 | PID / 父 PID | 检查结果 |
|---|---|---|
| GUI `UURemote` | 56546 / 1 | vmmap 返回 0；见证库映射 0 |
| `UURemoteService` | 72311 / 1 | vmmap 返回 0；见证库映射 0 |
| 新 `UURemoteServer` | 72316 / 72311 | vmmap 返回 0；见证库映射 0 |

该轮见证事件总数为 0。**job 注册成功、服务在运行、新子进程出现，都没有被计作库加载成功。**本轮没有对 root Daemon 或特权 Helper 安装见证库，也没有通过关闭 SIP、修改系统文件或重签第三方应用绕过原版部署条件。

已有[静态分析](远程软件静态分析.md)记录 UU 对应组件启用 Hardened Runtime，且未声明与本实验启动环境方式相关的运行时例外。该信息与加载负结果相容，但没有独立证明究竟是环境清理、dyld 策略、库校验还是其他启动细节造成；本报告不作唯一原因归因。

## 5. 运行时采样与远端验证缺口

对新 Server PID 72316 的 **2 秒 sample** 返回 0。原始记录为 [`uu-server-sample.txt`](../artifacts/uu-service-witness-20261101T141332Z/uu-server-sample.txt)，结构化解释为 [`runtime-sampling.json`](../artifacts/uu-service-witness-20261101T141332Z/runtime-sampling.json)。

结果是 `matchingStackLines=[]`，即匹配调用栈行数为 0；只有 **Binary Images** 列表中出现 ScreenCaptureKit、IOSurface 和 IOSurfaceAccelerator。它证明这些映像在进程中装载，**不证明此时正在调用这些捕获接口，也不证明该进程不用这些接口**。短时间统计采样可能错过异步、低频或尚未开始的捕获，不能代替完整函数跟踪。

此记录明确 `humanRemoteConnectionConfirmed=false`。截至本报告使用的证据时点，尚未收到用户确认本轮 UU 远端已经连入；没有基于该轮连接的对端截图、连续视频或可读/不可读对照。因此“正在活动取屏的后端”“远端收到的画面”“正常重开后远程是否恢复”均保持未验证。

另一个[CGDisplayStream 独立探针实验](CGDisplayStream补测.md)验证了自有进程中两种旧入口的像素遮蔽，这与 UU 的库加载、活动取屏或实际远端输出是不同证据，不能互相替代。

## 6. 恢复、正常重开与原文件校验

恢复脚本于 UTC **14:20:19** 卸载实验副本 job，再从 `/Library/LaunchAgents/com.netease.uuremote.agent.plist` 注册原定义；两步均返回 0，`instrumentation-state.json` 最终 `status=restored`。该瞬间新 job 状态曾是启动中的 `xpcproxy`，因此另以稍后的最终检查确认已到 `running`，不把中间状态当作完全恢复。

GUI 也进行了正常启动方式恢复：[`gui-normal-relaunch.json`](../artifacts/uu-service-witness-20261101T141332Z/gui-normal-relaunch.json)记载旧 GUI PID 56546 的 AppleScript 正常退出请求返回 1，随后向该精确当前用户 GUI PID 发送 SIGTERM；清除实验启动环境后调用正常打开流程，返回 0，生成 GUI PID **84593**。恢复记录没有声称这一启动返回值证明远端已经连通。

截至 UTC **14:21:26**，[`final-restoration-check.json`](../research/final-restoration-check.json)确认：

- UU 用户 job 的路径已是原 `/Library` 定义，状态 `running`，PID **84016**，`experimentEnvironmentKeysPresent=[]`。
- Server PID **84053** 的父 PID 为 84016，GUI PID **84593** 存在。它们是恢复后的 PID，不能与实验时 72311 / 72316 / 56546 混用。
- UU 与 ToDesk 两个被临时使用的用户 job 均恢复原定义且无实验环境键。
- 本轮已枚举的 **34 个原版 Mach-O 文件**前后 SHA-256 全部一致，其中 UU 12 个、ToDesk 22 个；包括 UU Server、libstreamer、GUI、Service、Daemon 和 Helper。该校验针对枚举出的这些文件，不声称覆盖用户偏好、运行日志、缓存或所有文件。

[`original-file-hashes-before.json`](../artifacts/uu-service-witness-20261101T141332Z/original-file-hashes-before.json)保留本轮初始哈希；[`original-file-preservation.json`](../artifacts/uu-service-witness-20261101T141332Z/original-file-preservation.json)单独核对原 LaunchAgent plist、GUI、Service、Daemon 四项前后不变。完整组件列表与扩展校验见上述最终检查文件。

原 LaunchAgent plist SHA-256：

```text
3d0534d286a10e87da17c04305211dc5a7914df86fafe4ad3876291d2872e21c
```

## 7. 命令与复核入口

以下为代码和历史操作的审阅入口；本报告整理阶段仅读取现有证据，没有再次启动、退出或修改第三方进程。

```sh
# 自有最小见证器的构建入口；不操作 UU。
bash scripts/build-load-witness.sh

# GUI 实验入口：执行会重启当前用户 UU GUI；历史结果已保存。
python3 scripts/test-uu-load-witness.py

# 服务实验参数说明；此 --help 不改变服务状态。
python3 scripts/uu-service-instrument.py start --help

# 本轮恢复使用的入口；恢复已经完成，无需为审阅重复执行。
python3 scripts/uu-service-instrument.py restore \
  --run-dir artifacts/uu-service-witness-20261101T141332Z

# 只读查看当前原版 job；PID 可能随后正常变化。
/bin/launchctl print gui/501/com.netease.uuremote.agent
```

历史 `start` 的关键参数均保存在 `instrumentation-state.json`：`--library build/libLoadWitness.dylib`、`--mode audit`、当前原生目标的 `--config`、新建实验目录 `--run-dir` 与该目录下 `--log witness.jsonl`。脚本要求新目录，不能使用已有证据目录重跑覆盖结果。

评审应依次查看：**自有正对照 → GUI 结果 → Service/Server 加载检查 → 运行时采样限制 → 原定义与原文件恢复**。本轮可交付结论是加载路径的明确部署边界和可追溯负结果，UU 的实际远端遮蔽仍未验证。
