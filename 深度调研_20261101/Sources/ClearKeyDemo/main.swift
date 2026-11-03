import AppKit
import AVFoundation
import CoreImage

// Synthetic local HLS experiment. This application does not set NSWindow
// sharingType or AVSampleBufferDisplayLayer.preventsCapture.
let arguments = CommandLine.arguments
func arg(_ name: String, _ fallback: String) -> String {
    guard let index = arguments.firstIndex(of: name), index + 1 < arguments.count else { return fallback }
    return arguments[index + 1]
}
let output = URL(fileURLWithPath: arg("--output", "artifacts/clearkey-manual"), isDirectory: true)
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let mediaURL = URL(string: arg("--url", "http://127.0.0.1:8766/encrypted/stream.m3u8"))!
let allowCapture = arg("--allow-capture", "false") == "true"
let runDuration = Double(arg("--duration", "30")) ?? 30
let outputOrder = arg("--output-order", "before")
let ciContext = CIContext()

func save(_ value: Any, name: String) {
    if let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]) {
        try? data.write(to: output.appendingPathComponent(name), options: .atomic)
    }
}

final class PlayerView: NSView {
    let videoLayer = AVPlayerLayer()
    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor.black.cgColor
        videoLayer.videoGravity = .resizeAspect
        layer?.addSublayer(videoLayer)
    }
    required init?(coder: NSCoder) { fatalError() }
    override func layout() {
        super.layout()
        CATransaction.begin(); CATransaction.setDisableActions(true)
        videoLayer.frame = bounds
        CATransaction.commit()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow!
    var view: PlayerView!
    var player: AVPlayer!
    var item: AVPlayerItem!
    var pixelOutput: AVPlayerItemVideoOutput!
    var timer: Timer?
    var observations: [[String: Any]] = []
    var pixelSamples: [[String: Any]] = []
    var copiedFrames = 0
    var outputChecks = 0
    var began = Date()
    var lastSavedAt = -1.0
    var endedCount = 0
    var finished = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        let menu = NSMenu()
        let appItem = NSMenuItem(); let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu; menu.addItem(appItem); NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 120, y: 180, width: 900, height: 560),
                          styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "ClearKeyDemo — allowsCapture=\(allowCapture)"
        window.delegate = self
        window.isReleasedWhenClosed = false
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 900, height: 560))
        content.wantsLayer = true; content.layer?.backgroundColor = NSColor.darkGray.cgColor
        let label = NSTextField(labelWithString: "CLEARKEY-PUBLIC · allowsCaptureOfClearKeyVideo = \(allowCapture)")
        label.frame = NSRect(x: 20, y: 517, width: 860, height: 28)
        label.textColor = .white; label.font = .boldSystemFont(ofSize: 19)
        content.addSubview(label)
        view = PlayerView(frame: NSRect(x: 0, y: 0, width: 900, height: 500))
        content.addSubview(view); window.contentView = content
        let asset = AVURLAsset(url: mediaURL)
        item = AVPlayerItem(asset: asset)
        pixelOutput = AVPlayerItemVideoOutput(pixelBufferAttributes: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        if outputOrder == "before" { item.add(pixelOutput) }
        player = AVPlayer(playerItem: item)
        if #available(macOS 26.4, *) { player.allowsCaptureOfClearKeyVideo = allowCapture }
        else { save(["error": "requires macOS 26.4 to exercise capture flag"], name: "error.json"); NSApp.terminate(nil); return }
        if outputOrder == "after" { item.add(pixelOutput) }
        view.videoLayer.player = player
        NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main) { [weak self] _ in
            self?.endedCount += 1
            self?.player.seek(to: .zero) { _ in self?.player.play() }
        }
        window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        began = Date(); player.play()
        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in self?.tick() }
        persist()
    }

    func tick() {
        guard !finished else { return }
        outputChecks += 1
        let host = CACurrentMediaTime()
        let itemTime = pixelOutput.itemTime(forHostTime: host)
        if outputOrder != "none", pixelOutput.hasNewPixelBuffer(forItemTime: itemTime),
           let pixel = pixelOutput.copyPixelBuffer(forItemTime: itemTime, itemTimeForDisplay: nil) {
            copiedFrames += 1
            let elapsed = Date().timeIntervalSince(began)
            if lastSavedAt < 0 || elapsed - lastSavedAt >= 3 {
                lastSavedAt = elapsed
                let name = String(format: "video-output-%03d.png", pixelSamples.count + 1)
                let image = CIImage(cvPixelBuffer: pixel)
                if let cg = ciContext.createCGImage(image, from: image.extent),
                   let data = NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:]) {
                    try? data.write(to: output.appendingPathComponent(name), options: .atomic)
                    pixelSamples.append(["file": name, "elapsed": elapsed, "itemTime": CMTimeGetSeconds(itemTime),
                                         "width": cg.width, "height": cg.height])
                }
            }
        }
        if outputChecks % 10 == 0 { observations.append(state()); persist() }
        if runDuration > 0 && Date().timeIntervalSince(began) >= runDuration { finish(); NSApp.terminate(nil) }
    }

    func state() -> [String: Any] {
        var result: [String: Any] = [
            "pid": ProcessInfo.processInfo.processIdentifier, "windowID": window.windowNumber,
            "mediaURL": mediaURL.absoluteString, "videoOutputAttachmentOrder": outputOrder, "requestedAllowsCapture": allowCapture,
            "sharingType": window.sharingType.rawValue, "itemStatus": item.status.rawValue,
            "itemError": item.error?.localizedDescription ?? "", "playerError": player.error?.localizedDescription ?? "",
            "playerRate": player.rate, "timeControlStatus": player.timeControlStatus.rawValue,
            "reasonForWaiting": player.reasonForWaitingToPlay?.rawValue ?? "",
            "isReadyForDisplay": view.videoLayer.isReadyForDisplay,
            "isOutputObscured": player.isOutputObscuredDueToInsufficientExternalProtection,
            "playbackLoops": endedCount, "videoOutputChecks": outputChecks, "videoOutputFramesCopied": copiedFrames,
            "elapsed": Date().timeIntervalSince(began), "os": ProcessInfo.processInfo.operatingSystemVersionString,
            "timestamp": ISO8601DateFormatter().string(from: Date()), "displayVerifiedByHuman": false
        ]
        let seconds = CMTimeGetSeconds(player.currentTime())
        if seconds.isFinite { result["currentTimeSeconds"] = seconds }
        if #available(macOS 26.4, *) { result["actualAllowsCapture"] = player.allowsCaptureOfClearKeyVideo }
        if let events = item.errorLog()?.events { result["errorLog"] = events.map { ["status": $0.errorStatusCode, "domain": $0.errorDomain, "comment": $0.errorComment ?? ""] } }
        return result
    }

    func persist() {
        save(state(), name: "player-state.json")
        save(observations, name: "playback-observations.json")
        save(pixelSamples, name: "video-output-samples.json")
    }
    func finish() { guard !finished else { return }; finished = true; timer?.invalidate(); persist(); player.pause() }
    func windowWillClose(_ notification: Notification) { finish(); NSApp.terminate(nil) }
    func applicationWillTerminate(_ notification: Notification) { finish() }
}
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
