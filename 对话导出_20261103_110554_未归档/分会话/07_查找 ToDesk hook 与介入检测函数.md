# 查找 ToDesk hook 与介入检测函数

时区：Asia/Kolkata（UTC+05:30）。

## 07 · 查找 ToDesk hook 与介入检测函数

会话 ID：`01a19fca-e669-7f80-8f8b-7de015ed69fc`

创建时间：2026-11-03 10:33:57；消息数：4（含提问卡片）。

### 001 · 用户 · 2026-11-03 10:33:58

todesk是hook了那个函数，是通过那个函数确认了是todesk介入？


---

### 002 · 助手 · 进度 · 2026-11-03 10:34:20

我先检查项目里 ToDesk 检测相关的代码，确认它检查的是哪个函数，以及如何据此识别 ToDesk。


---

### 003 · 助手 · 进度 · 2026-11-03 10:35:57

已定位到 `SCStream` 的启动捕获方法和画面帧回调。确认是 ToDesk 在取屏，还需要把调用日志中的 PID 对应到 `ToDesk_Session` 的程序路径；单看函数名无法识别是哪款软件。


---

### 004 · 助手 · 回复 · 2026-11-03 10:36:26

这次实验是**我们在 `ToDesk_Session` 进程内 Hook 了 ScreenCaptureKit 的取屏接口**。关键位置有三个：

| 方法 | 作用 |
|---|---|
| `-[SCStream addStreamOutput:type:sampleHandlerQueue:error:]` | 接入我们自己的画面接收代理 |
| `-[SCStream startCaptureWithCompletionHandler:]` | 记录开始取屏，以及启动是否成功 |
| `stream:didOutputSampleBuffer:ofType:` | 通过代理收到实际画面帧，在这里执行考试区域遮蔽 |

对应实现见 [CaptureHook.m](/Users/weiyao/Desktop/考试星防作弊/Hook新方案_20261101/Sources/CaptureHook/CaptureHook.m:352)。

**确认是 ToDesk 在取屏，靠的是“进程身份＋捕获调用＋实际帧”这条证据链：**

1. 日志记录 PID `32469` 的程序路径是 ToDesk 应用内的 `ToDesk_Session`。
2. 同一 PID 调用 `SCStream.startCapture`，启动结果 `success=1`。
3. 随后同一 PID 收到 `3024×1964` 的屏幕图像帧。

这些记录都在[当时的原始日志](/Users/weiyao/Desktop/考试星防作弊/Hook新方案_20261101/artifacts/todesk-block-20261101T135207Z/hook.jsonl:17)中，对应 ToDesk 5.2.3.0、Hook v1.2。

所以，**没有一个函数单独表示“ToDesk 介入”**：这些是公共取屏接口，需要结合调用进程确定归属。这条证据能确认 ToDesk 在采集屏幕；是否有人正在远程操作键鼠，还需要另外的证据。

---

