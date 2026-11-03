import AppKit
import ApplicationServices
import Foundation

// Test-only: use an explicit PID rather than a process name, which is ambiguous
// when historical and new builds of the Demo coexist.
let args = Array(CommandLine.arguments.dropFirst())
guard args.count == 2, let pid = Int32(args[0]), ["inspect", "end", "close"].contains(args[1]) else { exit(64) }
guard AXIsProcessTrusted() else { fputs("Accessibility unavailable; no UI action performed\n",stderr); exit(77) }
func value(_ item: AXUIElement, _ attribute: CFString) -> CFTypeRef? {
    var result: CFTypeRef?
    return AXUIElementCopyAttributeValue(item, attribute, &result) == .success ? result : nil
}
func children(_ item: AXUIElement) -> [AXUIElement] { value(item,kAXChildrenAttribute as CFString) as? [AXUIElement] ?? [] }
func title(_ item: AXUIElement) -> String { value(item,kAXTitleAttribute as CFString) as? String ?? "" }
func find(_ item: AXUIElement, title expected: String, depth: Int=0) -> AXUIElement? {
    guard depth < 8 else { return nil }
    if title(item) == expected && (value(item,kAXRoleAttribute as CFString) as? String)==kAXButtonRole { return item }
    for child in children(item) { if let found=find(child,title:expected,depth:depth+1) { return found } }
    return nil
}
let app=AXUIElementCreateApplication(pid)
let deadline=Date(timeIntervalSinceNow:6)
var lastWindows:[String]=[]
while Date()<deadline {
    let windows=value(app,kAXWindowsAttribute as CFString) as? [AXUIElement] ?? []
    lastWindows=windows.map(title)
    if let window=windows.first(where:{title($0).contains("考试准备")}) {
        let target:AXUIElement?
        if args[1]=="close", let raw=value(window,kAXCloseButtonAttribute as CFString),CFGetTypeID(raw)==AXUIElementGetTypeID() {
            target=unsafeBitCast(raw,to:AXUIElement.self)
        } else { target=find(window,title:args[1]=="inspect" ? "开始检查 / 重新检查" : "结束并恢复") }
        if let target {
            let result=AXUIElementPerformAction(target,kAXPressAction as CFString)
            print("pid=\(pid) action=\(args[1]) result=\(result.rawValue)")
            exit(result == .success ? 0 : 1)
        }
    }
    Thread.sleep(forTimeInterval:0.1)
}
fputs("No matching own test window/button; windows=\(lastWindows)\n",stderr)
exit(1)
