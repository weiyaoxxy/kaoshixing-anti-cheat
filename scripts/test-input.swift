import AppKit
import ApplicationServices
import CoreGraphics

// No permission requests, process activation, global event posts, or unrelated apps.
// Default is a read-only check. --post is required to inject the planned events.
let args = Array(CommandLine.arguments.dropFirst())
func value(_ name: String) -> String? {
    guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
    return args[i + 1]
}
var report: [String: Any] = [
    "timestamp": ISO8601DateFormatter().string(from: Date()),
    "CGPreflightPostEventAccess": CGPreflightPostEventAccess(),
    "AXIsProcessTrusted": AXIsProcessTrusted(),
    "posted": false,
    "postedEventCount": 0,
    "permissionRequested": false,
    "routing": "CGEvent.postToPid only",
    "note": "Posting is not an acknowledgement of delivery. Verify Demo inputEvents and recorded frames separately."
]
func finish(_ code: Int32 = 0) -> Never {
    let data = (try? JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])) ?? Data("{}".utf8)
    print(String(decoding: data, as: UTF8.self))
    if let path = value("--output") { try? data.write(to: URL(fileURLWithPath: path), options: .atomic) }
    exit(code)
}
if args.contains("--help") {
    print("TestInput --pid PID [--post] [--window-frame x,y,w,h] [--click-x X --click-y Y] [--text 'xyz12'] [--backspaces 1] [--output report.json]")
    print("Default only checks existing permissions and target. --window-frame is AppKit global point coordinates (bottom-left origin); explicit click coordinates use Quartz global points (top-left origin). Without either, derive the Demo window bounds from CoreGraphics. Only --post injects a B-option mouse click, ASCII text, and backspace to the verified Demo PID.")
    exit(0)
}
guard let rawPID = value("--pid"), let pid = Int32(rawPID), pid > 0 else {
    report["status"] = "permission_check_only"
    report["reason"] = "No valid --pid; no events can be posted."
    finish()
}
report["targetPID"] = pid
func targetApp() -> NSRunningApplication? {
    guard let app = NSRunningApplication(processIdentifier: pid), !app.isTerminated,
          app.bundleIdentifier == "local.examcapture.demo",
          app.executableURL?.lastPathComponent == "ExamCaptureDemo" else { return nil }
    return app
}
guard let app = targetApp(), let executable = app.executableURL else {
    report["status"] = "refused"
    report["reason"] = "PID is not a running local.examcapture.demo / ExamCaptureDemo."
    finish(2)
}
report["targetExecutable"] = executable.path
report["targetBundleIdentifier"] = app.bundleIdentifier ?? ""
let windows = (CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []).filter {
    ($0[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == pid &&
    ($0[kCGWindowLayer as String] as? NSNumber)?.intValue == 0 &&
    ($0[kCGWindowName as String] as? String ?? "").hasPrefix("ExamCaptureDemo")
}
guard let window = windows.first,
      let bounds = window[kCGWindowBounds as String] as? [String: Any],
      let rect = CGRect(dictionaryRepresentation: bounds as CFDictionary),
      let windowID = (window[kCGWindowNumber as String] as? NSNumber)?.int64Value else {
    report["status"] = "refused"
    report["reason"] = "No visible titled Demo window for this PID; cannot validate the click target."
    finish(2)
}
report["targetWindowID"] = windowID
report["windowBoundsQuartz"] = ["x": rect.minX, "y": rect.minY, "width": rect.width, "height": rect.height]
// Demo's B option is centered at view-local (100, 500 - 245 - 43 + 14).
// ExamView begins at content y=0, so use the full window bottom edge minus 226.
var point = CGPoint(x: rect.minX + 100, y: rect.maxY - 226)
if let frameArgument = value("--window-frame") {
    let fields = frameArgument.split(separator: ",").compactMap { Double($0) }
    guard fields.count == 4, fields.allSatisfy(\.isFinite), fields[2] > 0, fields[3] > 0 else {
        report["status"] = "refused"; report["reason"] = "Invalid AppKit --window-frame"; finish(2)
    }
    let mainHeight = CGDisplayBounds(CGMainDisplayID()).height
    point = CGPoint(x: fields[0] + 100, y: mainHeight - (fields[1] + 226))
    report["suppliedWindowFrameAppKit"] = fields
}
if let x = value("--click-x"), let y = value("--click-y"), let dx = Double(x), let dy = Double(y), dx.isFinite, dy.isFinite {
    point = CGPoint(x: dx, y: dy)
}
guard rect.contains(point) else {
    report["status"] = "refused"; report["reason"] = "Planned click is outside the verified Demo window."; finish(2)
}
let string = value("--text") ?? "xyz12"
guard !string.isEmpty, string.utf8.count <= 40, string.unicodeScalars.allSatisfy({ (32...126).contains($0.value) }) else {
    report["status"] = "refused"; report["reason"] = "Text must contain 1–40 printable ASCII characters."; finish(2)
}
let backspaces = Int(value("--backspaces") ?? "1") ?? -1
guard (0...40).contains(backspaces) else {
    report["status"] = "refused"; report["reason"] = "Backspaces must be 0–40."; finish(2)
}
report["plannedClickQuartz"] = ["x": point.x, "y": point.y]
report["plannedText"] = string
report["plannedBackspaces"] = backspaces
let authorized = (report["CGPreflightPostEventAccess"] as? Bool == true) && (report["AXIsProcessTrusted"] as? Bool == true)
report["authorizedByExistingPermissions"] = authorized
if !args.contains("--post") {
    report["status"] = authorized ? "ready_not_posted" : "blocked_not_posted"
    report["reason"] = "Read-only preflight; --post was not supplied."
    finish()
}
guard authorized else {
    report["status"] = "refused"; report["reason"] = "Existing event-post and accessibility permissions are required; no permission request was made."; finish(3)
}
let source = CGEventSource(stateID: .privateState)
var posted = 0
func send(_ event: CGEvent) {
    // Recheck identity before every event; never fall back to a global event tap.
    guard let current = targetApp(), current.executableURL == executable,
          CGPreflightPostEventAccess(), AXIsProcessTrusted() else {
        report["status"] = "aborted"; report["reason"] = "Target process identity or existing permission changed."; report["postedEventCount"] = posted; report["posted"] = posted > 0; finish(4)
    }
    event.postToPid(pid)
    posted += 1
    Thread.sleep(forTimeInterval: 0.04)
}
for type in [CGEventType.leftMouseDown, .leftMouseUp] {
    guard let event = CGEvent(mouseEventSource: source, mouseType: type, mouseCursorPosition: point, mouseButton: .left) else {
        report["status"] = "error"; report["reason"] = "Could not create mouse event."; finish(4)
    }
    event.setIntegerValueField(.mouseEventClickState, value: 1)
    event.setIntegerValueField(.mouseEventWindowUnderMousePointer, value: windowID)
    event.setIntegerValueField(.mouseEventWindowUnderMousePointerThatCanHandleThisEvent, value: windowID)
    send(event)
}
for character in string.utf16 {
    var codeUnit = character
    for down in [true, false] {
        guard let event = CGEvent(keyboardEventSource: source, virtualKey: 0, keyDown: down) else {
            report["status"] = "error"; report["reason"] = "Could not create keyboard event."; finish(4)
        }
        event.keyboardSetUnicodeString(stringLength: 1, unicodeString: &codeUnit)
        send(event)
    }
}
for _ in 0..<backspaces {
    for down in [true, false] {
        if let event = CGEvent(keyboardEventSource: source, virtualKey: 51, keyDown: down) { send(event) }
    }
}
report["posted"] = true
report["postedEventCount"] = posted
report["status"] = "posted_delivery_unverified"
finish()
