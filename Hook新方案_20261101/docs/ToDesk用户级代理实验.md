# ToDesk 用户级 Session Proxy instrumentation

脚本：`scripts/todesk-proxy-instrument.py`。这是 Hook 新方案的部署实验工具，不使用上一版受保护视频层或窗口共享限制。

**当前验证状态（2026-11-01）：已完成本机 ToDesk 5.2.3.0 的 audit、block 与原任务恢复实测，并取得三阶段远端人工确认。** 详见 [ToDesk 实机验证](ToDesk实机验证.md)。最初只做语法和帮助检查的阶段现已结束；这不扩大为其他版本、其他取屏路径或全部窗口状态的保证。第一次 block 启动曾遇到 `bootstrap` 返回 5，自动恢复记录保留在 [失败实验目录](../artifacts/todesk-block-20261101T135028Z/instrumentation-state.json)。

只读核对过的任务为 `gui/501/com.youqu.todesk.desktop`，原来源为 `/Library/LaunchAgents/com.youqu.todesk.session.plist`、程序为 `/Applications/ToDesk.app/Contents/MacOS/ToDesk_Session_Proxy`；不存在的测试服务返回码为 113。部署边界见 [部署与边界](部署与边界.md)。

## 操作范围

只替换当前用户 GUI 域里标签为 `com.youqu.todesk.desktop` 的已加载任务定义。将原 plist 复制到新实验目录后，在副本的 `EnvironmentVariables` 增加：

- `DYLD_INSERT_LIBRARIES`：指定已验证的项目内 hook dylib。
- `HOOK_DEMO_LOG`：实验目录中的新日志文件。
- `HOOK_DEMO_MODE`：`audit` 或 `block`。
- `HOOK_DEMO_CONFIG`：项目内配置 JSON 路径。

不修改 `/Library` 原 plist、不改签 ToDesk、不执行 sudo、不改 SIP、不更改系统级 ToDesk_Service；原有 `ToDesk_Session` 子进程可能继续运行，脚本只记录其 PID/PPID/UID/程序路径，不强制结束。

## 启动示例

先在项目根目录确认 hook dylib 和配置文件实际路径。下面的配置路径是示例，需要替换为本轮真实配置；run-dir 必须不存在，日志必须位于该新目录内。应选择已验证且实验期间不再改写的 dylib 版本。

```bash
python3 scripts/todesk-proxy-instrument.py start \
  --run-dir "$PWD/artifacts/todesk-proxy-001" \
  --library "$PWD/build/libCaptureHook-v1.2.dylib" \
  --config "$PWD/artifacts/本轮配置目录/hook-config.json" \
  --log "$PWD/artifacts/todesk-proxy-001/hook.jsonl" \
  --mode audit
```

start 要求原任务已从精确原 plist 路径加载，并在操作前保存：

- 原 plist 原始副本与 SHA-256。
- 修改后 plist 及 SHA-256。
- 配置和 dylib 的路径、SHA-256。
- 当前用户域、精确标签、程序路径。
- 操作前后 ToDesk 相关 PID、PPID、UID、可执行文件路径。
- 每次 bootout/bootstrap 的返回码与时间。

然后依次卸载该精确用户任务、bootstrap 实验副本并检查实际任务来源；还会等待最多 8 秒确认 Proxy 为 running 且有 PID。替换过程中发生错误会尝试自动恢复原任务，结果写入 `instrumentation-state.json`。原 plist 哈希变化或任务来源突然变成其他路径时，脚本会拒绝继续删除/替换，避免覆盖来源不明的任务。

## 状态与恢复

```bash
python3 scripts/todesk-proxy-instrument.py status \
  --run-dir "$PWD/artifacts/todesk-proxy-001"

python3 scripts/todesk-proxy-instrument.py restore \
  --run-dir "$PWD/artifacts/todesk-proxy-001"
```

status 仅读取精确标签的 job 和有限进程元数据，并在实验目录写 `last-status.json`。不会保存 launchctl 的原始完整输出，避免记录不相关环境变量。

restore 只处理该次实验的副本任务，核验原 plist 哈希，然后从原路径恢复 bootstrap。它不会终止旧 Session 进程，也不会保证新的远程连接已经恢复。若启动时自动回滚失败，`instrumentation-state.json` 会保留失败原因，可在核对现场后执行 restore。

## 结果解释

`instrumented-job-registered` 只说明 launchd 接受了来自预期副本的任务。以下四个结论必须分开：

1. 任务已注册、Proxy 已运行。
2. hook dylib 实际加载进目标进程。
3. 目标进程实际调用的取屏 API 命中了 hook。
4. 真实远端接收的考试区域被遮蔽，普通桌面仍正常。

仅有新 PID 或 launchctl 成功不能证明第 2–4 项。旧 Session 存活时，还需要辨别实际取屏进程是否仍是旧 PID；否则可能测试到未安装 hook 的旧捕获链路。该脚本不替代原生题目显示对照、帧级检查与远端观察。
