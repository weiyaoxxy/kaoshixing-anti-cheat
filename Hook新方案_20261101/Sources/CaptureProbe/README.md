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

## 扩展路径与单路径连续测试

```sh
# 新增矩形截图、历史 display screenshot 与仅目标应用的 SCStream。
./build/CaptureProbe --window-id 123 --extended --capture-application --omit-cursor --output artifacts/new-extended-case

# 在一条窗口流中持续观察14秒，供另一个进程驱动最小化/恢复/保护切换。
./build/CaptureProbe --window-id 123 --only stream --scope window --duration 14 --omit-cursor --output artifacts/new-lifecycle-window

# 只捕获目标应用在其所在显示器上的窗口。
./build/CaptureProbe --window-id 123 --only stream --extended --scope application --duration 14 --output artifacts/new-lifecycle-application
```

`--extended` 启用额外历史 `CGDisplayCreateImage`（`--only cg|all`）和 `SCScreenshotManager.captureImage(in:)`（macOS 15.2+，`--only screenshot|all`）。矩形来自目标窗口的 CoreGraphics 坐标，缺失时才使用 SCWindow.frame，并在报告记录来源。历史 display 路径优先选择与目标矩形相交的显示器；选择不到时回退主显示器并记录匹配失败。它不同于既有 `CGWindowListCreateImage` 合成桌面路径，文件为 `cg-direct-display.png`，报告为 `coreGraphics.directDisplay`。

`--capture-application` 配合 `--extended` 和 `--only stream|all`，额外加入应用流。它使用 `SCContentFilter(display:including:exceptingWindows:)`，只包含目标 SCWindow 的 owningApplication，并传空 `exceptingWindows`，不会错误地把目标窗口作为例外排除。报告为 `applicationFilter` 与 `stream_application`，帧目录为 `sck-stream-application/`。

`--scope window|display|application|all` 只选择 ScreenCaptureKit filter 路径，默认 `all` 保持原行为；`application` 自动选择应用流且要求 `--extended`。scope 不限制历史 CG 路径或矩形截图；需要隔离时同时传 `--only stream`。`--extended` 本身不隐式加入应用流，须传 `--capture-application` 或 `--scope application`。

`--omit-cursor` 将 filter 型截图和所有 SCStream 的 `showsCursor` 设为 false。矩形截图 API 与本工具调用的历史 CG API 不提供同样的光标参数，报告明确注明沿用该 API 默认行为，不能假定光标策略相同。

每帧 `attachments` 尽可能记录 `contentRect`、`scaleFactor`、`contentScale`、`displayTime`、`screenRect`、`boundingRect`、`presenterOverlayContentRect`、`dirtyRects`。不同帧状态/系统可能缺少某些键；字段缺失不代表保护成功。phase 仍按回调送达时刻标记。

所有参数经过校验，未知/重复参数、非法 window ID、非有限时长、超出 0.5–30 秒的时长返回退出码 64。输出目录必须不存在或为空；否则在调用任何捕获和权限请求前返回退出码 73。成功预留目录后会留下 `.capture-probe-reservation`；中断的运行也必须换新目录，不能复用旧 PNG。未指定输出路径时自动生成时间戳加 UUID 的新目录。原有矩阵脚本使用每例新的 capture 子目录，无需改变。

## 捕获附件中的非有限数值

部分 SCK 矩形附件可能是 `CGRect.null`，其中坐标为无穷值；直接交给 Foundation JSON 写出会抛出 Objective-C 异常。深度测试的初次运行 `deep-matrix-20261101T090423Z` 因此未产出完整报告，作为失败运行保留，不能计入有效矩阵。

当前版本的 `rectJSON` 将非有限坐标保存为 `NaN`、`+Infinity`、`-Infinity` 字符串并记录 `nonFiniteFields`。最终报告还递归规范所有嵌套数字，记录 `jsonEncodingPolicy`/`jsonSanitizedPaths`，并在写入前检查 `JSONSerialization.isValidJSONObject`。不把未知/无穷几何量改成 0。无法写出有效报告时退出码为 74。

`./build/CaptureProbe --json-self-test` 不访问屏幕或申请权限，可测试 NaN、无穷值、空矩形和正常数字的 JSON 往返。该选项仅用于探针可靠性验证；不是捕获保护测试。
