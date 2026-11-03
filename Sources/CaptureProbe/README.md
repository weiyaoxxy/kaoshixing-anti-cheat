# 独立捕获探针

此工具是独立的进程，不链接 Demo 的渲染代码或共享帧缓冲区。只有父进程/系统授予屏幕录制权限后，捕获结果才有解释意义。

```sh
./scripts/build-probe.sh
./build/CaptureProbe --permission --output artifacts/permission
./build/CaptureProbe --list --output artifacts/window-list
./build/CaptureProbe --window-id 123 --output artifacts/protected
```

窗口 ID 应从 Demo 日志或 `--list` 读取。也可用 `--target-name ExamCaptureDemo`，但同名多窗口时优先传 ID。`--request-permission --permission` 仅用于明确请求权限；`--permission` 本身只做 preflight，不触发请求。首次使用 ScreenCaptureKit 枚举/捕获时，系统仍可能显示屏幕录制授权提示。若更改权限后失败，退出并重新启动探针及负责启动它的终端/应用。

| 测试路径 | 文件 | 条件 |
|---|---|---|
| CoreGraphics 单窗口 | `cg-window.png` | 目标 ID；API 返回 nil 时只记 JSON |
| CoreGraphics 全屏 | `cg-display.png` | 所有可见窗口合成；排除桌面元素 |
| ScreenCaptureKit 单窗口截图 | `sck-screenshot-window.png` | macOS 14+，目标出现在 SCShareableContent |
| ScreenCaptureKit 显示器截图 | `sck-screenshot-display.png` | macOS 14+；目标所在显示器，否则主显示器 |
| ScreenCaptureKit 单窗口流 | `sck-stream-window/frame-*.png` | 默认 2 秒、请求 10 fps |
| ScreenCaptureKit 显示器流 | `sck-stream-display/frame-*.png` | 默认 2 秒、请求 10 fps |

`--duration` 可设 0.5–30 秒。静态画面下 complete 帧数可少于时长乘帧率，不能用此认定捕获失败。`--only cg|screenshot|stream|all` 可隔离路径；`--only cg` 不调用 ScreenCaptureKit 枚举。

`report.json` 保存时间、系统、PID、权限、窗口清单、捕获尺寸、SCK 帧状态与错误。完整帧保存为 PNG；流测试验证连续输出，不将 PNG 序列冒充系统录屏文件。图像需要与关闭保护的对照组及物理显示观察一起判断；黑屏、空文件、窗口不在清单中、属性设置成功均不能单独证明防截屏。

当前 SDK 对 `CGWindowListCreateImage` 的直接调用标记 unavailable。本工具用 `dlsym` 查找同名历史公开符号，记录是否存在及运行结果；这只用于兼容性研究，不能视为当前系统正式支持的新应用开发路径，也没有使用 SkyLight 私有接口。

构建目标为 arm64 macOS 13.0，Swift 5 语言模式；SCScreenshotManager 有 macOS 14.0 运行时检查。使用 ad-hoc 签名，无额外 entitlement。此最小探针不包含系统快捷键截图、Screenshot.app、第三方会议/远控、外接显示器 HDMI 捕获等测试，必须另行执行。

## 更新过滤器与重建流

```sh
./build/CaptureProbe --window-id 123 --only stream --exercise-filter-update --output artifacts/filter-update
```

每个窗口/显示器路径执行：初始流 2 秒 → `updateContentFilter` 传入同一个 filter → 再收集 2 秒 → 停止 → 新建 SCStream，再收集 2 秒。`--duration` 设置每段时长；默认两条路径合计约 12 秒。默认不传此选项时仍只收集原来的单段。

JSON 的 `phaseEvents` 记录阶段的墙钟时间与 host uptime；每帧记录 sample PTS、回调时间与阶段。阶段标签按回调送达时间划分，不能视为精确的帧产生边界。重建流的结果另存在 `stream_window_recreated` / `stream_display_recreated`，PNG 在相应 `*-recreated` 目录。API 调用失败时仍保留此前收到的帧。
