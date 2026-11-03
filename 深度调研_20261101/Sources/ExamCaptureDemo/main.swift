import AppKit
import AVFoundation
import CoreMedia
import CoreVideo
import QuartzCore
import ScreenCaptureKit

// Demo uses only synthetic exam content. No screen capture permission is required.
let args = CommandLine.arguments
func argument(_ key: String, _ fallback: String) -> String {
    guard let i = args.firstIndex(of: key), i + 1 < args.count else { return fallback }
    return args[i + 1]
}
let outputURL = URL(fileURLWithPath: argument("--output", FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Desktop/考试星防作弊/深度调研_20261101/artifacts/interactive").path), isDirectory: true)
try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
let requestedMode = argument("--mode", "protected")
let duration = Double(argument("--duration", "0")) ?? 0
let fps = Int(argument("--fps", "20")) ?? 20
let automaticRecording = args.contains("--record")
let scenario = argument("--scenario", "none")
let renderScaleOverride = Double(argument("--render-scale", "0")) ?? -1
guard ["baseline", "window-none", "protected", "both", "mixed"].contains(requestedMode),
      (1...60).contains(fps), duration >= 0,
      ["none", "protection-toggle", "sharing-toggle", "window-lifecycle"].contains(scenario),
      renderScaleOverride == 0 || (1...4).contains(renderScaleOverride) else {
    fputs("Invalid arguments: --mode baseline|window-none|protected|both|mixed; --fps 1...60; --duration >= 0\n", stderr)
    exit(2)
}
func saveJSON(_ value: [String: Any], _ name: String) {
    if let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]) {
        try? data.write(to: outputURL.appendingPathComponent(name), options: .atomic)
    }
}

final class Recorder {
    let writer: AVAssetWriter
    let input: AVAssetWriterInput
    let adaptor: AVAssetWriterInputPixelBufferAdaptor
    var accepted = 0
    var dropped = 0
    var firstTime: CFTimeInterval?
    init(url: URL, width: Int, height: Int) throws {
        writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
        input = AVAssetWriterInput(mediaType: .video, outputSettings: [
            AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: width, AVVideoHeightKey: height,
            AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 8_000_000, AVVideoMaxKeyFrameIntervalKey: fps]
        ])
        input.expectsMediaDataInRealTime = true
        adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
            kCVPixelBufferWidthKey as String: width, kCVPixelBufferHeightKey as String: height,
            kCVPixelBufferIOSurfacePropertiesKey as String: [:]
        ])
        guard writer.canAdd(input) else { throw NSError(domain: "Recorder", code: 1) }
        writer.add(input)
        guard writer.startWriting() else { throw writer.error ?? NSError(domain: "Recorder", code: 2) }
        writer.startSession(atSourceTime: .zero)
    }
    func append(_ buffer: CVPixelBuffer, now: CFTimeInterval) {
        if firstTime == nil { firstTime = now }
        guard input.isReadyForMoreMediaData else { dropped += 1; return }
        if adaptor.append(buffer, withPresentationTime: CMTime(seconds: now - firstTime!, preferredTimescale: 60000)) {
            accepted += 1
        } else { dropped += 1 }
    }
    func finish(_ done: @escaping () -> Void) {
        input.markAsFinished()
        writer.finishWriting { DispatchQueue.main.async { done() } }
    }
}

final class ExamView: NSView {
    let video = AVSampleBufferDisplayLayer()
    let overlay = NSTextField(labelWithString: "NATIVE-LEAK-8R3T  普通控件：会单独泄露")
    var mode = "protected"
    var phaseToken = "PHASE-00-INITIAL"
    var answer = ""
    var choice = 0
    var eventCount = 0
    var submitted = 0
    var renderMS: [Double] = []
    var pool: CVPixelBufferPool?
    var format: CMVideoFormatDescription?
    var recorder: Recorder?
    var timer: Timer?
    var lastFrame: CVPixelBuffer?
    var recordingURL: URL?
    var scale: CGFloat = 2
    var canvasSize = CGSize(width: 900, height: 500)
    var onChange: (() -> Void)?
    override var acceptsFirstResponder: Bool { true }
    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor.black.cgColor
        video.videoGravity = .resize
        video.preventsCapture = true
        layer?.addSublayer(video)
        overlay.font = .monospacedSystemFont(ofSize: 15, weight: .bold)
        overlay.textColor = .black
        overlay.backgroundColor = .yellow
        overlay.drawsBackground = true
        overlay.alignment = .center
        overlay.isHidden = true
        addSubview(overlay)
        setAccessibilityElement(true)
        setAccessibilityRole(.group)
        // Expose only a generic label: deliberately no secret exam text in AX metadata.
        setAccessibilityLabel("考试画布，使用 A 到 D 选择答案；此 PoC 尚未实现读屏与中文输入法")
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func layout() {
        super.layout()
        CATransaction.begin(); CATransaction.setDisableActions(true)
        video.frame = bounds
        CATransaction.commit()
        overlay.frame = NSRect(x: 170, y: bounds.height - 155, width: min(560, bounds.width - 180), height: 26)
    }
    func configure() {
        scale = renderScaleOverride > 0 ? CGFloat(renderScaleOverride) : (window?.backingScaleFactor ?? 2)
        canvasSize = bounds.size
        let w = Int(canvasSize.width * scale), h = Int(canvasSize.height * scale)
        let attributes: [String: Any] = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
            kCVPixelBufferWidthKey as String: w, kCVPixelBufferHeightKey as String: h,
            kCVPixelBufferIOSurfacePropertiesKey as String: [:], kCVPixelBufferCGImageCompatibilityKey as String: true,
            kCVPixelBufferCGBitmapContextCompatibilityKey as String: true]
        CVPixelBufferPoolCreate(kCFAllocatorDefault, [kCVPixelBufferPoolMinimumBufferCountKey as String: 4] as CFDictionary, attributes as CFDictionary, &pool)
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / Double(max(1, fps)), repeats: true) { [weak self] _ in self?.renderFrame() }
        renderFrame()
    }
    func setMode(_ value: String) {
        mode = value
        // This mode change is for interactive diagnostics. Automated tests use a fresh process per mode.
        video.preventsCapture = ["protected", "both", "mixed"].contains(value)
        window?.sharingType = ["window-none", "both"].contains(value) ? .none : .readOnly
        overlay.isHidden = value != "mixed"
        renderFrame()
        onChange?()
    }
    func text(_ s: String, _ x: CGFloat, _ y: CGFloat, _ size: CGFloat, _ color: NSColor = .white, bold: Bool = false) {
        (s as NSString).draw(at: CGPoint(x: x, y: y), withAttributes: [.font: NSFont.systemFont(ofSize: size, weight: bold ? .semibold : .regular), .foregroundColor: color])
    }
    func renderFrame() {
        let start = CACurrentMediaTime()
        guard let pool else { return }
        var optional: CVPixelBuffer?
        guard CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, pool, &optional) == kCVReturnSuccess, let buffer = optional else { return }
        CVPixelBufferLockBaseAddress(buffer, [])
        let w = CVPixelBufferGetWidth(buffer), h = CVPixelBufferGetHeight(buffer)
        guard let context = CGContext(data: CVPixelBufferGetBaseAddress(buffer), width: w, height: h, bitsPerComponent: 8,
            bytesPerRow: CVPixelBufferGetBytesPerRow(buffer), space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGBitmapInfo.byteOrder32Little.rawValue | CGImageAlphaInfo.premultipliedFirst.rawValue) else {
            CVPixelBufferUnlockBaseAddress(buffer, []); return
        }
        context.scaleBy(x: scale, y: scale)
        let ns = NSGraphicsContext(cgContext: context, flipped: false)
        NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = ns
        NSColor(calibratedRed: 0.04, green: 0.10, blue: 0.18, alpha: 1).setFill()
        NSBezierPath(rect: CGRect(origin: .zero, size: canvasSize)).fill()
        let top = canvasSize.height
        text("考试星 · 受保护考试画布", 32, top - 54, 26, bold: true)
        text("EXAM-SECRET-7K9Q", 32, top - 101, 30, .cyan, bold: true)
        text(phaseToken, 32, top - 133, 16, .yellow, bold: true)
        NSColor.magenta.setFill(); NSBezierPath(rect: CGRect(x: canvasSize.width - 126, y: top - 106, width: 88, height: 64)).fill()
        text("第 1 题：以下哪种方式允许客户端保存自身考试画面？", 32, top - 195, 23, bold: true)
        let choices = ["A  将原始渲染帧送入本地编码器", "B  让外部进程读取考试窗口", "C  只设置窗口标题", "D  只检测截图快捷键"]
        for (i, item) in choices.enumerated() {
            let y = top - 245 - CGFloat(i) * 43
            (i == choice ? NSColor(calibratedRed: 0.05, green: 0.35, blue: 0.40, alpha: 1) : NSColor(calibratedWhite: 0.15, alpha: 1)).setFill()
            NSBezierPath(roundedRect: CGRect(x: 28, y: y - 4, width: canvasSize.width - 56, height: 36), xRadius: 8, yRadius: 8).fill()
            text((i == choice ? "●  " : "○  ") + item, 42, y, 19)
        }
        text("输入演示（ASCII）：\(answer.isEmpty ? "点击画布后输入；A–D 选择，⌫ 删除" : answer)", 32, 52, 17)
        text("事件 \(eventCount)   帧 \(submitted)   模式 \(mode)   仅合成试题", 32, 22, 13, .lightGray)
        NSGraphicsContext.restoreGraphicsState()
        if lastFrame == nil, let image = context.makeImage() {
            let rep = NSBitmapImageRep(cgImage: image)
            try? rep.representation(using: .png, properties: [:])?.write(to: outputURL.appendingPathComponent("source-reference.png"))
        }
        CVPixelBufferUnlockBaseAddress(buffer, [])
        lastFrame = buffer
        if format == nil { CMVideoFormatDescriptionCreateForImageBuffer(allocator: kCFAllocatorDefault, imageBuffer: buffer, formatDescriptionOut: &format) }
        if let format {
            var timing = CMSampleTimingInfo(duration: .invalid, presentationTimeStamp: CMTime(seconds: start, preferredTimescale: 60000), decodeTimeStamp: .invalid)
            var sample: CMSampleBuffer?
            CMSampleBufferCreateReadyWithImageBuffer(allocator: kCFAllocatorDefault, imageBuffer: buffer, formatDescription: format, sampleTiming: &timing, sampleBufferOut: &sample)
            if let sample {
                // Host-time PTS, no DisplayImmediately attachment: the renderer uses the default host timebase.
                if #available(macOS 14.0, *) {
                    if video.sampleBufferRenderer.isReadyForMoreMediaData { video.sampleBufferRenderer.enqueue(sample); submitted += 1 }
                } else {
                    if video.isReadyForMoreMediaData { video.enqueue(sample); submitted += 1 }
                }
            }
        }
        recorder?.append(buffer, now: start)
        renderMS.append((CACurrentMediaTime() - start) * 1000)
    }
    func startRecording() {
        guard recorder == nil, let frame = lastFrame else { return }
        let url = outputURL.appendingPathComponent("self-recording-\(UUID().uuidString.prefix(8)).mp4")
        do { recorder = try Recorder(url: url, width: CVPixelBufferGetWidth(frame), height: CVPixelBufferGetHeight(frame)); recordingURL = url }
        catch { saveJSON(["error": error.localizedDescription], "recording-error.json") }
    }
    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        let p = convert(event.locationInWindow, from: nil)
        for i in 0..<4 {
            let y = canvasSize.height - 245 - CGFloat(i) * 43
            if CGRect(x: 28, y: y - 4, width: canvasSize.width - 56, height: 36).contains(p) { choice = i }
        }
        eventCount += 1; renderFrame()
    }
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 51 { if !answer.isEmpty { answer.removeLast() } }
        else if let s = event.characters, !event.modifierFlags.contains(.command) {
            if let c = s.uppercased().first, let i = "ABCD".firstIndex(of: c) { choice = "ABCD".distance(from: "ABCD".startIndex, to: i) }
            if s.unicodeScalars.allSatisfy({ $0.value >= 32 && $0.value < 127 }) { answer = String((answer + s).suffix(45)) }
        }
        eventCount += 1; renderFrame()
    }
    func stats() -> [String: Any] {
        let sorted = renderMS.sorted()
        var result: [String: Any] = ["mode": mode, "pid": ProcessInfo.processInfo.processIdentifier, "windowID": window?.windowNumber ?? -1,
            "phaseToken": phaseToken,
            "preventsCapture": video.preventsCapture, "sharingType": window?.sharingType.rawValue ?? 99,
            "submittedFrames": submitted, "inputEvents": eventCount, "backingScale": scale,
            "pixelWidth": Int(canvasSize.width * scale), "pixelHeight": Int(canvasSize.height * scale), "targetFPS": fps,
            "renderMeanMS": renderMS.reduce(0,+) / Double(max(1, renderMS.count)),
            "renderP95MS": sorted.isEmpty ? 0 : sorted[min(sorted.count-1, Int(Double(sorted.count) * 0.95))],
            "outputObscured": video.isOutputObscuredDueToInsufficientExternalProtection,
            "displayVerifiedByHuman": false, "recordingPath": recordingURL?.path ?? ""]
        if #available(macOS 14.4, *) { result["isReadyForDisplay"] = video.isReadyForDisplay }
        if #available(macOS 14.0, *) { result["rendererStatus"] = video.sampleBufferRenderer.status.rawValue; result["rendererError"] = video.sampleBufferRenderer.error?.localizedDescription ?? "" }
        if let recorder { result["recordedFrames"] = recorder.accepted; result["recordingDroppedFrames"] = recorder.dropped; result["writerStatus"] = recorder.writer.status.rawValue; result["writerError"] = recorder.writer.error?.localizedDescription ?? "" }
        return result
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow!
    var exam: ExamView!
    var status: NSTextField!
    var modePicker: NSPopUpButton!
    var finishing = false
    let launchHostTime = CACurrentMediaTime()
    var events: [[String: Any]] = []
    var phaseIndex = 0
    func logEvent(_ name: String) {
        var event = exam.stats()
        event["event"] = name
        event["hostTimeSeconds"] = CACurrentMediaTime()
        event["secondsSinceLaunch"] = CACurrentMediaTime() - launchHostTime
        event["windowVisible"] = window.isVisible
        event["miniaturized"] = window.isMiniaturized
        events.append(event)
        saveJSON(["scenario": scenario, "events": events], "scenario-events.json")
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        let menu = NSMenu(); let appItem = NSMenuItem(); menu.addItem(appItem)
        let appMenu = NSMenu(); appMenu.addItem(withTitle: "退出 Demo", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"); appItem.submenu = appMenu; NSApp.mainMenu = menu
        let size = CGSize(width: 900, height: 600)
        window = NSWindow(contentRect: CGRect(origin: CGPoint(x: 100, y: 100), size: size), styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "ExamCaptureDemo — \(requestedMode)"; window.delegate = self
        window.isReleasedWhenClosed = false
        let content = NSView(frame: CGRect(origin: .zero, size: size)); content.wantsLayer = true
        content.layer?.backgroundColor = NSColor(calibratedRed: 0.10, green: 0.22, blue: 0.40, alpha: 1).cgColor
        window.contentView = content
        let publicLabel = NSTextField(labelWithString: "PUBLIC-CONTROL-4M2P · 捕获对照区（始终是普通 UI）")
        publicLabel.frame = CGRect(x: 22, y: 562, width: 860, height: 24); publicLabel.textColor = .white; publicLabel.font = .boldSystemFont(ofSize: 18); content.addSubview(publicLabel)
        modePicker = NSPopUpButton(frame: CGRect(x: 20, y: 524, width: 205, height: 28))
        modePicker.addItems(withTitles: ["baseline", "window-none", "protected", "both", "mixed"]); modePicker.selectItem(withTitle: requestedMode)
        modePicker.target = self; modePicker.action = #selector(changeMode); content.addSubview(modePicker)
        let recordButton = NSButton(title: "开始自身录制", target: self, action: #selector(record)); recordButton.frame = CGRect(x: 240, y: 524, width: 145, height: 28); content.addSubview(recordButton)
        status = NSTextField(labelWithString: "原始帧 → 受保护显示 + 本地 MP4"); status.textColor = .white; status.frame = CGRect(x: 400, y: 527, width: 480, height: 22); content.addSubview(status)
        exam = ExamView(frame: CGRect(x: 0, y: 0, width: 900, height: 500)); content.addSubview(exam)
        window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        exam.onChange = { [weak self] in self?.persist() }
        exam.setMode(requestedMode); exam.configure(); window.makeFirstResponder(exam)
        if automaticRecording { exam.startRecording(); status.stringValue = "正在录制自身原始帧 · 不请求屏幕录制权限" }
        persist()
        logEvent("window-ready")
        if args.contains("--self-capture") {
            Timer.scheduledTimer(withTimeInterval: 2, repeats: false) { [weak self] _ in
                guard let self else { return }
                Task { @MainActor in await self.captureSelf() }
            }
        }
        let actions: [(Double, String)]
        switch scenario {
        case "protection-toggle": actions = [(4, "baseline"), (8, "protected"), (12, "mixed"), (16, "protected")]
        case "sharing-toggle": actions = [(4, "window-none"), (8, "baseline"), (12, "window-none"), (16, "baseline")]
        case "window-lifecycle": actions = [(4, "minimize"), (8, "restore"), (12, "hide"), (16, "show")]
        default: actions = []
        }
        for (delay, action) in actions {
            Timer.scheduledTimer(withTimeInterval: delay, repeats: false) { [weak self] _ in
                guard let self else { return }
                self.logEvent("before-\(action)")
                self.phaseIndex += 1
                self.exam.phaseToken = String(format: "PHASE-%02d-", self.phaseIndex) + action.uppercased()
                switch action {
                case "minimize": self.window.miniaturize(nil)
                case "restore": self.window.deminiaturize(nil)
                case "hide": self.window.orderOut(nil)
                case "show": self.window.makeKeyAndOrderFront(nil)
                default: self.exam.setMode(action); self.modePicker.selectItem(withTitle: action); self.window.title = "ExamCaptureDemo — \(action)"
                }
                self.logEvent("after-\(action)")
                self.persist()
            }
        }
        Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.persist() }
        if duration > 0 { Timer.scheduledTimer(withTimeInterval: duration, repeats: false) { [weak self] _ in self?.finish() } }
    }
    @objc func changeMode() { let mode = modePicker.titleOfSelectedItem ?? "protected"; exam.setMode(mode); window.title = "ExamCaptureDemo — \(mode)" }
    @objc func record() { exam.startRecording(); status.stringValue = "正在录制自身原始帧 · 关闭窗口完成 MP4" }
    @MainActor func captureSelf() async {
        let targetID = UInt32(window.windowNumber)
        var result: [String: Any] = ["callerPID": ProcessInfo.processInfo.processIdentifier, "windowID": window.windowNumber,
            "mode": exam.mode, "api": "SCShareableContent.currentProcess + SCScreenshotManager.captureImage", "scope": "same process, no exemption assumed"]
        if #available(macOS 14.4, *) {
            guard exam.video.isReadyForDisplay, exam.submitted > 10 else {
                result["status"] = "inconclusive-not-ready"
                saveJSON(result, "self-capture.json")
                return
            }
            do {
                let content = try await SCShareableContent.currentProcess
                guard let target = content.windows.first(where: { $0.windowID == targetID }) else {
                    result["status"] = "target-missing"; saveJSON(result, "self-capture.json"); return
                }
                let filter = SCContentFilter(desktopIndependentWindow: target)
                let config = SCStreamConfiguration()
                config.width = Int(filter.contentRect.width * CGFloat(filter.pointPixelScale))
                config.height = Int(filter.contentRect.height * CGFloat(filter.pointPixelScale))
                config.showsCursor = false
                let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
                guard let png = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]) else { throw NSError(domain: "SelfCapture", code: 1) }
                try png.write(to: outputURL.appendingPathComponent("self-sck-window.png"))
                result["status"] = "saved"; result["width"] = image.width; result["height"] = image.height
            } catch { result["status"] = "error"; result["error"] = error.localizedDescription }
        } else { result["status"] = "unavailable" }
        saveJSON(result, "self-capture.json")
    }
    func persist() {
        guard exam != nil else { return }
        var data = exam.stats(); data["os"] = ProcessInfo.processInfo.operatingSystemVersionString
        data["timestamp"] = ISO8601DateFormatter().string(from: Date())
        if let screen = window.screen { data["screenFrame"] = NSStringFromRect(screen.frame) }
        data["windowFrameAppKit"] = NSStringFromRect(window.frame)
        saveJSON(data, "demo-state.json")
    }
    func finish() {
        guard !finishing else { return }; finishing = true; exam.timer?.invalidate()
        if let recorder = exam.recorder { recorder.finish { self.persist(); NSApp.terminate(nil) } }
        else { persist(); NSApp.terminate(nil) }
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool { finish(); return false }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if !finishing { finish(); return .terminateCancel }; return .terminateNow
    }
}
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
