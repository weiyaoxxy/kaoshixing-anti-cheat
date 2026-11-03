import Foundation
import Darwin

/// Read-only, best-effort inspection. A loaded module is not proof of capture interception.
/// `output` is a JSON file URL, not a directory. No raw command output is persisted.
final class UUHookMonitor {
    private let output: URL
    private let queue = DispatchQueue(label: "local.examcapture.uu-hook-monitor", qos: .utility)
    private let lock = NSLock()
    private var refreshing = false
    private var callbacks: [([String: Any]) -> Void] = []
    private var history = UUHMHistory()

    init(output: URL) { self.output = output }

    /// Concurrent refresh requests share one scan; every completion runs on the main queue.
    func refresh(completion: @escaping ([String: Any]) -> Void) {
        lock.lock()
        callbacks.append(completion)
        let shouldStart = !refreshing
        refreshing = true
        lock.unlock()
        guard shouldStart else { return }
        queue.async { [self] in
            var report = UUHMInspection.scan()
            report["historyWriteSucceeded"] = history.record(report, to: output.deletingLastPathComponent().appendingPathComponent("uu-hook-events.jsonl"))
            do {
                try FileManager.default.createDirectory(at: output.deletingLastPathComponent(),
                                                        withIntermediateDirectories: true)
                report["reportWriteSucceeded"] = true
                let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
                try data.write(to: output, options: [.atomic])
                try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: output.path)
            } catch {
                // Error descriptions can contain unrelated paths or values; retain only a category.
                report["reportWriteSucceeded"] = false
                report["reportWriteError"] = "outputWriteFailed"
            }
            lock.lock()
            let pending = callbacks
            callbacks.removeAll()
            refreshing = false
            lock.unlock()
            DispatchQueue.main.async { pending.forEach { $0(report) } }
        }
    }
}

struct UUHMHistory {
    private var previousKey: Data?

    /// Deliberately omit scan timestamps, tool durations and region counts from deduplication.
    mutating func record(_ report: [String: Any], to output: URL) -> Bool {
        let fields = ["pid", "parentPID", "uid", "executable", "role", "startTimeSeconds", "startTimeMicroseconds",
                      "status", "reason", "moduleEvidence", "witnessModuleEvidence", "witnessStatus", "signingIdentity"]
        let processes = (report["processes"] as? [[String: Any]] ?? []).map { row in
            row.filter { fields.contains($0.key) }
        }
        let observation: [String: Any] = ["status": report["status"] ?? "unknown", "processes": processes,
            "components": report["components"] ?? [], "enumerationComplete": report["enumerationComplete"] ?? false]
        guard let key = try? JSONSerialization.data(withJSONObject: observation, options: [.sortedKeys]) else { return false }
        if key == previousKey { return true }
        var event = observation
        event["event"] = "uuHookObservationChanged"
        event["observedAtUTC"] = report["observedAtUTC"] ?? UUHMInspection.timestamp()
        event["locallyMutable"] = true
        event["actualHookInvocationVerified"] = false
        event["captureBlockingVerified"] = false
        event["knownHookIdentityVerified"] = false
        event["moduleNameMatchOnly"] = true
        guard var data = try? JSONSerialization.data(withJSONObject: event, options: [.sortedKeys]) else { return false }
        data.append(0x0a)
        do { try FileManager.default.createDirectory(at: output.deletingLastPathComponent(), withIntermediateDirectories: true) }
        catch { return false }
        let fd = Darwin.open(output.path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { return false }
        defer { Darwin.close(fd) }
        guard fchmod(fd, 0o600) == 0 else { return false }
        let success = data.withUnsafeBytes { bytes -> Bool in
            var written = 0
            while written < bytes.count {
                let count = Darwin.write(fd, bytes.baseAddress!.advanced(by: written), bytes.count - written)
                if count > 0 { written += count }
                else if count < 0 && errno == EINTR { continue }
                else { return false }
            }
            return true
        }
        if success { previousKey = key }
        return success
    }
}

// Internal types deliberately remain accessible to the separate fixture test executable.
struct UUHMCommandResult {
    var exitCode: Int32?
    var stdout: String = ""
    var stderr: String = ""
    var timedOut = false
    var truncated = false
    var launchFailed = false
    var succeeded: Bool { exitCode == 0 && !timedOut && !truncated && !launchFailed }
}

enum UUHMCommand {
    /// Bounded, nonblocking pipe reads avoid pipe-capacity deadlocks. Only the helper that
    /// this function starts may receive TERM/KILL; the inspected UU PID never receives signals.
    static func run(_ executable: String, _ arguments: [String], timeout: TimeInterval,
                    maximumBytes: Int = 8 * 1024 * 1024) -> UUHMCommandResult {
        guard timeout > 0 else { return UUHMCommandResult(timedOut: true) }
        let task = Process()
        let outPipe = Pipe(), errPipe = Pipe()
        task.executableURL = URL(fileURLWithPath: executable)
        task.arguments = arguments
        task.environment = ["PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C", "LANG": "C", "TZ": "UTC"]
        task.standardInput = FileHandle.nullDevice
        task.standardOutput = outPipe
        task.standardError = errPipe
        var out = Data(), err = Data()
        var result = UUHMCommandResult()
        do { try task.run() } catch { return UUHMCommandResult(launchFailed: true) }
        try? outPipe.fileHandleForWriting.close()
        try? errPipe.fileHandleForWriting.close()
        let descriptors = [outPipe.fileHandleForReading.fileDescriptor, errPipe.fileHandleForReading.fileDescriptor]
        for fd in descriptors { _ = fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK) }
        defer {
            try? outPipe.fileHandleForReading.close()
            try? errPipe.fileHandleForReading.close()
        }
        var ended = [false, false]
        let deadline = ProcessInfo.processInfo.systemUptime + timeout
        var stopDeadline: TimeInterval?
        var hardDeadline: TimeInterval?
        var buffer = [UInt8](repeating: 0, count: 16384)
        while true {
            for index in descriptors.indices where !ended[index] {
                // Limit reads per turn so a noisy helper cannot starve the timeout.
                for _ in 0..<64 {
                    let count = Darwin.read(descriptors[index], &buffer, buffer.count)
                    if count > 0 {
                        let available = max(0, maximumBytes - out.count - err.count)
                        let kept = min(count, available)
                        if index == 0 { out.append(contentsOf: buffer.prefix(kept)) }
                        else { err.append(contentsOf: buffer.prefix(kept)) }
                        if kept < count { result.truncated = true }
                    } else {
                        if count == 0 || (errno != EAGAIN && errno != EINTR) { ended[index] = true }
                        break
                    }
                }
            }
            let now = ProcessInfo.processInfo.systemUptime
            if !task.isRunning && ended.allSatisfy({ $0 }) { break }
            if (now >= deadline || result.truncated) && stopDeadline == nil {
                result.timedOut = now >= deadline
                if task.isRunning { task.terminate() }
                stopDeadline = now + 0.15
                hardDeadline = now + 0.6
            }
            if let stop = stopDeadline, now >= stop, task.isRunning {
                _ = Darwin.kill(task.processIdentifier, SIGKILL)
                stopDeadline = .infinity
            }
            if let hard = hardDeadline, now >= hard { break }
            usleep(10_000)
        }
        if !task.isRunning { result.exitCode = task.terminationStatus }
        result.stdout = String(decoding: out, as: UTF8.self)
        result.stderr = String(decoding: err, as: UTF8.self)
        return result
    }
}

struct UUHMProcess: Equatable {
    let pid: Int32
    let parentPID: UInt32
    let uid: UInt32
    let executable: String
    let startSeconds: UInt64
    let startMicroseconds: UInt64
    let role: String

    var identity: [String: Any] {
        ["pid": pid, "parentPID": parentPID, "uid": uid,
         "executable": UUHMInspection.safePath(executable), "role": role,
         "startTimeUTC": UUHMInspection.timestamp(Date(timeIntervalSince1970:
            Double(startSeconds) + Double(startMicroseconds) / 1_000_000)),
         "startTimeSeconds": startSeconds, "startTimeMicroseconds": startMicroseconds,
         "origin": executable.hasPrefix("/Applications/UURemote.app/") ? "installedApplication" : "otherLocation"]
    }

    /// Parent PID can change when a parent exits. It is not part of process birth identity.
    func sameLifetime(as other: UUHMProcess?) -> Bool {
        guard let other = other else { return false }
        return pid == other.pid && uid == other.uid && executable == other.executable
            && startSeconds == other.startSeconds && startMicroseconds == other.startMicroseconds
    }
}

enum UUHMNative {
    static let roles = ["UURemote": "gui", "UURemoteService": "service",
                        "UURemoteServer": "server", "UURemoteDaemon": "daemon"]

    /// macOS can deny libproc BSD/name queries for root-owned processes while allowing
    /// the ordinary read-only KERN_PROC_PID snapshot (also used by process listing tools).
    static func kernelInfo(_ pid: Int32) -> kinfo_proc? {
        var info = kinfo_proc()
        var mib: [Int32] = [CTL_KERN, KERN_PROC, KERN_PROC_PID, pid]
        var size = MemoryLayout<kinfo_proc>.size
        guard sysctl(&mib, UInt32(mib.count), &info, &size, nil, 0) == 0,
              size == MemoryLayout<kinfo_proc>.size else { return nil }
        return info
    }

    static func process(_ pid: Int32, role: String) -> UUHMProcess? {
        var bsd = proc_bsdinfo()
        let size = Int32(MemoryLayout<proc_bsdinfo>.size)
        if proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &bsd, size) != size {
            guard let info = kernelInfo(pid), info.kp_proc.p_starttime.tv_sec > 0 else { return nil }
            bsd.pbi_uid = info.kp_eproc.e_ucred.cr_uid
            bsd.pbi_ppid = UInt32(info.kp_eproc.e_ppid)
            bsd.pbi_start_tvsec = UInt64(info.kp_proc.p_starttime.tv_sec)
            bsd.pbi_start_tvusec = UInt64(info.kp_proc.p_starttime.tv_usec)
        }
        // PROC_PIDPATHINFO_MAXSIZE is the C macro (4 * MAXPATHLEN), not imported by Swift.
        var bytes = [CChar](repeating: 0, count: 4 * Int(MAXPATHLEN))
        guard proc_pidpath(pid, &bytes, UInt32(bytes.count)) > 0 else { return nil }
        let path = String(cString: bytes)
        guard path.hasPrefix("/"), bsd.pbi_start_tvsec > 0 else { return nil }
        return UUHMProcess(pid: pid, parentPID: bsd.pbi_ppid, uid: bsd.pbi_uid,
                           executable: path, startSeconds: bsd.pbi_start_tvsec,
                           startMicroseconds: bsd.pbi_start_tvusec, role: role)
    }

    static func enumerate() -> (processes: [UUHMProcess], unresolved: [[String: Any]], complete: Bool) {
        var capacity = max(1024, Int(proc_listallpids(nil, 0)) + 256)
        var identifiers: [Int32] = []
        var count = 0
        var complete = false
        for _ in 0..<3 {
            identifiers = [Int32](repeating: 0, count: capacity)
            count = Int(proc_listallpids(&identifiers, Int32(capacity * MemoryLayout<Int32>.size)))
            if count < 0 { return ([], [], false) }
            if count < capacity { complete = true; break }
            capacity *= 2
        }
        var found: [UUHMProcess] = [], unresolved: [[String: Any]] = []
        for pid in identifiers.prefix(min(count, identifiers.count)) where pid > 0 {
            var nameBuffer = [CChar](repeating: 0, count: 256)
            let nameLength = proc_name(pid, &nameBuffer, UInt32(nameBuffer.count))
            let name: String
            if nameLength > 0 { name = String(cString: nameBuffer) }
            else if var info = kernelInfo(pid) {
                name = withUnsafePointer(to: &info.kp_proc.p_comm) { pointer in
                    pointer.withMemoryRebound(to: CChar.self, capacity: Int(MAXCOMLEN) + 1) { String(cString: $0) }
                }
            } else {
                // An inaccessible live name prevents a definitive assertion that no UU exists.
                if Darwin.kill(pid, 0) == 0 || errno == EPERM { complete = false }
                continue
            }
            guard let role = roles[name] else { continue }
            guard let item = process(pid, role: role) else {
                unresolved.append(["pid": pid, "role": role, "status": "unknown",
                                   "reason": "processIdentityUnavailableOrExited"])
                continue
            }
            // Check the real executable, not arguments or a mutable process display name.
            guard URL(fileURLWithPath: item.executable).lastPathComponent == name else {
                unresolved.append(["pid": pid, "role": role, "status": "unknown",
                                   "reason": "processNameAndExecutableDisagree"])
                continue
            }
            found.append(item)
        }
        return (found.sorted { $0.pid < $1.pid }, unresolved, complete)
    }
}

enum UUHMInspection {
    static let roles = ["gui", "service", "server", "daemon"]
    static let hookPattern = #"^libCaptureHook(?:[-.][A-Za-z0-9_.-]+)?\.dylib$"#
    static let witnessPattern = #"^libLoadWitness(?:[-.][A-Za-z0-9_.-]+)?\.dylib$"#

    static func timestamp(_ date: Date = Date()) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: date)
    }

    static func safePath(_ value: String) -> String {
        value.replacingOccurrences(of: #"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"#,
                                   with: "<redacted-uuid>", options: .regularExpression)
    }

    static func remaining(_ deadline: TimeInterval, maximum: TimeInterval) -> TimeInterval {
        max(0, min(maximum, deadline - ProcessInfo.processInfo.systemUptime))
    }

    static func capture(_ pattern: String, in text: String) -> String? {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.anchorsMatchLines]),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              match.numberOfRanges > 1, let range = Range(match.range(at: 1), in: text) else { return nil }
        return String(text[range])
    }

    static func failure(_ result: UUHMCommandResult) -> String {
        if result.launchFailed { return "inspectionToolUnavailable" }
        if result.timedOut { return "inspectionTimedOut" }
        if result.truncated { return "inspectionOutputLimitExceeded" }
        let message = result.stderr.lowercased() + result.stdout.lowercased()
        if ["permission", "privileges", "not permitted", "not allowed", "task_for_pid", "access denied"].contains(where: message.contains) {
            return "inspectionPermissionDenied"
        }
        return "inspectionFailed"
    }

    /// Accept only executable __TEXT image regions and verify vmmap's PID/path header.
    /// A file mapping, header, footer, or arbitrary substring does not prove image loading.
    static func classify(_ result: UUHMCommandResult, process: UUHMProcess,
                         current: UUHMProcess?) -> [String: Any] {
        var value: [String: Any] = ["status": "unknown", "moduleEvidence": [],
                                    "witnessModuleEvidence": [], "actualHookInvocationVerified": false,
                                    "knownHookIdentityVerified": false, "moduleNameMatchOnly": true,
                                    "captureBlockingVerified": false,
                                    "vmmapTimedOut": result.timedOut,
                                    "vmmapOutputTruncated": result.truncated]
        value["vmmapExitCode"] = result.exitCode.map { Int($0) } ?? NSNull() as Any
        guard process.sameLifetime(as: current) else {
            value["reason"] = "processExitedOrIdentityChangedDuringInspection"
            return value
        }
        guard result.succeeded else { value["reason"] = failure(result); return value }
        let reportedPID = capture(#"^Process:\s+.*\[([0-9]+)\]\s*$"#, in: result.stdout)
        let reportedPath = capture(#"^Path:\s+(.+?)\s*$"#, in: result.stdout)
        var executableRegionCount = 0
        var hookPaths = Set<String>(), witnessPaths = Set<String>()
        var executablePaths: [String] = []
        for line in result.stdout.split(separator: "\n") {
            // -wide prevents truncation; the only retained part is a recognized module path.
            guard let path = capture(#"^__TEXT\s+[0-9a-fA-F]+-[0-9a-fA-F]+\s+\[[^\]]+\]\s+r-x/[rwx-]{3}\s+\S+\s+(/.+?)\s*$"#, in: String(line)) else { continue }
            executableRegionCount += 1
            executablePaths.append(path)
            let name = URL(fileURLWithPath: path).lastPathComponent
            if name.range(of: hookPattern, options: .regularExpression) != nil { hookPaths.insert(safePath(path)) }
            if name.range(of: witnessPattern, options: .regularExpression) != nil { witnessPaths.insert(safePath(path)) }
        }
        func canonical(_ path: String) -> String { URL(fileURLWithPath: path).resolvingSymlinksInPath().path }
        let directPathMatch = reportedPath.map { canonical($0) == canonical(process.executable) } ?? false
        // vmmap can redact temporary-directory headers as /private/var/folders/*/name.
        // In that case require a non-redacted main executable region as well as native lifetime identity.
        let redactedPathMatch = reportedPath?.contains("*") == true && executablePaths.contains {
            canonical($0) == canonical(process.executable)
        }
        guard reportedPID == String(process.pid), directPathMatch || redactedPathMatch else {
            value["reason"] = "vmmapIdentityHeaderUnavailableOrMismatched"
            return value
        }
        value["vmmapHeaderPathRedacted"] = redactedPathMatch && !directPathMatch
        guard executableRegionCount > 0 else {
            value["reason"] = "noUsableExecutableMappings"
            return value
        }
        value["status"] = hookPaths.isEmpty ? "noKnownHookObserved" : "observedLoaded"
        value["reason"] = hookPaths.isEmpty ? "knownCaptureHookNameNotFoundInCurrentExecutableMappings" : "knownCaptureHookNameMappedExecutable"
        value["moduleEvidence"] = hookPaths.sorted().map { ["path": $0, "evidence": "currentExecutableTextMapping", "identityBasis": "moduleFilenameOnly"] }
        value["witnessModuleEvidence"] = witnessPaths.sorted().map { ["path": $0, "evidence": "currentExecutableTextMapping", "identityBasis": "moduleFilenameOnly"] }
        value["witnessStatus"] = witnessPaths.isEmpty ? "noKnownWitnessObserved" : "observedLoaded"
        value["executableRegionCount"] = executableRegionCount
        return value
    }

    static func signingIdentity(_ path: String, deadline: TimeInterval) -> [String: Any] {
        let result = UUHMCommand.run("/usr/bin/codesign", ["-d", "--verbose=4", path],
                                    timeout: remaining(deadline, maximum: 1), maximumBytes: 65536)
        guard result.succeeded else { return ["status": "unknown", "reason": failure(result)] }
        var value: [String: Any] = ["status": "metadataObserved", "basis": "executableOnDiskAtInspectionTime",
                                    "signatureValidityVerified": false, "runningCodeAuthenticityVerified": false]
        for (prefix, key) in [("Identifier", "identifier"), ("TeamIdentifier", "teamIdentifier")] {
            if let text = capture("^" + prefix + "=(.+)$", in: result.stderr),
               text.range(of: #"^[A-Za-z0-9_. -]{1,160}$"#, options: .regularExpression) != nil { value[key] = text }
        }
        value["adHoc"] = result.stderr.contains("(adhoc,") || result.stderr.contains("(adhoc)") || result.stderr.contains("Signature=adhoc")
        return value
    }

    static func launchJob(_ target: String, deadline: TimeInterval) -> [String: Any] {
        let result = UUHMCommand.run("/bin/launchctl", ["print", target],
                                    timeout: remaining(deadline, maximum: 1), maximumBytes: 256 * 1024)
        var value: [String: Any] = ["target": target]
        if result.exitCode == 113 && !result.timedOut && !result.truncated {
            value["status"] = "notRegistered"
            return value
        }
        guard result.succeeded else { value["status"] = "unknown"; value["reason"] = failure(result); return value }
        value["status"] = "observed"
        for key in ["path", "program", "state", "pid"] {
            if let text = capture(#"^\s*"# + key + #"\s*=\s*(.*?)\s*$"#, in: result.stdout) {
                if key == "pid" { value[key] = Int(text) }
                else { value[key] = safePath(text) }
            }
        }
        // Names only: never emit launchd environment values or ProgramArguments.
        let pattern = #"(?m)^\s*((?:DYLD_|HOOK_DEMO_)[A-Za-z0-9_]+)\s*=>"#
        let regex = try! NSRegularExpression(pattern: pattern)
        value["experimentalEnvironmentKeys"] = regex.matches(in: result.stdout, range: NSRange(result.stdout.startIndex..., in: result.stdout)).compactMap {
            Range($0.range(at: 1), in: result.stdout).map { String(result.stdout[$0]) }
        }.sorted()
        return value
    }

    static func scan() -> [String: Any] {
        let started = timestamp()
        let deadline = ProcessInfo.processInfo.systemUptime + 9
        let enumeration = UUHMNative.enumerate()
        let jobs = [launchJob("gui/\(getuid())/com.netease.uuremote.agent", deadline: deadline),
                    launchJob("system/com.netease.uuremote.daemon", deadline: deadline)]
        var records: [[String: Any]] = []
        for process in enumeration.processes {
            let result = UUHMCommand.run("/usr/bin/vmmap", ["-w", String(process.pid)],
                                        timeout: remaining(deadline, maximum: 2.5))
            var record = process.identity
            record.merge(classify(result, process: process, current: UUHMNative.process(process.pid, role: process.role))) { _, new in new }
            record["signingIdentity"] = signingIdentity(process.executable, deadline: deadline)
            record["launchdAssociation"] = jobs.first { ($0["pid"] as? Int) == Int(process.pid) && ($0["program"] as? String) == safePath(process.executable) }
                .map { ["target": $0["target"] as? String ?? "", "basis": "currentJobPIDAndProgramMatch"] } ?? ["basis": "notObserved"]
            records.append(record)
        }
        records.append(contentsOf: enumeration.unresolved)
        let states = records.compactMap { $0["status"] as? String }
        let status: String
        if states.contains("observedLoaded") { status = "observedLoaded" }
        else if states.contains("unknown") || !enumeration.complete { status = "unknown" }
        else if records.isEmpty { status = "notRunning" }
        else { status = "noKnownHookObserved" }
        let componentStates: [[String: Any]] = roles.map { role in
            let rows = records.filter { $0["role"] as? String == role }
            let values = rows.compactMap { $0["status"] as? String }
            let state = values.contains("observedLoaded") ? "observedLoaded" :
                values.contains("unknown") || !enumeration.complete ? "unknown" : rows.isEmpty ? "notRunning" : "noKnownHookObserved"
            return ["role": role, "status": state, "pids": rows.compactMap { $0["pid"] as? Int32 }]
        }
        let checkedCount = states.filter { $0 != "unknown" }.count
        let summary: String
        switch status {
        case "observedLoaded": summary = "UU 发现匹配 Hook 文件名的已加载模块；库身份和实际拦截均未验证"
        case "unknown":
            let coverage = enumeration.complete ? "\(records.count - checkedCount) 个进程的 Hook 状态未知" : "另有进程枚举受限"
            summary = "UU 已识别 \(records.count) 个进程，\(checkedCount) 个完成映射检查；\(coverage)"
        case "notRunning": summary = "未发现运行中的 UU 组件"
        default: summary = "UU 当前可检查进程未发现已知 Hook；不代表没有其他注入"
        }
        return ["schemaVersion": 1, "scanStartedAtUTC": started, "observedAtUTC": timestamp(),
                "status": status, "summary": summary, "components": componentStates, "processes": records, "launchdJobs": jobs,
                "enumerationComplete": enumeration.complete, "actualHookInvocationVerified": false,
                "knownHookIdentityVerified": false, "moduleNameMatchOnly": true,
                "captureBlockingVerified": false, "systemMutationPerformed": false,
                "limitations": [
                    "Matches known CaptureHook module filenames in executable mappings; renamed modules and other injection methods can be missed, and matching names alone do not prove library authenticity.",
                    "A loaded module does not prove hook installation, capture callbacks, blocking, or remote-session success.",
                    "No historical hook logs, account/device identifiers, credentials, full arguments, environment values, or raw vmmap output are collected into this report.",
                    "Code-signing fields describe files on disk; running-code trust is not attested. UU components are selected by executable name and reported with actual path and signing metadata.",
                    "Permissions, process churn, or deadlines can prevent inspection. Unknown is never converted to a clean result.",
                    "A scan is a short series of observations, not an atomic system snapshot. No continual monitoring or anti-tamper guarantee is implied.",
                    "The JSON snapshot and deduplicated JSONL history are locally writable evidence, not tamper-proof or remotely attested audit records."
                ]]
    }
}
