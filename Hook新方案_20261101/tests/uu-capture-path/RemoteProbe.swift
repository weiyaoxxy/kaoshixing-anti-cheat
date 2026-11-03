import AppKit

final class Probe: NSObject, NSApplicationDelegate {
    let output: URL
    let marker = String(UUID().uuidString.prefix(8))
    var window: NSWindow!
    var counterLabel: NSTextField!
    var clicksLabel: NSTextField!
    var tick = 0
    var clicks = 0
    var timer: Timer?

    init(output: URL) { self.output = output }
    func label(_ text: String, _ y: CGFloat, _ size: CGFloat) -> NSTextField {
        let label = NSTextField(labelWithString: text)
        label.frame = NSRect(x: 24, y: y, width: 660, height: 40)
        label.font = .monospacedSystemFont(ofSize: size, weight: .medium)
        return label
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 710, height: 320),
                          styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "UU 采集路径验证 — 合成测试窗口"
        window.isReleasedWhenClosed = false
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        let content = window.contentView!
        content.addSubview(label("测试编号：\(marker)", 245, 26))
        counterLabel = label("动态计数：0", 185, 28)
        content.addSubview(counterLabel)
        clicksLabel = label("按钮点击：0", 125, 24)
        content.addSubview(clicksLabel)
        let button = NSButton(title: "远端点击此按钮验证操作", target: self, action: #selector(clicked))
        button.bezelStyle = .rounded
        button.frame = NSRect(x: 24, y: 65, width: 330, height: 40)
        content.addSubview(button)
        content.addSubview(label("只显示合成数据，不采集屏幕画面。", 15, 17))
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            guard let self else { return }
            self.tick += 1
            self.counterLabel.stringValue = "动态计数：\(self.tick)"
            self.persist()
            if self.tick >= 3600 { NSApp.terminate(nil) }
        }
        persist()
    }
    @objc func clicked() {
        clicks += 1
        clicksLabel.stringValue = "按钮点击：\(clicks)"
        persist()
    }
    func persist() {
        let value: [String: Any] = ["schemaVersion": 1, "marker": marker,
            "pid": ProcessInfo.processInfo.processIdentifier, "tick": tick, "clicks": clicks,
            "atUTC": ISO8601DateFormatter().string(from: Date()),
            "inputOriginVerified": false, "windowNumber": window.windowNumber,
            "automaticExitAfterTicks": 3600, "floatingTestWindow": true]
        if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) {
            try? data.write(to: output, options: .atomic)
            try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: output.path)
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { timer?.invalidate(); persist() }
}

guard CommandLine.arguments.count == 2 else {
    fputs("RemoteProbe NEW_STATE_JSON\n", stderr)
    exit(64)
}
let output = URL(fileURLWithPath: CommandLine.arguments[1])
guard !FileManager.default.fileExists(atPath: output.path),
      FileManager.default.fileExists(atPath: output.deletingLastPathComponent().path) else {
    fputs("Output must be a new file in an existing directory\n", stderr)
    exit(64)
}
let application = NSApplication.shared
let delegate = Probe(output: output)
application.delegate = delegate
application.run()
