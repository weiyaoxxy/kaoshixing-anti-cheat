import AppKit
import CoreGraphics

struct Options {
    let output: URL
    let duration: TimeInterval

    init() throws {
        let args = Array(CommandLine.arguments.dropFirst())
        guard args.count == 1 || (args.count == 3 && args[1] == "--duration") else {
            throw NSError(domain: "SunloginRemoteProbe", code: 64,
                          userInfo: [NSLocalizedDescriptionKey: "Usage: SunloginRemoteProbe NEW_OUTPUT_DIRECTORY [--duration SECONDS(1...3600)]"])
        }
        output = URL(fileURLWithPath: args[0], isDirectory: true).standardizedFileURL
        duration = args.count == 3 ? (Double(args[2]) ?? 0) : 3600
        guard duration.isFinite, duration >= 1, duration <= 3600,
              !FileManager.default.fileExists(atPath: output.path) else {
            throw NSError(domain: "SunloginRemoteProbe", code: 64,
                          userInfo: [NSLocalizedDescriptionKey: "Output must not exist; duration must be 1...3600 seconds."])
        }
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: false,
                                                attributes: [.posixPermissions: 0o700])
    }
}

final class Probe: NSObject, NSApplicationDelegate, NSWindowDelegate {
    let options: Options
    let marker = String(UUID().uuidString.prefix(8))
    let pid = ProcessInfo.processInfo.processIdentifier
    let startedAtUTC = ISO8601DateFormatter().string(from: Date())
    var testWindow: NSWindow!
    var publicWindow: NSWindow!
    var testCounter: NSTextField!
    var publicCounter: NSTextField!
    var clickCounter: NSTextField!
    var tick = 0
    var clicks = 0
    var active = true
    var timer: Timer?
    var stopTimer: Timer?

    init(options: Options) { self.options = options }

    func text(_ string: String, frame: NSRect, size: CGFloat) -> NSTextField {
        let value = NSTextField(labelWithString: string)
        value.frame = frame
        value.font = .monospacedSystemFont(ofSize: size, weight: .medium)
        value.lineBreakMode = .byWordWrapping
        value.maximumNumberOfLines = 0
        return value
    }

    func window(title: String, width: CGFloat, height: CGFloat) -> NSWindow {
        let value = NSWindow(contentRect: NSRect(x: 0, y: 0, width: width, height: height),
                             styleMask: [.titled, .closable], backing: .buffered, defer: false)
        value.title = title
        value.isReleasedWhenClosed = false
        value.sharingType = .readOnly
        value.level = .floating
        value.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        value.delegate = self
        return value
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        let menu = NSMenu()
        let item = NSMenuItem()
        let submenu = NSMenu()
        submenu.addItem(withTitle: "退出向日葵测试窗口", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = submenu
        menu.addItem(item)
        NSApp.mainMenu = menu

        let visible = (NSScreen.main ?? NSScreen.screens[0]).visibleFrame
        let horizontal = visible.width >= 920
        let testWidth: CGFloat = min(560, max(300, visible.width - 32))
        let publicWidth: CGFloat = min(320, max(280, visible.width - 32))
        testWindow = window(title: "向日葵 Hook 验证 — 测试区域", width: testWidth, height: 270)
        publicWindow = window(title: "向日葵 Hook 验证 — 公共对照", width: publicWidth, height: 150)
        let testContent = testWindow.contentView!
        testContent.addSubview(text("测试编号：\(marker)", frame: NSRect(x: 20, y: 207, width: testWidth - 40, height: 34), size: 25))
        testCounter = text("测试区计数：0", frame: NSRect(x: 20, y: 153, width: testWidth - 40, height: 34), size: 25)
        testContent.addSubview(testCounter)
        clickCounter = text("按钮点击：0", frame: NSRect(x: 20, y: 112, width: testWidth - 40, height: 30), size: 20)
        testContent.addSubview(clickCounter)
        let button = NSButton(title: "从远端点击此测试按钮", target: self, action: #selector(clicked))
        button.bezelStyle = .rounded
        button.frame = NSRect(x: 20, y: 62, width: min(290, testWidth - 40), height: 38)
        testContent.addSubview(button)
        testContent.addSubview(text("仅合成数据；此窗口是遮蔽目标。", frame: NSRect(x: 20, y: 16, width: testWidth - 40, height: 35), size: 16))

        let publicContent = publicWindow.contentView!
        publicContent.addSubview(text("公共对照 · \(marker)", frame: NSRect(x: 18, y: 105, width: publicWidth - 36, height: 28), size: 18))
        publicCounter = text("LIVE-TICK 0", frame: NSRect(x: 18, y: 62, width: publicWidth - 36, height: 34), size: 25)
        publicContent.addSubview(publicCounter)
        publicContent.addSubview(text("遮蔽时此计数应继续变化", frame: NSRect(x: 18, y: 20, width: publicWidth - 36, height: 30), size: 16))

        testWindow.setFrameOrigin(NSPoint(x: visible.minX + 16, y: visible.maxY - testWindow.frame.height - 16))
        if horizontal {
            publicWindow.setFrameOrigin(NSPoint(x: testWindow.frame.maxX + 16,
                                                y: visible.maxY - publicWindow.frame.height - 16))
        } else {
            publicWindow.setFrameOrigin(NSPoint(x: visible.minX + 16,
                                                y: testWindow.frame.minY - publicWindow.frame.height - 16))
        }
        publicWindow.orderFront(nil)
        testWindow.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        persist()
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            guard let self else { return }
            self.tick += 1
            self.testCounter.stringValue = "测试区计数：\(self.tick)"
            self.publicCounter.stringValue = "LIVE-TICK \(self.tick)"
            self.persist()
        }
        stopTimer = Timer.scheduledTimer(withTimeInterval: options.duration, repeats: false) { _ in NSApp.terminate(nil) }
    }

    @objc func clicked() {
        clicks += 1
        clickCounter.stringValue = "按钮点击：\(clicks)"
        persist()
    }

    func windowInfo(_ window: NSWindow?) -> [String: Any] {
        guard let window else { return ["visible": false] }
        let windowID = CGWindowID(window.windowNumber)
        let entries = CGWindowListCopyWindowInfo(.optionIncludingWindow, windowID) as? [[String: Any]] ?? []
        let match = entries.first { row in
            (row[kCGWindowNumber as String] as? NSNumber)?.uint32Value == windowID &&
            (row[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == pid
        }
        let raw = match?[kCGWindowBounds as String] as? [String: Any]
        var result: [String: Any] = ["windowID": window.windowNumber, "ownerPID": pid,
                                    "visible": active && window.isVisible && !window.isMiniaturized,
                                    "floating": true]
        if let raw, let x = raw["X"] as? NSNumber, let y = raw["Y"] as? NSNumber,
           let width = raw["Width"] as? NSNumber, let height = raw["Height"] as? NSNumber,
           [x, y, width, height].allSatisfy({ $0.doubleValue.isFinite }), width.doubleValue > 0, height.doubleValue > 0 {
            result["bounds"] = ["x": x.doubleValue, "y": y.doubleValue,
                                "width": width.doubleValue, "height": height.doubleValue]
        }
        return result
    }

    func write(_ filename: String, _ value: [String: Any]) throws {
        let url = options.output.appendingPathComponent(filename)
        let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .prettyPrinted])
        try data.write(to: url, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }

    func persist() {
        let target = windowInfo(testWindow)
        let control = windowInfo(publicWindow)
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let enabled = active && target["visible"] as? Bool == true && target["bounds"] != nil
        var config: [String: Any] = ["schemaVersion": 1, "enabled": enabled,
                                     "ownerPID": pid, "windowID": testWindow?.windowNumber ?? 0,
                                     "scope": "single_synthetic_test_window", "timestamp": timestamp]
        if let bounds = target["bounds"] { config["bounds"] = bounds }
        let state: [String: Any] = ["schemaVersion": 1, "pid": pid, "marker": marker,
                                    "startedAtUTC": startedAtUTC, "atUTC": timestamp,
                                    "active": active, "tick": tick, "clicks": clicks,
                                    "inputOriginVerified": false, "screenPixelsCollected": false,
                                    "automaticExitAfterSeconds": options.duration,
                                    "testWindow": target, "publicWindow": control]
        do {
            try write("hook-config.json", config)
            try write("state.json", state)
        } catch {
            fputs("Synthetic probe output write failed: \(error.localizedDescription)\n", stderr)
            if active { NSApp.terminate(nil) }
        }
    }

    func windowDidMove(_ notification: Notification) { if testWindow != nil && publicWindow != nil { persist() } }
    func windowDidMiniaturize(_ notification: Notification) { persist() }
    func windowDidDeminiaturize(_ notification: Notification) { persist() }
    func windowWillClose(_ notification: Notification) {
        if let closing = notification.object as? NSWindow, closing === testWindow {
            active = false
            persist()
            NSApp.terminate(nil)
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) {
        active = false
        timer?.invalidate()
        stopTimer?.invalidate()
        persist()
    }
}

do {
    let options = try Options()
    let app = NSApplication.shared
    let delegate = Probe(options: options)
    app.delegate = delegate
    app.run()
} catch {
    fputs("\(error.localizedDescription)\n", stderr)
    exit(64)
}
