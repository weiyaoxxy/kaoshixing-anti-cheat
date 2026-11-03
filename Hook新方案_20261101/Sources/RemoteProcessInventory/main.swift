import Foundation
import Darwin
import QuartzCore
import Security
import CryptoKit

// Schema v2: all PID discovery. Name/path hints NEVER authenticate or filter.
// Security calls execute in an owned worker; the supervisor enforces a deadline.
// Only the supervisor's own unreaped child can be signaled on timeout. Observed
// processes are never signaled, attached, restarted, or otherwise modified.

struct Candidate { let vendors: [String]; let role: String; let basis: [String] }
enum NativeInventory {
    static func kernelInfo(_ pid: Int32) -> kinfo_proc? {
        var info = kinfo_proc()
        var mib: [Int32] = [CTL_KERN, KERN_PROC, KERN_PROC_PID, pid]
        var size = MemoryLayout<kinfo_proc>.size
        guard sysctl(&mib, UInt32(mib.count), &info, &size, nil, 0) == 0,
              size == MemoryLayout<kinfo_proc>.size, info.kp_proc.p_pid == pid
        else { return nil }
        return info
    }

    static func bsdInfo(_ pid: Int32) -> proc_bsdinfo? {
        var info = proc_bsdinfo()
        let size = Int32(MemoryLayout<proc_bsdinfo>.size)
        if proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, size) != size {
            // A root-owned service can deny PROC_PIDTBSDINFO while permitting
            // KERN_PROC_PID, the ordinary read-only process-list snapshot.
            guard let fallback = kernelInfo(pid), fallback.kp_proc.p_starttime.tv_sec > 0,
                  fallback.kp_proc.p_starttime.tv_usec >= 0 else { return nil }
            info.pbi_pid = UInt32(pid)
            info.pbi_uid = fallback.kp_eproc.e_ucred.cr_uid
            info.pbi_ppid = UInt32(fallback.kp_eproc.e_ppid)
            info.pbi_status = UInt32(fallback.kp_proc.p_stat)
            info.pbi_start_tvsec = UInt64(fallback.kp_proc.p_starttime.tv_sec)
            info.pbi_start_tvusec = UInt64(fallback.kp_proc.p_starttime.tv_usec)
        }
        guard info.pbi_pid == UInt32(pid), info.pbi_start_tvsec > 0,
              info.pbi_start_tvusec < 1_000_000 else { return nil }
        return info
    }

    static func executablePath(_ pid: Int32) -> String? {
        var bytes = [CChar](repeating: 0, count: 4 * Int(MAXPATHLEN))
        guard proc_pidpath(pid, &bytes, UInt32(bytes.count)) > 0 else { return nil }
        let path = String(cString: bytes)
        return path.hasPrefix("/") ? path : nil
    }

    static func fallbackName(_ pid: Int32) -> String? {
        var bytes = [CChar](repeating: 0, count: 256)
        if proc_name(pid, &bytes, UInt32(bytes.count)) > 0 { return String(cString: bytes) }
        guard var info = kernelInfo(pid) else { return nil }
        return withUnsafePointer(to: &info.kp_proc.p_comm) { pointer in
            pointer.withMemoryRebound(to: CChar.self, capacity: Int(MAXCOMLEN) + 1) {
                String(cString: $0)
            }
        }
    }

    static func nameVendors(_ name: String) -> Set<String> {
        let name = name.lowercased()
        var vendors: Set<String> = []
        if name.hasPrefix("todesk") || name.hasPrefix("com.youqu.todesk.") { vendors.insert("todesk") }
        if name.hasPrefix("uuremote") || name.hasPrefix("com.netease.uuremote.") { vendors.insert("uu") }
        if name.hasPrefix("awesun") || name.hasPrefix("sunlogin") ||
            name.hasPrefix("com.oray.awesun.") || name.hasPrefix("com.oray.sunlogin.") {
            vendors.insert("sunlogin")
        }
        return vendors
    }

    static func candidate(_ executable: String) -> Candidate {
        let url = URL(fileURLWithPath: executable)
        let name = url.lastPathComponent.lowercased()
        let parts = url.pathComponents.map { $0.lowercased() }
        var vendors = nameVendors(name)
        var basis = vendors.isEmpty ? [] : ["actualExecutableBasename"]
        let bundleVendors = Set(parts.flatMap { part -> [String] in
            guard part.hasSuffix(".app") else { return [] }
            if part.hasPrefix("todesk") { return ["todesk"] }
            if part.hasPrefix("uuremote") { return ["uu"] }
            if part.hasPrefix("awesun") || part.hasPrefix("sunlogin") { return ["sunlogin"] }
            return []
        })
        vendors.formUnion(bundleVendors)
        if !bundleVendors.isEmpty { basis.append("actualExecutableBundleComponent") }
        if parts.contains("todesk") && executable.lowercased().hasPrefix("/library/application support/") {
            vendors.insert("todesk"); basis.append("knownSupportDirectory")
        }
        if executable.lowercased().hasPrefix("/library/application support/oray/awesun/") ||
            executable.lowercased().hasPrefix("/library/application support/oray/sunlogin/") {
            vendors.insert("sunlogin"); basis.append("knownSupportDirectory")
        }
        var role = vendors.isEmpty ? "otherProcess" : "otherVendorComponent"
        switch name {
        case "todesk", "uuremote": role = "gui"
        case "todesk_service", "uuremoteservice": role = "service"
        case "todesk_session_proxy": role = "sessionProxy"
        case "todesk_session": role = "session"
        case "uuremoteserver": role = "server"
        case "uuremotedaemon": role = "daemon"
        case "uuremotehelper", "todesk_xpchelper", "awesun_helper": role = "helper"
        case "todesk_screenwall_helper": role = "screenwallHelper"
        case "awesun_desktop", "sunloginclient_desktop": role = "desktopAgent"
        case "awesun":
            if executable.hasSuffix("/Contents/Helpers/AweSun") { role = "service" }
            else if executable.hasSuffix("/Contents/MacOS/AweSun") { role = "gui" }
        default:
            if !vendors.isEmpty {
                if name.contains("uninstall") { role = "uninstaller" }
                else if name.contains("updat") || name == "installer" || name == "downloader" { role = "updater" }
                else if name.contains("crash") { role = "crashReporter" }
                else if name.contains("helper") { role = "helper" }
            }
        }
        return Candidate(vendors: vendors.sorted(), role: role, basis: Array(Set(basis)).sorted())
    }

    static func allPIDs() -> ([Int32], Bool) {
        let count = proc_listallpids(nil, 0)
        guard count >= 0 else { return ([], false) }
        var capacity = max(1024, Int(count) + 256)
        for _ in 0..<4 {
            var pids = [Int32](repeating: 0, count: capacity)
            let observed = Int(proc_listallpids(&pids, Int32(capacity * 4)))
            guard observed >= 0 else { return ([], false) }
            if observed < capacity {
                return (Set(pids.prefix(observed)).filter { $0 > 0 }.sorted(), true)
            }
            capacity *= 2
        }
        return ([], false)
    }
}

func utc() -> String { ISO8601DateFormatter().string(from: Date()) }
func hex(_ data: Data) -> String { data.map { String(format: "%02x", $0) }.joined() }
func hash(_ data: Data) -> String { hex(Data(SHA256.hash(data: data))) }
func quoteRequirement(_ s: String) -> String {
    "\"" + s.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"") + "\""
}
func emit(_ value: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) else { exit(70) }
    FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10]))
}
func fileIdentity(_ path: String?) -> [String: Any]? {
    guard let path else { return nil }
    var s = stat()
    guard lstat(path, &s) == 0 else { return nil }
    return ["device": s.st_dev, "inode": s.st_ino, "bytes": s.st_size,
            "mtimeSeconds": s.st_mtimespec.tv_sec, "mtimeNanoseconds": s.st_mtimespec.tv_nsec,
            "ctimeSeconds": s.st_ctimespec.tv_sec, "ctimeNanoseconds": s.st_ctimespec.tv_nsec,
            "mode": s.st_mode, "ownerUID": s.st_uid]
}
func sameDict(_ a: [String: Any]?, _ b: [String: Any]?) -> Bool {
    guard let a, let b else { return false }
    return NSDictionary(dictionary: a).isEqual(to: b)
}
func metadata(_ code: SecCode) -> ([String: Any], SecStaticCode?, OSStatus) {
    var disk: SecStaticCode?
    let copyStatus = SecCodeCopyStaticCode(code, [], &disk)
    guard copyStatus == errSecSuccess, let disk else { return ([:], nil, copyStatus) }
    var information: CFDictionary?
    let status = SecCodeCopySigningInformation(disk, SecCSFlags(rawValue: kSecCSSigningInformation), &information)
    guard status == errSecSuccess, let raw = information as? [String: Any] else { return ([:], disk, status) }
    var answer: [String: Any] = [:]
    for (source, target) in [(kSecCodeInfoIdentifier, "Identifier"), (kSecCodeInfoTeamIdentifier, "TeamIdentifier"),
                             (kSecCodeInfoFormat, "Format")] {
        if let value = raw[source as String] as? String { answer[target] = value }
    }
    if let digest = raw[kSecCodeInfoUnique as String] as? Data { answer["CDHash"] = hex(digest) }
    if let flags = raw[kSecCodeInfoFlags as String] as? NSNumber { answer["SigningFlags"] = flags }
    if let executable = raw[kSecCodeInfoMainExecutable as String] as? URL { answer["SignedExecutable"] = executable.path }
    answer["source"] = "staticReferenceFromRunningCode; metadataUntrustedUntilValidation"
    return (answer, disk, status)
}
func statusEvidence(_ status: OSStatus, error: Unmanaged<CFError>? = nil) -> [String: Any] {
    // Treat only known validation failures as failed; new OS errors, permissions,
    // unsupported APIs and missing objects remain unknown rather than app tampering.
    let invalid: Set<OSStatus> = [errSecCSGuestInvalid, errSecCSUnsigned, errSecCSSignatureFailed,
        errSecCSResourcesNotSealed, errSecCSResourcesNotFound, errSecCSResourcesInvalid,
        errSecCSBadResource, errSecCSReqFailed, errSecCSStaticCodeChanged, errSecCSInfoPlistFailed,
        errSecCSResourceDirectoryFailed, errSecCSUnsignedNestedCode, errSecCSBadNestedCode]
    var result: [String: Any] = ["status": status == 0 ? "verified" : invalid.contains(status) ? "failed" : "unknown",
                                "OSStatus": status]
    if let error { result["diagnostic"] = String(CFErrorCopyDescription(error.takeRetainedValue()) as String).prefix(1200).description }
    else if let message = SecCopyErrorMessageString(status, nil) { result["diagnostic"] = message as String }
    return result
}
func match(_ meta: [String: Any], policy: [String: Any]) -> [(String, String, String)] {
    guard let vendors = policy["vendors"] as? [String: [String: Any]],
          let identifier = meta["Identifier"] as? String else { return [] }
    var results: [(String, String, String)] = []
    for (vendor, definition) in vendors {
        guard let ids = definition["identifiers"] as? [String: String], let role = ids[identifier] else { continue }
        if policy["testOnly"] as? Bool == true {
            guard let allowed = definition["testCDHashes"] as? [String], let cdhash = meta["CDHash"] as? String,
                  allowed.contains(cdhash) else { continue }
            results.append((vendor, role, "identifier " + quoteRequirement(identifier) + " and cdhash H\"" + cdhash + "\""))
            continue
        }
        guard let team = definition["teamID"] as? String, meta["TeamIdentifier"] as? String == team else { continue }
        var requirement = "anchor apple generic and certificate leaf[subject.OU] = " + quoteRequirement(team)
            + " and identifier " + quoteRequirement(identifier)
        if let pins = definition["requiredCDHashes"] as? [String: [String]], let allowed = pins[identifier] {
            guard !allowed.isEmpty, let cdhash = meta["CDHash"] as? String, allowed.contains(cdhash) else { continue }
            requirement += " and cdhash H\"" + cdhash + "\""
        }
        results.append((vendor, role, requirement))
    }
    return results
}
func birth(_ info: proc_bsdinfo?) -> [String: Any]? {
    guard let i = info else { return nil }
    return ["uid": i.pbi_uid, "startTimeSeconds": i.pbi_start_tvsec, "startTimeMicroseconds": i.pbi_start_tvusec]
}
func inspect(_ pid: Int32, policy: [String: Any], includeStatic: Bool) -> [String: Any] {
    let began = CACurrentMediaTime()
    let before = NativeInventory.bsdInfo(pid), path = NativeInventory.executablePath(pid)
    let hint = path.map(NativeInventory.candidate) ?? Candidate(vendors: NativeInventory.fallbackName(pid).map { NativeInventory.nameVendors($0).sorted() } ?? [], role: "unknown", basis: ["unverifiedProcessNameHint"])
    var row: [String: Any] = ["pid": pid, "executable": path as Any? ?? NSNull(),
        "candidateVendors": hint.vendors, "role": hint.role, "discoveryBasis": hint.basis,
        "identityStrength": path == nil ? "pidBirthOnly" : "pidBirthPath", "samePIDExecCoverageGuaranteed": false,
        "remoteSessionVerified": false, "runningMemoryAttested": false, "observedAtUTC": utc()]
    if let before { row.merge(birth(before)!) { _, new in new }; row["parentPID"] = before.pbi_ppid }
    let fileBefore = fileIdentity(path)
    var code: SecCode?
    let guestStatus = SecCodeCopyGuestWithAttributes(nil, [kSecGuestAttributePid as String: pid] as CFDictionary, [], &code)
    var evidence: [String: Any] = ["guestOSStatus": guestStatus, "source": "Security.framework",
        "dynamicValidation": ["status": "unknown"], "staticValidation": ["status": "notRequested"],
        "metadata": [:], "metadataStatus": "unavailable", "matchedVendors": []]
    var verified: (String, String)?
    var category = "inspectionUnavailable"
    if guestStatus == errSecSuccess, let code {
        let (meta, disk, metadataStatus) = metadata(code)
        evidence["metadata"] = meta; evidence["metadataOSStatus"] = metadataStatus
        evidence["metadataStatus"] = metadataStatus == 0 ? "availableUnvalidated" : "unavailable"
        let matches = match(meta, policy: policy)
        evidence["matchedVendors"] = matches.map { $0.0 }
        if metadataStatus == 0 {
            // Apple platform code can be properly signed without a Team ID.
            // Absence of TeamIdentifier alone must not mean unsigned/ad-hoc.
            let signingFlags = (meta["SigningFlags"] as? NSNumber)?.uint32Value ?? 0
            category = signingFlags & 0x2 != 0 ? "unsignedOrAdHocCode" : "unknownSignedCode"
            evidence["dynamicValidation"] = ["status": "notRequested", "reason": "notInKnownComponentCatalogue"]
            if matches.count == 1 {
                let found = matches[0]
                var requirement: SecRequirement?
                let reqStatus = SecRequirementCreateWithString(found.2 as CFString, [], &requirement)
                evidence["requirement"] = found.2
                evidence["requirementSHA256"] = hash(Data(found.2.utf8))
                evidence["requirementOSStatus"] = reqStatus
                if reqStatus == 0, let requirement {
                    var dynamicError: Unmanaged<CFError>?
                    let dynamicStatus = SecCodeCheckValidityWithErrors(code, [], requirement, &dynamicError)
                    evidence["dynamicValidation"] = statusEvidence(dynamicStatus, error: dynamicError)
                    if dynamicStatus == 0 { verified = (found.0, found.1); category = "knownRemoteIdentityVerified" }
                    else { category = (evidence["dynamicValidation"] as? [String: Any])?["status"] as? String == "unknown" ? "inspectionUnavailable" : "knownMetadataButValidationFailed" }
                    if includeStatic, let disk {
                        var staticError: Unmanaged<CFError>?
                        let staticStatus = SecStaticCodeCheckValidityWithErrors(disk, SecCSFlags(rawValue: kSecCSStrictValidate), requirement, &staticError)
                        var answer = statusEvidence(staticStatus, error: staticError)
                        answer["scope"] = "Security static reference for running architecture; strict; nested code not recursively attested"
                        evidence["staticValidation"] = answer
                    }
                } else { category = "inspectionUnavailable"; evidence["reason"] = "invalidPolicyRequirement" }
            }
        } else if metadataStatus == errSecCSUnsigned {
            category = "unsignedOrAdHocCode"
            evidence["dynamicValidation"] = statusEvidence(metadataStatus)
        }
    } else {
        evidence["dynamicValidation"] = statusEvidence(guestStatus)
        if guestStatus == errSecCSUnsigned { category = "unsignedOrAdHocCode" }
    }
    let after = NativeInventory.bsdInfo(pid), afterPath = NativeInventory.executablePath(pid)
    let stable = sameDict(birth(before), birth(after)) && path == afterPath
    row["identityStableAcrossReads"] = stable
    row["processStableAfterVerification"] = stable
    if let before { row["kernelProcessStatusBefore"] = before.pbi_status }
    if let after { row["kernelProcessStatusAfter"] = after.pbi_status }
    row["fileBefore"] = fileBefore as Any? ?? NSNull()
    row["fileAfter"] = fileIdentity(afterPath) as Any? ?? NSNull()
    row["fileStableAcrossVerification"] = sameDict(fileBefore, fileIdentity(afterPath))
    if !stable || (fileBefore != nil && !sameDict(fileBefore, fileIdentity(afterPath))) {
        verified = nil; category = "processExitedOrChanged"
    }
    // Kernel SZOMB denotes an already exited process awaiting reaping. Require
    // two matching birth identities and two kernel state observations; names do
    // not authorize this exclusion. Preserve the unsuccessful code query below.
    if stable, before?.pbi_status == UInt32(SZOMB), after?.pbi_status == UInt32(SZOMB) {
        verified = nil; category = "nonExecutingZombie"
        row["activeExecutionExcludedReason"] = "stableKernelZombieStateBeforeAndAfter"
    }
    if let verified {
        // Reacquire and compare the kernel-selected code object's metadata. Same-PID
        // exec of the identical image remains an explicit non-ES coverage limit.
        var second: SecCode?
        let secondStatus = SecCodeCopyGuestWithAttributes(nil, [kSecGuestAttributePid as String: pid] as CFDictionary, [], &second)
        let firstMeta = evidence["metadata"] as? [String: Any]
        let secondMeta = second.map { metadata($0).0 }
        var finalRequirement: SecRequirement?
        let finalRequirementStatus = SecRequirementCreateWithString((evidence["requirement"] as! String) as CFString, [], &finalRequirement)
        let finalValidation = second.flatMap { code in finalRequirement.map { SecCodeCheckValidity(code, [], $0) } } ?? errSecCSNoSuchCode
        evidence["dynamicRevalidationOSStatus"] = finalValidation
        if secondStatus == 0 && finalRequirementStatus == 0 && finalValidation == 0 && sameDict(firstMeta, secondMeta) {
            row["verifiedVendor"] = verified.0; row["verifiedRole"] = verified.1
            evidence["verifiedVendor"] = verified.0; evidence["verifiedRole"] = verified.1
        } else { category = "processExitedOrChanged"; evidence["reinspectionOSStatus"] = secondStatus }
    }
    row["status"] = category == "knownRemoteIdentityVerified" ? "verifiedComponentRunning" : category
    row["category"] = category
    row["codeIdentity"] = evidence
    row["signatureEvaluated"] = true
    row["inspectionSeconds"] = CACurrentMediaTime() - began
    return row
}

func validPolicy(_ policy: [String: Any], allowTest: Bool) -> Bool {
    guard let version = policy["policyVersion"] as? String, !version.isEmpty,
          let vendors = policy["vendors"] as? [String: [String: Any]], !vendors.isEmpty else { return false }
    if policy["testOnly"] as? Bool == true && !allowTest { return false }
    for definition in vendors.values {
        guard let ids = definition["identifiers"] as? [String: String], !ids.isEmpty else { return false }
        if policy["testOnly"] as? Bool == true {
            guard let hashes = definition["testCDHashes"] as? [String], !hashes.isEmpty,
                  hashes.allSatisfy({ $0.range(of: "^[0-9a-f]{40}$", options: .regularExpression) != nil }) else { return false }
        } else {
            guard let team = definition["teamID"] as? String,
                  team.range(of: "^[A-Z0-9]{10}$", options: .regularExpression) != nil else { return false }
            if definition["requiredCDHashes"] != nil {
                guard let pins = definition["requiredCDHashes"] as? [String: [String]],
                      pins.keys.allSatisfy({ ids[$0] != nil }),
                      pins.values.allSatisfy({ !$0.isEmpty && $0.allSatisfy({ $0.range(of: "^[0-9a-f]{40}$", options: .regularExpression) != nil }) }) else { return false }
            }
        }
    }
    return true
}

let arguments = Array(CommandLine.arguments.dropFirst())
if arguments == ["--worker"] {
    guard let request = try? JSONSerialization.jsonObject(with: FileHandle.standardInput.readDataToEndOfFile()) as? [String: Any],
          let pids = request["pids"] as? [Int32], let policy = request["policy"] as? [String: Any],
          let expectedParent = request["supervisorPID"] as? Int32, expectedParent > 1,
          let workerBudget = request["budgetSeconds"] as? Double, workerBudget > 0, workerBudget <= 120,
          validPolicy(policy, allowTest: request["allowTest"] as? Bool == true) else { exit(64) }
    guard getppid() == expectedParent else { _exit(125) }
    // Independent exit path if the supervisor itself is killed. This is not
    // cancellation of a Swift Security task: the entire owned worker exits.
    let workerDeadline = CACurrentMediaTime() + workerBudget
    let watchdog = DispatchSource.makeTimerSource(queue: DispatchQueue.global(qos: .userInitiated))
    watchdog.schedule(deadline: .now() + .milliseconds(50), repeating: .milliseconds(50))
    watchdog.setEventHandler {
        if getppid() != expectedParent { _exit(125) }
        if CACurrentMediaTime() >= workerDeadline { _exit(124) }
    }
    watchdog.resume()
    for pid in pids { autoreleasepool { emit(inspect(pid, policy: policy, includeStatic: request["includeStatic"] as? Bool ?? true)) } }
    exit(0)
}

var selectedPID: Int32?, policyPath: String?, budget = 12.0, allowTest = false, includeStatic = true
var index = 0
while index < arguments.count {
    let arg = arguments[index]
    if arg == "--allow-test-policy" { allowTest = true; index += 1; continue }
    if arg == "--skip-static" { includeStatic = false; index += 1; continue }
    guard index + 1 < arguments.count else { fputs("Missing option value\n", stderr); exit(64) }
    let value = arguments[index + 1]
    switch arg {
    case "--pid": guard let n = Int32(value), n > 0 else { exit(64) }; selectedPID = n
    case "--policy": policyPath = value
    case "--budget": guard let n = Double(value), n.isFinite, n > 0, n <= 120 else { exit(64) }; budget = n
    default: fputs("Usage: RemoteProcessInventory [--pid N] [--policy PATH] [--budget SECONDS] [--skip-static] [--allow-test-policy]\n", stderr); exit(64)
    }
    index += 2
}
let executable = URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL.path
let policyURL = URL(fileURLWithPath: policyPath ?? URL(fileURLWithPath: executable).deletingLastPathComponent().appendingPathComponent("policy.json").path)
guard let policyBytes = try? Data(contentsOf: policyURL),
      let policy = try? JSONSerialization.jsonObject(with: policyBytes) as? [String: Any],
      validPolicy(policy, allowTest: allowTest) else { fputs("Invalid/unreadable policy, or test policy not explicitly allowed\n", stderr); exit(64) }
let started = utc(), began = CACurrentMediaTime()
let (enumerated, enumerationOK) = selectedPID.map { ([$0], true) } ?? NativeInventory.allPIDs()
// Prioritize hints for timely positive evidence but never omit unhinted PIDs.
let hintPriority = Dictionary(uniqueKeysWithValues: enumerated.map { pid in
    (pid, NativeInventory.executablePath(pid).map { !NativeInventory.candidate($0).vendors.isEmpty } ?? false)
})
let pids = enumerated.sorted { a, b in
    let aHint = hintPriority[a]!, bHint = hintPriority[b]!
    return aHint == bHint ? a < b : aHint
}
var inputPipe: [Int32] = [0, 0], outputPipe: [Int32] = [0, 0]
guard pipe(&inputPipe) == 0, pipe(&outputPipe) == 0 else { exit(71) }
var actions: posix_spawn_file_actions_t?
posix_spawn_file_actions_init(&actions)
posix_spawn_file_actions_adddup2(&actions, inputPipe[0], STDIN_FILENO)
posix_spawn_file_actions_adddup2(&actions, outputPipe[1], STDOUT_FILENO)
for fd in inputPipe + outputPipe { posix_spawn_file_actions_addclose(&actions, fd) }
let argv: [UnsafeMutablePointer<CChar>?] = [strdup(executable), strdup("--worker"), nil]
let workerEnvironment: [UnsafeMutablePointer<CChar>?] = ProcessInfo.processInfo.environment
    .filter { !$0.key.hasPrefix("DYLD_") }.map { strdup($0.key + "=" + $0.value) } + [nil]
var worker: pid_t = 0
let spawnStatus = posix_spawn(&worker, executable, &actions, nil, argv, workerEnvironment)
posix_spawn_file_actions_destroy(&actions)
argv.forEach { if let p = $0 { free(p) } }
workerEnvironment.forEach { if let p = $0 { free(p) } }
close(inputPipe[0]); close(outputPipe[1])
guard spawnStatus == 0 else { close(inputPipe[1]); close(outputPipe[0]); exit(71) }
let request = try! JSONSerialization.data(withJSONObject: ["pids": pids, "policy": policy,
    "allowTest": allowTest, "includeStatic": includeStatic, "budgetSeconds": budget, "supervisorPID": getpid()])
let writer = FileHandle(fileDescriptor: inputPipe[1], closeOnDealloc: true)
writer.write(request); try? writer.close()
let currentFlags = fcntl(outputPipe[0], F_GETFL)
_ = fcntl(outputPipe[0], F_SETFL, currentFlags | O_NONBLOCK)
var buffer = Data(), chunk = [UInt8](repeating: 0, count: 65536), childStatus: Int32 = 0
var timedOut = false, outputLimitExceeded = false, reaped = false
while !reaped {
    while true {
        let n = read(outputPipe[0], &chunk, chunk.count)
        if n <= 0 { break }
        buffer.append(contentsOf: chunk.prefix(n))
        if buffer.count > 32 * 1024 * 1024 { outputLimitExceeded = true; break }
    }
    let result = waitpid(worker, &childStatus, WNOHANG)
    if result == worker { reaped = true; break }
    if result == -1 { reaped = true; childStatus = -1; break }
    if CACurrentMediaTime() - began > budget || outputLimitExceeded {
        timedOut = !outputLimitExceeded
        // worker has not been reaped, so its PID cannot be reused here.
        _ = kill(worker, SIGKILL)
        while waitpid(worker, &childStatus, 0) < 0 && errno == EINTR {}
        reaped = true; break
    }
    usleep(10_000)
}
while true {
    let n = read(outputPipe[0], &chunk, chunk.count)
    if n <= 0 { break }
    buffer.append(contentsOf: chunk.prefix(n))
}
close(outputPipe[0])
var rows: [[String: Any]] = []
for line in buffer.split(separator: 10) {
    if let row = try? JSONSerialization.jsonObject(with: Data(line)) as? [String: Any], row["pid"] is NSNumber { rows.append(row) }
}
let completed = Set(rows.compactMap { ($0["pid"] as? NSNumber)?.int32Value })
let missing = pids.filter { !completed.contains($0) }
let gaps = rows.filter { ["inspectionUnavailable", "processExitedOrChanged", "knownMetadataButValidationFailed"].contains($0["category"] as? String ?? "") }
var unresolved = gaps.map { ["pid": $0["pid"]!, "reason": $0["category"]!] }
unresolved += missing.map { ["pid": $0, "reason": timedOut ? "scanDeadlineExceeded" : "workerIncomplete"] as [String: Any] }
let inputUnchanged = (try? Data(contentsOf: policyURL)) == policyBytes
let complete = enumerationOK && missing.isEmpty && gaps.isEmpty && inputUnchanged && !timedOut && !outputLimitExceeded && childStatus == 0
let coverage: [String: Any] = ["pidEnumerationSucceeded": enumerationOK, "listedPIDCount": pids.count,
    "inspectedPIDCount": rows.count, "pathUnavailableCount": rows.filter { $0["executable"] is NSNull }.count,
    "identityUnavailableCount": gaps.count, "notInspectedCount": missing.count,
    "nonExecutingZombieCount": rows.filter { $0["category"] as? String == "nonExecutingZombie" }.count,
    "metadataAvailableCount": rows.filter { ($0["codeIdentity"] as? [String: Any])?["metadataStatus"] as? String == "availableUnvalidated" }.count,
    "dynamicValidationScope": "only catalogue-matched components; other metadata remains unvalidated",
    "staticValidationRequested": includeStatic,
    "scanDeadlineExceeded": timedOut, "outputLimitExceeded": outputLimitExceeded,
    "atomicSystemSnapshot": false, "samePIDExecCoverageGuaranteed": false,
    "discoveryScope": "all enumerated PIDs; no name/path gate; bounded non-atomic observation",
    "temporalCoverage": "pollingOnly; shortLivedProcessesMayBeMissed"]
emit(["schemaVersion": 2, "mode": selectedPID == nil ? "allProcessIdentities" : "specifiedPID",
      "scanStartedAtUTC": started, "observedAtUTC": utc(), "elapsedSeconds": CACurrentMediaTime() - began,
      "budgetSeconds": budget, "enumerationComplete": complete, "processes": rows,
      "unresolved": unresolved, "coverage": coverage, "policyVersion": policy["policyVersion"]!,
      "policySHA256": hash(policyBytes), "policyFileUnchanged": inputUnchanged,
      "testPolicy": policy["testOnly"] as? Bool == true, "policyCryptographicallyAuthenticated": false,
      "signatureEvaluated": true, "remoteSessionVerified": false, "runningMemoryAttested": false,
      "systemMutationPerformed": false, "targetProcessMutationPerformed": false,
      "ownedWorkerTerminatedForBudget": timedOut || outputLimitExceeded,
      "workerWaitStatus": childStatus])
exit(complete ? 0 : 2)
