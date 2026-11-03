import Foundation
import Darwin
import QuartzCore

// Standalone, read-only identity inspection. No process arguments, environment,
// account settings, memory contents, signals, launchd changes or UU monitoring.
struct Identity {
    let pid: Int32
    let parentPID: UInt32
    let uid: UInt32
    let executable: String
    let startSeconds: UInt64
    let startMicroseconds: UInt64
    let role: String

    var json: [String: Any] {
        ["pid": pid, "parentPID": parentPID, "uid": uid, "executable": executable,
         "startTimeSeconds": startSeconds, "startTimeMicroseconds": startMicroseconds,
         "role": role]
    }
}

enum Native {
    static let prefixes = ["/Applications/AweSun.app/",
                           "/Library/Application Support/Oray/AweSun/AweSun.app/"]
    static let candidateNames: Set<String> = ["AweSun", "AweSun_Helper", "AweSun_Desktop"]

    static func kernelInfo(_ pid: Int32) -> kinfo_proc? {
        var info = kinfo_proc()
        var mib: [Int32] = [CTL_KERN, KERN_PROC, KERN_PROC_PID, pid]
        var size = MemoryLayout<kinfo_proc>.size
        guard sysctl(&mib, UInt32(mib.count), &info, &size, nil, 0) == 0,
              size == MemoryLayout<kinfo_proc>.size else { return nil }
        return info
    }

    static func path(_ pid: Int32) -> String? {
        var bytes = [CChar](repeating: 0, count: 4 * Int(MAXPATHLEN))
        guard proc_pidpath(pid, &bytes, UInt32(bytes.count)) > 0 else { return nil }
        let result = String(cString: bytes)
        return result.hasPrefix("/") ? result : nil
    }

    static func bsdInfo(_ pid: Int32) -> proc_bsdinfo? {
        var info = proc_bsdinfo()
        let size = Int32(MemoryLayout<proc_bsdinfo>.size)
        if proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, size) != size {
            guard let kernel = kernelInfo(pid), kernel.kp_proc.p_pid == pid,
                  kernel.kp_proc.p_starttime.tv_sec > 0 else { return nil }
            info.pbi_pid = UInt32(pid)
            info.pbi_uid = kernel.kp_eproc.e_ucred.cr_uid
            info.pbi_ppid = UInt32(kernel.kp_eproc.e_ppid)
            info.pbi_start_tvsec = UInt64(kernel.kp_proc.p_starttime.tv_sec)
            info.pbi_start_tvusec = UInt64(kernel.kp_proc.p_starttime.tv_usec)
        }
        guard info.pbi_pid == UInt32(pid), info.pbi_start_tvsec > 0,
              info.pbi_start_tvusec < 1_000_000 else { return nil }
        return info
    }

    static func role(_ path: String) -> String {
        guard let prefix = prefixes.first(where: { path.hasPrefix($0) }) else { return "requestedProcess" }
        switch String(path.dropFirst(prefix.count)) {
        case "Contents/MacOS/AweSun": return "gui"
        case "Contents/Helpers/AweSun": return "service"
        case "Contents/Helpers/AweSun_Helper": return "helper"
        case "Contents/Helpers/AweSun_Desktop.app/Contents/MacOS/AweSun_Desktop": return "desktopAgent"
        default: return "otherBundleExecutable"
        }
    }

    static func identity(_ pid: Int32) -> Identity? {
        guard let before = bsdInfo(pid), let beforePath = path(pid),
              let after = bsdInfo(pid), let afterPath = path(pid),
              beforePath == afterPath, before.pbi_uid == after.pbi_uid,
              before.pbi_start_tvsec == after.pbi_start_tvsec,
              before.pbi_start_tvusec == after.pbi_start_tvusec else { return nil }
        return Identity(pid: pid, parentPID: after.pbi_ppid, uid: after.pbi_uid,
                        executable: afterPath, startSeconds: after.pbi_start_tvsec,
                        startMicroseconds: after.pbi_start_tvusec, role: role(afterPath))
    }

    static func fallbackName(_ pid: Int32) -> String? {
        var bytes = [CChar](repeating: 0, count: 256)
        if proc_name(pid, &bytes, UInt32(bytes.count)) > 0 { return String(cString: bytes) }
        guard var info = kernelInfo(pid) else { return nil }
        return withUnsafePointer(to: &info.kp_proc.p_comm) { pointer in
            pointer.withMemoryRebound(to: CChar.self, capacity: Int(MAXCOMLEN) + 1) { String(cString: $0) }
        }
    }

    static func enumerate() -> ([Identity], [[String: Any]], Bool) {
        let requested = proc_listallpids(nil, 0)
        guard requested >= 0 else { return ([], [["reason": "pidEnumerationFailed"]], false) }
        var capacity = max(1024, Int(requested) + 256)
        var pids: [Int32] = []
        var count = 0
        var complete = false
        for _ in 0..<3 {
            pids = [Int32](repeating: 0, count: capacity)
            count = Int(proc_listallpids(&pids, Int32(capacity * MemoryLayout<Int32>.size)))
            guard count >= 0 else { return ([], [["reason": "pidEnumerationFailed"]], false) }
            if count < capacity { complete = true; break }
            capacity *= 2
        }
        var found: [Identity] = []
        var unresolved: [[String: Any]] = []
        if !complete { unresolved.append(["reason": "pidEnumerationCapacityExceeded"]) }
        for pid in Set(pids.prefix(min(count, pids.count))) where pid > 0 {
            guard let executable = path(pid) else {
                if let name = fallbackName(pid), !candidateNames.contains(name) { continue }
                unresolved.append(["pid": pid, "reason": "pathUnavailableOrProcessExited"])
                complete = false
                continue
            }
            guard prefixes.contains(where: { executable.hasPrefix($0) }) else { continue }
            guard let item = identity(pid), item.executable == executable else {
                unresolved.append(["pid": pid, "reason": "identityUnavailableChangedOrProcessExited"])
                complete = false
                continue
            }
            found.append(item)
        }
        return (found.sorted { $0.pid < $1.pid }, unresolved, complete)
    }
}

let args = Array(CommandLine.arguments.dropFirst())
var identities: [Identity] = []
var unresolved: [[String: Any]] = []
var complete = false
var mode = "aweSunBundleInventory"
if args.isEmpty {
    (identities, unresolved, complete) = Native.enumerate()
} else if args.count == 2, args[0] == "--pid", let pid = Int32(args[1]), pid > 0 {
    mode = "specifiedPID"
    if let identity = Native.identity(pid) {
        identities = [identity]
        complete = true
    } else {
        unresolved = [["pid": pid, "reason": "identityUnavailableChangedOrProcessExited"]]
    }
} else {
    fputs("Usage: SunloginProcessInventory [--pid POSITIVE_PID]\n", stderr)
    exit(64)
}
let report: [String: Any] = ["schemaVersion": 1, "mode": mode,
                             "observedAtUTC": ISO8601DateFormatter().string(from: Date()),
                             "observedHostTime": CACurrentMediaTime(),
                             "complete": complete, "enumerationComplete": complete,
                             "processes": identities.map { $0.json }, "unresolved": unresolved,
                             "systemMutationPerformed": false]
do {
    let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([10]))
    exit(complete ? 0 : 2)
} catch {
    fputs("Process identity serialization failed\n", stderr)
    exit(1)
}
