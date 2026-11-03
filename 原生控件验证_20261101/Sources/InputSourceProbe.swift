import Foundation
import Carbon

// Default is read-only. A requested selection can use only an already enabled,
// selectable source returned by TISCreateInputSourceList(includeAllInstalled:false).
// Never enables, disables, installs, registers or sets a default input source.
// The caller must restore the original ID in a finally/defer block after testing.
let args = Array(CommandLine.arguments.dropFirst())
func argument(_ name: String) -> String? {
    guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
    return args[i + 1]
}
if args.contains("--help") {
    print("""
    InputSourceProbe [--select ENABLED_ID | --restore ORIGINAL_ENABLED_ID] [--output result.json]
    Default: read-only list of currently enabled, selectable sources and current
    keyboard input source. --select/--restore call TISSelectInputSource only after
    validating the requested ID against that list. No source is enabled or installed.
    Save beforeID, and restore it in the caller's finally/defer block. This tool does
    not post keyboard events and does not change keyboard-layout defaults directly.
    """)
    exit(0)
}
var output: [String: Any] = [
    "timestamp": ISO8601DateFormatter().string(from: Date()),
    "selectionRequested": false,
    "enabledOrInstalledAnySource": false,
    "wrotePreferencesDirectly": false,
    "postedInputEvents": false,
    "enumeration": "TISCreateInputSourceList(nil, false), filtered enabled && selectCapable",
    "restorationRequirement": "Caller must preserve beforeID and restore it in finally/defer. Selecting a source changes the current user-session input state; it is not scoped to this process."
]
func finish(_ code: Int32) -> Never {
    do {
        let data = try JSONSerialization.data(withJSONObject: output, options: [.prettyPrinted,.sortedKeys])
        print(String(decoding: data, as: UTF8.self))
        if let path = argument("--output") { try data.write(to: URL(fileURLWithPath: path), options: .atomic) }
    } catch {
        fputs("InputSourceProbe output error: \(error)\n",stderr)
        exit(74)
    }
    exit(code)
}
func stringProperty(_ source: TISInputSource, _ property: CFString) -> String? {
    guard let pointer = TISGetInputSourceProperty(source,property) else { return nil }
    return Unmanaged<CFString>.fromOpaque(pointer).takeUnretainedValue() as String
}
func boolProperty(_ source: TISInputSource, _ property: CFString) -> Bool {
    guard let pointer = TISGetInputSourceProperty(source,property) else { return false }
    return CFBooleanGetValue(Unmanaged<CFBoolean>.fromOpaque(pointer).takeUnretainedValue())
}
func describe(_ source: TISInputSource) -> [String: Any] {
    return [
        "id":stringProperty(source,kTISPropertyInputSourceID) ?? "",
        "name":stringProperty(source,kTISPropertyLocalizedName) ?? "",
        "type":stringProperty(source,kTISPropertyInputSourceType) ?? "",
        "category":stringProperty(source,kTISPropertyInputSourceCategory) ?? "",
        "enabled":boolProperty(source,kTISPropertyInputSourceIsEnabled),
        "selectCapable":boolProperty(source,kTISPropertyInputSourceIsSelectCapable),
        "selected":boolProperty(source,kTISPropertyInputSourceIsSelected)
    ]
}
func current() -> [String: Any]? {
    guard let owned = TISCopyCurrentKeyboardInputSource() else { return nil }
    return describe(owned.takeRetainedValue())
}
var i = 0
while i < args.count {
    guard ["--select","--restore","--output"].contains(args[i]), i + 1 < args.count else {
        output["status"] = "refused_invalid_arguments"; output["reason"] = "Unknown argument or missing value: \(args[i])"; finish(64)
    }
    i += 2
}
guard !(args.contains("--select") && args.contains("--restore")) else {
    output["status"] = "refused_invalid_arguments"; output["reason"] = "Use only one of --select and --restore."; finish(64)
}
guard let before = current() else {
    output["status"] = "error"; output["reason"] = "TISCopyCurrentKeyboardInputSource returned nil."; finish(1)
}
output["before"] = before; output["beforeID"] = before["id"]
if let layout = TISCopyCurrentKeyboardLayoutInputSource() {
    output["keyboardLayoutBefore"] = describe(layout.takeRetainedValue())
}
guard let ownedList = TISCreateInputSourceList(nil,false) else {
    output["status"] = "error"; output["reason"] = "TISCreateInputSourceList returned nil."; finish(1)
}
let list = ownedList.takeRetainedValue()
var eligible: [TISInputSource] = []
for index in 0..<CFArrayGetCount(list) {
    guard let pointer = CFArrayGetValueAtIndex(list,index) else { continue }
    let source = Unmanaged<TISInputSource>.fromOpaque(pointer).takeUnretainedValue()
    if boolProperty(source,kTISPropertyInputSourceIsEnabled) && boolProperty(source,kTISPropertyInputSourceIsSelectCapable) { eligible.append(source) }
}
output["sources"] = eligible.map(describe)
output["eligibleSourceCount"] = eligible.count
let requested = argument("--select") ?? argument("--restore")
guard let requested else {
    output["status"] = "read_only"
    output["after"] = current() ?? [:]; output["afterID"] = current()?["id"] ?? ""
    finish(0)
}
output["selectionRequested"] = true
output["operation"] = args.contains("--restore") ? "restore" : "select"
output["requestedID"] = requested
guard let source = eligible.first(where:{ stringProperty($0,kTISPropertyInputSourceID) == requested }) else {
    output["status"] = "refused_source_not_enabled_or_not_selectable"
    output["reason"] = "Requested ID is not in the current enabled/selectable source list; no enabling/installing fallback is permitted."
    output["after"] = current() ?? [:]; output["afterID"] = current()?["id"] ?? ""
    finish(2)
}
// Recheck eligibility immediately before selection; the source list is a snapshot.
guard boolProperty(source,kTISPropertyInputSourceIsEnabled), boolProperty(source,kTISPropertyInputSourceIsSelectCapable) else {
    output["status"] = "refused_source_changed"; finish(2)
}
let status = TISSelectInputSource(source)
output["OSStatus"] = status
output["selectedSourceAfter"] = describe(source)
let deadline = Date().addingTimeInterval(2)
var after = current() ?? [:]
while status == noErr && (after["id"] as? String) != requested && Date() < deadline {
    RunLoop.current.run(until: Date().addingTimeInterval(0.05))
    after = current() ?? [:]
}
output["after"] = after; output["afterID"] = after["id"] ?? ""
output["currentKeyboardSourceMatchesRequested"] = (after["id"] as? String) == requested
output["status"] = status == noErr ? "selection_returned_noErr_check_current_id" : "selection_failed"
finish(status == noErr && (after["id"] as? String) == requested ? 0 : 1)
