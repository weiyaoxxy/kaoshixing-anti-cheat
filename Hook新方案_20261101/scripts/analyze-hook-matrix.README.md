# Hook 矩阵分析脚本

```bash
python3 scripts/analyze-hook-matrix.py artifacts/controlled-matrix-实际时间戳
```

依赖 Python 3.9+、Pillow，以及本项目已编译的 `build/InspectMedia`（Apple Vision OCR）。脚本只读取已有捕获资料，不启动或操作 Demo、远程软件、hook 或系统设置。

默认按照 `manifest.json.cases` 的先后顺序处理 case，读取 `run.json`、`target-before.json`、`capture/report.json` 和 `hook.jsonl`。发现目录中未列入 manifest 的 case 时也会保留。单帧 PNG 和 `sck-stream-*` 目录的每张 PNG 都会完整解码并 OCR，不抽样跳图。

输出：

- `ocr.jsonl`：InspectMedia 原始结果，加输入图片 SHA-256、检查器 SHA-256 和相对路径。重复运行只有在两个哈希一致且上一轮无 OCR 错误时才复用结果。
- `summary.json`：每个 case/捕获路径的文件数量、回调/保存计数、权限和错误状态、秘密/公共标记命中数、透明/全黑/尺寸统计、匹配正对照及结论。
- `summary.md`：可直接审阅的统计表和限制。

秘密匹配接受 InspectMedia 的 `secretDetected` 或文本归一化后的 `NATIVEEXAMSECRET`/`HOOK9`。公共对照必须匹配本轮 `PUBLICCONTROLHOOK`，不接受旧 Demo 的 PUBLIC-CONTROL-4M2P。连续 display/application 流还要求至少两个不同 `LIVE-TICK` 值，避免只凭一张不变的公共画面断言捕获流正常。

`redaction-supported-in-tested-path` 要求：捕获成功、权限和目标/PID核对成功、图像/帧计数完整、相关 hook 加载与 API 调用可证、block 输出没有秘密、display/application 公共对照保留，以及同一路径在同一窗口的前置 baseline/audit 和后置无 hook recovery 均能读出秘密。任一必需条件缺失都会降级为错误、未截断、缺失对照或不确定，不把零帧、进程崩溃、权限错误或透明图自动记作成功。

本分析不能证明所有内容均不泄露，也不能排除采样间隔内的短暂闪帧，更不等于 UU/ToDesk 已经完成进程内 hook 部署。所有原始图像和错误记录保留，便于人工复核。
