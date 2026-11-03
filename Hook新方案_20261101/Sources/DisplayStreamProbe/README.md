# CGDisplayStream 独立探针

用于本项目自有进程的旧版连续取屏实验，分别经过 `CGDisplayStreamCreateWithDispatchQueue` 和 `CGDisplayStreamCreate`。不启动、不修改、不注入 UU / ToDesk，也不能据此证明它们的实际捕获入口或远端画面。

```sh
bash scripts/build-display-stream-probe.sh
build/DisplayStreamProbe --api queue --output artifacts/your-new-directory --duration 2
python3 scripts/run-display-stream-matrix.py
python3 scripts/analyze-display-stream-matrix.py artifacts/display-stream-matrix-20261101T141122Z
```

当前 macOS 26 SDK 将这些历史公开 API 标记为 unavailable（10.8 引入、14.0 废弃、15.0 不可用）。源码使用 `__asm` 给历史导出符号声明不同的本地函数名，仍经普通 Mach-O 符号绑定；`dlsym` 仅检查导出存在和读取属性键。此为兼容性实验，不是当前受支持的新产品 API。构建只面向 arm64；部署目标 13.0 不是对每一系统版本的运行保证。

探针调用 `CGPreflightScreenCaptureAccess()`，不主动弹出授权；权限不足、符号缺失、create 返回 NULL、start/stop 失败、无完整帧、图像错误均记录为 inconclusive。成功创建、成功启动和黑图本身都不证明防截屏。

以主显示器实际像素尺寸、完整显示范围、BGRA、最短帧间隔 0.1 秒和 `showsCursor=false` 运行；不指定 sourceRect/destinationRect。实际是内容变化驱动的回调，10fps 是上限请求，不保证每秒 10 个完整新帧。runloop 版把源加入主 runloop 并持续驱动，queue 版用专门串行队列。完整帧在回调内锁定 IOSurface、复制像素到独立 NSData 后立即解锁，以免把系统重复使用的表面误当快照。首个完整帧、每第 5 完整帧和最后完整帧各存 PNG，最多 10 张。所有回调（包括 idle/blank/stopped）仍写报告。

`report.json` 包含调用入口、PID、权限、符号检查、主显示器点/像素尺寸、create/start/stop 结果、每回调原始状态/时间/格式/平面数/步长、完整帧数、保存 PNG 数、保存策略、像素颜色/alpha 极值和错误。停止回调未出现时不提前释放 stream，交由进程结束回收，同时把结果标记无法判断。此探针按完整 IOSurface 消费像素，不验证仅消费 dirty region 的远程客户端、窗口移动、多显示器、HDR 或特殊格式。

矩阵脚本让原生合成考试窗口置前，按每 API 的 baseline、audit、block、recovery 启动 8 个独立子进程。仅 audit/block 子进程设置 `DYLD_INSERT_LIBRARIES`，不修改其他进程或系统服务；原生窗口维持普通共享策略。每次新建目录、保留原始 report/PNG/日志以及 hook、探针 SHA256。全显示器原图可能含其他桌面内容，仅应在本地保留；对外报告应只用合成窗口区域的裁剪图。禁止把无帧、失败或缺失日志算作成功。

本机两入口的四组对照已经完成，结果及限制见 [`docs/CGDisplayStream补测.md`](../../docs/CGDisplayStream补测.md)。分析器核对 PID、权限、生命周期、PNG 计数、hook 实际调用、全屏黑/透明统计、题目标记和公共 LIVE-TICK，并要求两入口各有完整四组前后对照。
