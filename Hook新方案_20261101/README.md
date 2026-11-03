# 捕获 Hook 新方案：原生考试窗口验证

本方案于 2026-11-01 建立。核心源码和早期证据在本目录；2026-11-02 的三家远控复核、完整性检测和总审计另保存在项目根目录的 `docs/`、`artifacts/`。此前的受保护视频渲染 Demo 保留原位置，属于另一条架构路线。

**实测结论：本机 ToDesk 5.2.3.0 已通过远端“可见 → 遮蔽 → 恢复可见”人工验证；UU 4.40.0 的原版主程序、用户服务及新派生取屏子进程没有加载实验库，本轮未实现 UU 遮蔽。** 该方案只影响实际加载 hook 的捕获进程，未加载库的独立进程仍能截到考试内容，不能承诺系统级防截屏。

**截至 2026-11-02：向日葵 16.5.0 的原版 Desktop 加载尝试也未验证成功，未进入遮蔽测试。ToDesk 的实机正结果绑定 Hook v1.2，不能沿用为当前 v1.4 的验收。** [完整审计与架构决策](../docs/Hook路线完整审计与架构决策_20261102.md)将本方案定位为指定宿主中的输出遮蔽/诊断 PoC，建议不再作为管理员对抗场景的通用主方案，并记录原帧放行、配置/几何、恢复和生命周期等待修问题。

## 阅读入口

- [2026-11-03 远控伪装识别与考试管控详细方案](../docs/远控伪装识别与考试管控详细方案_20261103.md)：首版以管理员服务实现身份检测、考试门禁、发现后终止、复查、上报及恢复；ES 执行前拒绝为可选增强，首版无需等待其授权。当前仍是待实施设计。
- [2026-11-03 远控软件运行检测](../docs/远控软件运行检测测试_20261103.md)：先判断 ToDesk/UU/向日葵是否运行的独立只读工具、三轮本机结果和同名误报验证；[构建与使用](Sources/RemoteProcessInventory/README.md)。
- [2026-11-02 总审计与路线建议](../docs/Hook路线完整审计与架构决策_20261102.md)：三家证据、核心代码、考试闭环及合成故障复现。
- [UU 签名与 Hook 对照](../docs/UU签名与Hook对照实验_20261102.md)：重签副本不加载 Hook 也离线，不能算拦截成功。
- [UU 实际调用测试](../docs/UU_Hook实际调用测试报告_20261102.md)、[UU 路径与 v1.4 诊断复核](../docs/UU采集路径复核与Hook诊断升级验证_20261102.md)：区分库加载、真实调用、外部栈观察和自有宿主验证。
- [向日葵最终测试报告](../docs/向日葵Hook实机测试_20261102.md)：加载负结果、自动恢复、旧会话画面差异及完全重连后的确认。
- [Word 1.1：含 UU 连线运行证据](docs/Hook新方案验证报告_v1.1_UU连线验证.docx)：确认此次 UU Server 实际使用 SCK；未实现 UU 遮蔽。
- [Word 审阅报告](docs/Hook新方案验证报告.docx)：带截图的独立交付文档。
- [UU 连线运行验证](docs/UU连线运行验证.md)：用户正常画面反馈、实际取屏调用栈及证据边界。
- [新方案验证报告](docs/新方案验证报告.md)：结论、机制、实验矩阵、截图、部署边界和复现方式。
- [ToDesk 实机验证](docs/ToDesk实机验证.md)：真实 Session 进程日志及用户远端三阶段反馈。
- [独立探针 9 路捕获验证](docs/受控实验结果.md)：281 张实际输出图的解码/OCR 对照。
- [CGDisplayStream 两入口验证](docs/CGDisplayStream补测.md)：161 次完整帧回调，采样保存并检查 41 张 PNG。
- [UU 加载验证](docs/UU加载验证.md)：主程序和用户服务链的负结果及恢复证据。
- [部署与边界](docs/部署与边界.md)：签名、权限、覆盖范围及产品化限制。

## 在这台 Mac 上演示

以下是保留的 **v1.2 历史演示入口**，依赖本机已有 `build/libCaptureHook.dylib`。它不是完整考试保护开关；旧 ToDesk/UU 控制器的恢复缺陷见总审计 F08。仅代码和文档的 ZIP 不含这些历史二进制，不能直接沿用本节认定已复现。

1. 双击 **启动原生考试Demo.command**，出现真正的原生输入框、按钮、文本区和独立计数对照窗。
2. 双击 **ToDesk仅记录模式.command**，从另一台设备重新连接 ToDesk，检查两个窗口和动态计数均可见。
3. 双击 **ToDesk开启遮蔽.command**，重新连接，检查考试窗范围隐藏、公共计数继续变化。
4. 双击 **恢复ToDesk正常状态.command**，重新连接，确认考试内容恢复可见。

切换模式会重启当前用户的 ToDesk 代理，可能中断连接；旧 Session 可能继续存活，需重新连接并核对实际会话进程。这些脚本只支持本次确认过的用户级任务标签和程序路径，不修改原始 plist、第三方应用文件或系统安全设置。任务注册成功不等于画面遮蔽成功，仍须按上述步骤观察。实验结束已恢复原启动定义，具体时点见报告及保存的状态文件。

**验证UU加载限制.command** 仅复现最小见证库的 GUI 启动加载测试，会重启 UU 界面；它不是“UU 遮蔽开关”。服务链验证工具为 `scripts/uu-service-instrument.py`，操作及结果见 UU 文档。

也可以在本目录运行：

```bash
python3 scripts/democtl.py start-native
python3 scripts/democtl.py todesk-audit
python3 scripts/democtl.py todesk-block
python3 scripts/democtl.py restore
python3 scripts/democtl.py status
```

## 构建与受控复测

本轮构建为 Apple Silicon arm64；原生目标和主探针部署目标 macOS 13，hook 部署目标 macOS 14。完整矩阵仅在 macOS 26.6.2 / SDK 26.5 实测，编译部署目标不等于已验证兼容范围。需要 Xcode Command Line Tools 和捕获进程的屏幕录制授权。

```bash
bash scripts/build-native-demo.sh
zsh scripts/build-probe.sh
HOOK_BUILD_DIR="$(mktemp -d /tmp/exam-hook-build.XXXXXX)"
bash scripts/build-hook.sh "$HOOK_BUILD_DIR/libCaptureHook-v1.4.dylib"
bash scripts/build-load-witness.sh
bash scripts/build-display-stream-probe.sh
python3 scripts/democtl.py start-native
python3 scripts/run-controlled-matrix.py --only all --library "$HOOK_BUILD_DIR/libCaptureHook-v1.4.dylib"
```

这里显式构建并选择当前 v1.4 源码的新产物，不覆盖历史库。构建脚本拒绝覆盖已有输出；`democtl.py` 的 ToDesk 快捷入口仍固定使用历史 `build/libCaptureHook.dylib`，没有自动切换到这份 v1.4。新运行得到的是新的自有探针实验，不能直接继承历史矩阵或 ToDesk 实机结果。

`run-controlled-matrix.py` 在新目录保存实验；使用 `scripts/analyze-hook-matrix.py <该目录>` 对输出作完整检查。现有审计证据无需重跑：

```bash
python3 scripts/analyze-hook-matrix.py artifacts/controlled-matrix-20261101T134227Z
```

## 目录与已知限制

| 位置 | 内容 |
|---|---|
| `Sources/NativeExamDemo` | 普通原生考试窗，无 preventsCapture、DRM 或 sharingType.none |
| `Sources/CaptureHook` | CG interpose / SCK Objective-C 方法挂接、帧复制及矩形遮蔽 |
| `Sources/CaptureProbe`、`Sources/DisplayStreamProbe` | 独立进程捕获验证器 |
| `Sources/LoadWitness` | 只写加载日志的最小 C 动态库，排除捕获框架自身造成的混淆 |
| `build` | 本机历史二进制；libCaptureHook.dylib 对应已测 v1.2，当前构建脚本默认输出另名 v1.4，二者不自动同步 |
| `scripts`、根目录 `.command` | 构建、复测、分析、可恢复的实验启动工具 |
| `docs`、`report-assets` | 报告及带来源记录的对照截图 |
| `research`、`artifacts` | 静态审计、状态、实际日志、原始输出图和历史失败轮次 |

当前 hook 是 **fail-open**：配置无效、格式或范围不支持、分配失败等情况下原样放行。没有覆盖所有捕获 API、所有软件、移动窗口、弹窗、中文输入法候选、多屏/HDR、旧帧缓存或辅助功能读取。新原生 Demo 尚未集成自身录像编码。真实 ToDesk 接收端没有保存截图，远端证据是用户反馈；报告内截图均明确标注为本地独立探针结果。

完整工作目录的 `UU深入验证_20261101/sandbox-apps/` 保留了 UU 原厂签名/重签实验副本；它们不是本项目代码，也没有包含在“仅代码与文档”的 ZIP 中。历史失败证据保留以便审阅，不能计作通过。
