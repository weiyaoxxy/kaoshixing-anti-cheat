import AppKit
import ApplicationServices
import CoreGraphics

// Default: read-only preflight. This tool never requests TCC permissions or reads
// clipboard contents. --post is required for events; --global additionally requires
// the verified Demo to be the frontmost application before every posted event.
let args = Array(CommandLine.arguments.dropFirst())
func value(_ key: String) -> String? {
    guard let i = args.firstIndex(of: key), i + 1 < args.count else { return nil }
    return args[i + 1]
}
let expectedBundle = "local.examcapture.nativecontrols"
let expectedExecutableName = "NativeControlDemo"
var report: [String: Any] = [
    "timestamp": ISO8601DateFormatter().string(from: Date()),
    "CGPreflightPostEventAccess": CGPreflightPostEventAccess(),
    "AXIsProcessTrusted": AXIsProcessTrusted(),
    "permissionRequested": false, "clipboardRead": false,
    "postedEventCount": 0, "posted": false,
    "routing": args.contains("--global") ? "CGEvent.post(cghidEventTap); foreground and window guarded" : "CGEvent.postToPid",
    "verificationBoundary": "A successful post is not evidence the app handled the event. Compare Demo state, editing selection, native events, and rendered pixels. Unicode injection does not test an IME composition session."
]
func finish(_ code: Int32 = 0) -> Never {
    let data = (try? JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])) ?? Data("{}".utf8)
    print(String(decoding: data, as: UTF8.self))
    if let output = value("--output") { try? data.write(to: URL(fileURLWithPath: output), options: .atomic) }
    exit(code)
}
func reject(_ message: String, _ code: Int32 = 2) -> Never {
    report["status"] = "refused"; report["reason"] = message; finish(code)
}
if args.contains("--help") {
    print("""
    NativeInputProbe --pid PID [--post] [--global] [--activate] [--window-id ID]
      [--click X,Y | --double-click X,Y | --drag X1,Y1,X2,Y2]
      [--click-offset X,Y] [--scroll DY] [--scroll-at X,Y]
      [--text STRING] [--key a|z|left|right|up|down|tab|return|delete|escape|home|end|pageup|pagedown]
      [--flags command,shift,option,control] [--output result.json]
    Coordinates use Quartz global points (top-left origin); --click-offset is relative
    to the verified visible window's top-left corner. Actions execute in argument order.
    --flags applies to key and mouse actions, never to --text. Text injection allows
    Unicode but does not validate Chinese input-method composition. Clipboard shortcuts
    command+c/v/x require --allow-clipboard-shortcut; the tool never reads or prepares
    the clipboard, so do not enable them without an explicitly isolated synthetic test.
    Without --post, no events and no activation are performed. This accepts only the
    native-controls Demo bundle, not arbitrary application PIDs.
    --ax-inspect --pid PID performs only a bounded, read-only AX tree inspection of
    the verified Demo (depth <= 10, nodes <= 300); no --post is needed or used.
    """)
    exit(0)
}
guard let pidText = value("--pid"), let pid = Int32(pidText), pid > 0 else {
    report["status"] = "permission_check_only"; finish()
}
func targetApp() -> NSRunningApplication? {
    guard let app = NSRunningApplication(processIdentifier: pid), !app.isTerminated,
          app.bundleIdentifier == expectedBundle,
          app.executableURL?.lastPathComponent == expectedExecutableName else { return nil }
    return app
}
guard let app = targetApp(), let executable = app.executableURL else {
    reject("PID is not the running local.examcapture.nativecontrols / NativeControlDemo.")
}
report["targetPID"] = pid; report["targetExecutable"] = executable.path
report["targetBundleIdentifier"] = app.bundleIdentifier ?? ""
if args.contains("--ax-inspect") {
    guard AXIsProcessTrusted() else { reject("AX inspection requires existing accessibility permission; no prompt was requested.", 3) }
    let root = AXUIElementCreateApplication(pid)
    var count = 0
    var truncated = false
    var seen: [AXUIElement] = []
    func read(_ element: AXUIElement, _ name: CFString) -> (CFTypeRef?, AXError) {
        var value: CFTypeRef?
        let error = AXUIElementCopyAttributeValue(element, name, &value)
        return (value,error)
    }
    func inspect(_ element: AXUIElement, depth: Int) -> [String: Any] {
        if depth > 10 || count >= 300 { truncated = true; return ["truncated": true] }
        if seen.contains(where: { CFEqual($0,element) }) { return ["alreadyVisited": true] }
        seen.append(element); count += 1
        var row: [String: Any] = ["index": count, "depth": depth]
        let attributes: [(String,CFString)] = [
            ("role",kAXRoleAttribute as CFString), ("subrole",kAXSubroleAttribute as CFString),
            ("title",kAXTitleAttribute as CFString), ("description",kAXDescriptionAttribute as CFString),
            ("value",kAXValueAttribute as CFString), ("selectedText",kAXSelectedTextAttribute as CFString),
            ("focused",kAXFocusedAttribute as CFString), ("enabled",kAXEnabledAttribute as CFString)
        ]
        for (key,name) in attributes {
            let (value,error) = read(element,name)
            if error == .success, let value {
                if let s = value as? String { row[key] = String(s.prefix(2000)); if s.count > 2000 { row[key+"Truncated"] = true } }
                else if let n = value as? NSNumber { row[key] = n }
                else { row[key+"Type"] = String(describing: CFGetTypeID(value)) }
            } else { row[key+"AXError"] = error.rawValue }
        }
        var children: [AXUIElement] = []
        for attribute in [kAXChildrenAttribute,kAXWindowsAttribute] {
            let (value,error) = read(element,attribute as CFString)
            if error == .success, let list = value as? [AXUIElement] {
                for child in list where !children.contains(where: { CFEqual($0,child) }) { children.append(child) }
            }
        }
        row["reportedChildCount"] = children.count
        row["children"] = children.prefix(max(0,300-count)).map { inspect($0,depth: depth+1) }
        if children.count > max(0,300-count) && count >= 300 { truncated = true }
        return row
    }
    report["axTree"] = inspect(root,depth: 0)
    report["axNodesVisited"] = count; report["axTreeTruncated"] = truncated
    report["axScope"] = "Read-only synthetic Demo AX contents only; authorized AX access is distinct from captured screen pixels. An empty/bounded tree does not prove inaccessible content across every AX path."
    report["status"] = "ax_inspected_no_events_posted"
    finish()
}
let allWindows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
let suppliedWindowID = value("--window-id").flatMap(UInt32.init)
let windows = allWindows.filter { row in
    (row[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == pid &&
    (row[kCGWindowLayer as String] as? NSNumber)?.intValue == 0 &&
    (suppliedWindowID == nil || (row[kCGWindowNumber as String] as? NSNumber)?.uint32Value == suppliedWindowID!)
}
guard let window = windows.first,
      let b = window[kCGWindowBounds as String] as? [String: Any],
      let rect = CGRect(dictionaryRepresentation: b as CFDictionary),
      !rect.isEmpty, !rect.isInfinite, !rect.isNull,
      let windowID = (window[kCGWindowNumber as String] as? NSNumber)?.int64Value else {
    reject("No visible normal-level Demo window; hidden source windows are never input targets.")
}
report["targetWindowID"] = windowID
report["windowBoundsQuartz"] = ["x": rect.minX, "y": rect.minY, "width": rect.width, "height": rect.height]
func numbers(_ text: String, count: Int) -> [Double] {
    let parts = text.split(separator: ",", omittingEmptySubsequences: false).compactMap { Double($0) }
    guard parts.count == count, parts.allSatisfy(\.isFinite) else { reject("Invalid coordinate argument: \(text)") }
    return parts
}
func checkedPoint(_ text: String, offset: Bool = false) -> CGPoint {
    let v = numbers(text, count: 2)
    let p = CGPoint(x: v[0] + (offset ? rect.minX : 0), y: v[1] + (offset ? rect.minY : 0))
    guard rect.contains(p) else { reject("Coordinate is outside the verified Demo window.") }
    return p
}
let keyCodes: [String: CGKeyCode] = [
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23,
    "9": 25, "7": 26, "8": 28, "0": 29,
    "o": 31, "u": 32, "i": 34, "p": 35,
    "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    "return": 36, "tab": 48, "space": 49,
    "delete": 51, "backspace": 51, "escape": 53, "forwarddelete": 117,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121
]
var flags = CGEventFlags()
let flagWords = (value("--flags") ?? "").lowercased().split(separator: ",").map(String.init)
for word in flagWords {
    switch word {
    case "command", "cmd": flags.insert(.maskCommand)
    case "shift": flags.insert(.maskShift)
    case "option", "alt": flags.insert(.maskAlternate)
    case "control", "ctrl": flags.insert(.maskControl)
    case "none", "": break
    default: reject("Unknown modifier: \(word)")
    }
}
report["modifiers"] = flagWords
enum Action { case click(CGPoint, Int), drag(CGPoint, CGPoint), text(String), key(String, CGKeyCode), scroll(Int32, CGPoint) }
var actions: [Action] = []
var plan: [[String: Any]] = []
var i = 0
while i < args.count {
    let key = args[i]
    let takesValue = ["--pid", "--window-id", "--click", "--click-offset", "--double-click", "--drag", "--scroll", "--scroll-at", "--text", "--key", "--flags", "--output"].contains(key)
    if takesValue && i + 1 >= args.count { reject("Missing value after \(key)") }
    let v = takesValue ? args[i+1] : ""
    switch key {
    case "--click", "--click-offset", "--double-click":
        let p = checkedPoint(v, offset: key == "--click-offset")
        let count = key == "--double-click" ? 2 : 1
        actions.append(.click(p, count)); plan.append(["operation": "click", "count": count, "x": p.x, "y": p.y])
    case "--drag":
        let n = numbers(v, count: 4)
        let a = checkedPoint("\(n[0]),\(n[1])"), b = checkedPoint("\(n[2]),\(n[3])")
        actions.append(.drag(a,b)); plan.append(["operation": "drag", "from": [a.x,a.y], "to": [b.x,b.y], "steps": 16])
    case "--text":
        guard !v.isEmpty, v.utf8.count <= 512 else { reject("Text must contain 1–512 UTF-8 bytes.") }
        actions.append(.text(v)); plan.append(["operation": "unicodeText", "text": v, "testsIME": false])
    case "--key":
        let name = v.lowercased()
        guard let code = keyCodes[name] else { reject("Unsupported key: \(v)") }
        if flags.contains(.maskCommand), ["c", "v", "x"].contains(name), !args.contains("--allow-clipboard-shortcut") {
            reject("Clipboard shortcut requires explicit --allow-clipboard-shortcut and a synthetic clipboard test; clipboard is never read by this tool.")
        }
        // Do not close the app or start operating-system UI through a generic test key.
        if flags.contains(.maskCommand), ["q", "w", "space", "tab"].contains(name) { reject("App-closing and system-navigation shortcuts are outside this input probe's scope.") }
        actions.append(.key(name, code)); plan.append(["operation": "key", "name": name, "virtualKey": code])
    case "--scroll":
        guard let delta = Int32(v), (-2000...2000).contains(delta), delta != 0 else { reject("Scroll delta must be between -2000 and 2000, excluding zero.") }
        let p = value("--scroll-at").map { checkedPoint($0) } ?? CGPoint(x: rect.midX, y: rect.midY)
        actions.append(.scroll(delta, p)); plan.append(["operation": "scrollPixels", "delta": delta, "x": p.x, "y": p.y])
    case "--pid", "--window-id", "--scroll-at", "--flags", "--output", "--post", "--global", "--activate", "--allow-clipboard-shortcut": break
    default: reject("Unknown argument: \(key)")
    }
    i += takesValue ? 2 : 1
}
report["plannedActions"] = plan
let allowed = CGPreflightPostEventAccess() && AXIsProcessTrusted()
report["authorizedByExistingPermissions"] = allowed
if !args.contains("--post") { report["status"] = allowed ? "ready_not_posted" : "blocked_not_posted"; finish() }
guard allowed else { reject("Existing event-post and accessibility permissions are required; this tool does not request them.", 3) }
guard !actions.isEmpty else { reject("No input action was requested.") }
if args.contains("--activate") {
    report["activationRequested"] = true
    report["activationAccepted"] = app.activate(options: [.activateIgnoringOtherApps])
    Thread.sleep(forTimeInterval: 0.3)
}
let source = CGEventSource(stateID: .privateState)
var posted = 0
func send(_ event: CGEvent) {
    guard let current = targetApp(), current.executableURL == executable,
          CGPreflightPostEventAccess(), AXIsProcessTrusted() else {
        report["postedEventCount"] = posted; report["posted"] = posted > 0
        reject("Target identity or existing permissions changed while posting.", 4)
    }
    if args.contains("--global") {
        guard NSWorkspace.shared.frontmostApplication?.processIdentifier == pid else {
            report["postedEventCount"] = posted; report["posted"] = posted > 0
            reject("Verified Demo is no longer frontmost; global posting aborted.", 4)
        }
        event.post(tap: .cghidEventTap)
    } else { event.postToPid(pid) }
    posted += 1
    Thread.sleep(forTimeInterval: 0.025)
}
func mouse(_ type: CGEventType, at point: CGPoint, clickCount: Int = 1) {
    guard let e = CGEvent(mouseEventSource: source, mouseType: type, mouseCursorPosition: point, mouseButton: .left) else { reject("Could not create mouse event.", 4) }
    e.flags = flags
    e.setIntegerValueField(.mouseEventClickState, value: Int64(clickCount))
    e.setIntegerValueField(.mouseEventWindowUnderMousePointer, value: windowID)
    e.setIntegerValueField(.mouseEventWindowUnderMousePointerThatCanHandleThisEvent, value: windowID)
    send(e)
}
for action in actions {
    switch action {
    case .click(let p, let count):
        for n in 1...count { mouse(.leftMouseDown, at: p, clickCount: n); mouse(.leftMouseUp, at: p, clickCount: n) }
    case .drag(let a, let b):
        mouse(.leftMouseDown, at: a)
        for n in 1...16 {
            let f = CGFloat(n)/16
            mouse(.leftMouseDragged, at: CGPoint(x: a.x+(b.x-a.x)*f, y: a.y+(b.y-a.y)*f))
        }
        mouse(.leftMouseUp, at: b)
    case .text(let string):
        for character in string {
            let units = Array(String(character).utf16)
            for down in [true,false] {
                guard let e = CGEvent(keyboardEventSource: source, virtualKey: 0, keyDown: down) else { reject("Could not create Unicode key event.", 4) }
                units.withUnsafeBufferPointer { p in e.keyboardSetUnicodeString(stringLength: p.count, unicodeString: p.baseAddress!) }
                e.flags = []
                send(e)
            }
        }
    case .key(_,let code):
        for down in [true,false] {
            guard let e = CGEvent(keyboardEventSource: source, virtualKey: code, keyDown: down) else { reject("Could not create key event.", 4) }
            e.flags = flags; send(e)
        }
    case .scroll(let delta,let p):
        guard let e = CGEvent(scrollWheelEvent2Source: source, units: .pixel, wheelCount: 1, wheel1: delta, wheel2: 0, wheel3: 0) else { reject("Could not create scroll event.", 4) }
        e.location = p; e.flags = flags; send(e)
    }
    Thread.sleep(forTimeInterval: 0.1)
}
report["posted"] = posted > 0
report["postedEventCount"] = posted
report["status"] = "posted_delivery_unverified"
finish()
