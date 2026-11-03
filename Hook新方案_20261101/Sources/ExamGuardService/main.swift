// Bounded local-development worker, NOT a distributed SMAppService daemon.
// No caller-supplied PID, executable, job label, or shell command is executed.
// The sole writable IPC operation is END. Root-owned status is observational.
import Foundation
import Security
import CryptoKit
import Darwin

enum GuardFailure: Error { case invalid(String) }
func fail(_ message: String) throws -> Never { throw GuardFailure.invalid(message) }
func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
func continuous() -> Double {
    var tb = mach_timebase_info_data_t(); mach_timebase_info(&tb)
    return Double(mach_continuous_time()) * Double(tb.numer) / Double(tb.denom) / 1e9
}
func birth(_ pid: Int32) -> [UInt64]? {
    var info = proc_bsdinfo()
    let n = proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, Int32(MemoryLayout.size(ofValue: info)))
    guard n == MemoryLayout.size(ofValue: info) else { return nil }
    return [UInt64(info.pbi_uid), UInt64(info.pbi_start_tvsec), UInt64(info.pbi_start_tvusec)]
}
func executable(_ pid: Int32) -> String? {
    var bytes = [CChar](repeating: 0, count: 4 * Int(MAXPATHLEN))
    guard proc_pidpath(pid, &bytes, UInt32(bytes.count)) > 0 else { return nil }
    return String(cString: bytes)
}
func exitedAwaitingReap(_ pid: Int32, expected: [UInt64]) -> Bool {
    var first = proc_bsdinfo(), second = proc_bsdinfo()
    let size = Int32(MemoryLayout<proc_bsdinfo>.size)
    guard proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &first, size) == size,
          proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &second, size) == size else { return false }
    let a = [UInt64(first.pbi_uid), UInt64(first.pbi_start_tvsec), UInt64(first.pbi_start_tvusec)]
    let b = [UInt64(second.pbi_uid), UInt64(second.pbi_start_tvsec), UInt64(second.pbi_start_tvusec)]
    return a == expected && b == expected && first.pbi_status == UInt32(SZOMB) && second.pbi_status == UInt32(SZOMB)
}
func pids() -> [Int32] {
    var capacity = max(Int(proc_listallpids(nil, 0)) + 128, 1024)
    for _ in 0..<5 {
        var values = [Int32](repeating: 0, count: capacity)
        let count = proc_listallpids(&values, Int32(capacity * MemoryLayout<Int32>.size))
        if count > 0 && count < capacity { return Array(Set(values.prefix(Int(count)).filter { $0 > 0 })).sorted() }
        capacity *= 2
    }
    return []
}
let teams = ["uu": "PU9BNSBJW7", "todesk": "KM56KD59W4", "sunlogin": "ZBNMDRTU32"]
let identifiers: [String: Set<String>] = [
    "uu": ["com.netease.uuremote", "com.netease.uuremote.agent", "com.netease.uuremote.server", "com.netease.uuremote.daemon", "com.netease.uuremote.helper"],
    "todesk": ["com.youqu.todesk.mac", "ToDesk_Service", "ToDesk_Session_Proxy", "com.youqu.todesk.mac.tdsvc", "com.youqu.todesk.helper", "com.youqu.todesk.RenderHelper"],
    "sunlogin": ["com.oray.sunlogin.macclient", "AweSun", "com.oray.sunlogin.macclient.agent", "$(PRODUCT_BUNDLE_IDENTIFIER)"]
]
let apps = ["uu": "/Applications/UURemote.app", "todesk": "/Applications/ToDesk.app", "sunlogin": "/Applications/AweSun.app"]
let guiIDs = ["com.netease.uuremote", "com.youqu.todesk.mac", "com.oray.sunlogin.macclient"]

func requirement(_ vendor: String, _ identifier: String) -> SecRequirement? {
    // Both values must come from the compiled catalogue, never interpolated caller text.
    guard let team = teams[vendor], identifiers[vendor]?.contains(identifier) == true else { return nil }
    var text = "anchor apple generic and certificate leaf[subject.OU] = \"\(team)\" and identifier \"\(identifier)\""
    if identifier == "$(PRODUCT_BUNDLE_IDENTIFIER)" { text += " and cdhash H\"e3a12b43dfba8ef18382d5ae85d3e53a9b0937c2\"" }
    var req: SecRequirement?
    return SecRequirementCreateWithString(text as CFString, [], &req) == errSecSuccess ? req : nil
}
struct Target {
    let pid: Int32
    let life: [UInt64]
    let path: String
    let vendor: String
    let signingID: String
    let cdhash: String
    var json: [String: Any] { ["pid": pid, "uid": life[0], "birth": life, "executable": path, "vendor": vendor, "signingID": signingID, "cdhash": cdhash] }
}
func target(_ pid: Int32, vendors: Set<String>, uid: UInt32) -> Target? {
    guard let before = birth(pid), before[0] == UInt64(uid) || before[0] == 0, let path = executable(pid) else { return nil }
    var code: SecCode?
    guard SecCodeCopyGuestWithAttributes(nil, [kSecGuestAttributePid: pid] as CFDictionary, [], &code) == errSecSuccess,
          let code else { return nil }
    var info: CFDictionary?, staticCode: SecStaticCode?
    guard SecCodeCopyStaticCode(code, [], &staticCode) == errSecSuccess, let staticCode,
          SecCodeCopySigningInformation(staticCode, SecCSFlags(rawValue: kSecCSSigningInformation), &info) == errSecSuccess,
          let data = info as? [String: Any], let team = data[kSecCodeInfoTeamIdentifier as String] as? String,
          let signingID = data[kSecCodeInfoIdentifier as String] as? String,
          let vendor = vendors.first(where: { teams[$0] == team && identifiers[$0]?.contains(signingID) == true }),
          let req = requirement(vendor, signingID), SecCodeCheckValidity(code, [], req) == errSecSuccess,
          before == birth(pid), executable(pid) == path else { return nil }
    let hash = (data[kSecCodeInfoUnique as String] as? Data)?.map { String(format: "%02x", $0) }.joined() ?? ""
    guard !hash.isEmpty else { return nil }
    if signingID == "$(PRODUCT_BUNDLE_IDENTIFIER)" && hash != "e3a12b43dfba8ef18382d5ae85d3e53a9b0937c2" { return nil }
    return Target(pid: pid, life: before, path: path, vendor: vendor, signingID: signingID, cdhash: hash)
}
func same(_ a: Target, _ b: Target?) -> Bool {
    guard let b else { return false }
    return a.pid == b.pid && a.life == b.life && a.path == b.path && a.vendor == b.vendor && a.signingID == b.signingID && a.cdhash == b.cdhash
}
func staticallyValid(_ path: String, vendor: String, id: String, resources: Bool = true) -> Bool {
    var code: SecStaticCode?
    guard let req = requirement(vendor, id), SecStaticCodeCreateWithPath(URL(fileURLWithPath: path) as CFURL, [], &code) == errSecSuccess,
          let code else { return false }
    let flags = resources ? SecCSFlags() : SecCSFlags(rawValue: kSecCSDoNotValidateResources)
    guard SecStaticCodeCheckValidity(code, flags, req) == errSecSuccess else { return false }
    if id == "$(PRODUCT_BUNDLE_IDENTIFIER)" {
        var info: CFDictionary?
        guard SecCodeCopySigningInformation(code, SecCSFlags(rawValue: kSecCSSigningInformation), &info) == errSecSuccess,
              let d = info as? [String: Any], let hash = d[kSecCodeInfoUnique as String] as? Data else { return false }
        return hash.map { String(format: "%02x", $0) }.joined() == "e3a12b43dfba8ef18382d5ae85d3e53a9b0937c2"
    }
    return true
}
struct Job {
    let vendor: String, plist: String, label: String, program: String, signingID: String, system: Bool
}
let jobs: [Job] = [
    Job(vendor: "uu", plist: "/Library/LaunchAgents/com.netease.uuremote.agent.plist", label: "com.netease.uuremote.agent", program: "/Applications/UURemote.app/Contents/MacOS/UURemoteService", signingID: "com.netease.uuremote.agent", system: false),
    Job(vendor: "uu", plist: "/Library/LaunchDaemons/com.netease.uuremote.daemon.plist", label: "com.netease.uuremote.daemon", program: "/Applications/UURemote.app/Contents/MacOS/UURemoteDaemon", signingID: "com.netease.uuremote.daemon", system: true),
    Job(vendor: "todesk", plist: "/Library/LaunchAgents/com.youqu.todesk.session.plist", label: "com.youqu.todesk.desktop", program: "/Applications/ToDesk.app/Contents/MacOS/ToDesk_Session_Proxy", signingID: "ToDesk_Session_Proxy", system: false),
    Job(vendor: "todesk", plist: "/Library/LaunchDaemons/com.youqu.todesk.service.plist", label: "com.youqu.todesk.service", program: "/Applications/ToDesk.app/Contents/MacOS/ToDesk_Service", signingID: "ToDesk_Service", system: true),
    Job(vendor: "sunlogin", plist: "/Library/LaunchAgents/com.oray.awesun.agent.plist", label: "com.oray.awesun.desktopagent", program: "/Applications/AweSun.app/Contents/Helpers/AweSun_Desktop.app/Contents/MacOS/AweSun_Desktop", signingID: "com.oray.sunlogin.macclient.agent", system: false),
    Job(vendor: "sunlogin", plist: "/Library/LaunchDaemons/com.oray.awesun.plist", label: "com.oray.awesun.service", program: "/Applications/AweSun.app/Contents/Helpers/AweSun", signingID: "AweSun", system: true),
    Job(vendor: "sunlogin", plist: "/Library/LaunchDaemons/com.oray.awesun.helper.plist", label: "com.oray.awesun.helper", program: "/Applications/AweSun.app/Contents/Helpers/AweSun_Helper", signingID: "$(PRODUCT_BUNDLE_IDENTIFIER)", system: true)
    // Generic helper identity additionally pins the observed arm64 CDHash above.
]
struct CommandResult { let code: Int32; let output: String; let timedOut: Bool }
func command(_ executable: String, _ arguments: [String], timeout: Double = 8) -> CommandResult {
    var fds: [Int32] = [0, 0]
    guard pipe(&fds) == 0 else { return CommandResult(code: -1, output: "pipeFailed", timedOut: false) }
    defer { close(fds[0]) }
    var actions: posix_spawn_file_actions_t?; posix_spawn_file_actions_init(&actions)
    defer { posix_spawn_file_actions_destroy(&actions) }
    posix_spawn_file_actions_addopen(&actions, STDIN_FILENO, "/dev/null", O_RDONLY, 0)
    posix_spawn_file_actions_adddup2(&actions, fds[1], STDOUT_FILENO)
    posix_spawn_file_actions_adddup2(&actions, fds[1], STDERR_FILENO)
    posix_spawn_file_actions_addclose(&actions, fds[0])
    posix_spawn_file_actions_addclose(&actions, fds[1])
    var attributes: posix_spawnattr_t?; posix_spawnattr_init(&attributes)
    defer { posix_spawnattr_destroy(&attributes) }
    posix_spawnattr_setflags(&attributes, Int16(POSIX_SPAWN_SETPGROUP))
    posix_spawnattr_setpgroup(&attributes, getpgrp()) // Explicitly stay in the supervised worker group.
    var argv = ([executable] + arguments).map { strdup($0) } + [nil]
    var environment = [strdup("PATH=/usr/bin:/bin:/usr/sbin:/sbin"), strdup("LANG=C"), nil]
    defer { argv.forEach { free($0) }; environment.forEach { free($0) } }
    var child: pid_t = 0
    let spawned = posix_spawn(&child, executable, &actions, &attributes, &argv, &environment)
    close(fds[1])
    guard spawned == 0 else { return CommandResult(code: -1, output: "spawnFailed:\(spawned)", timedOut: false) }
    _ = fcntl(fds[0], F_SETFL, O_NONBLOCK)
    var bytes = Data(), buffer = [UInt8](repeating: 0, count: 65536), status: Int32 = 0
    var done = false, tooLarge = false
    func drain() {
        for _ in 0..<64 {
            let n = read(fds[0], &buffer, buffer.count)
            if n <= 0 { break }
            if bytes.count + n <= 4 * 1024 * 1024 { bytes.append(contentsOf: buffer.prefix(n)) } else { tooLarge = true }
        }
    }
    let end = continuous() + timeout
    while continuous() < end {
        drain()
        let result = waitpid(child, &status, WNOHANG)
        if result == child { done = true; break }
        if result < 0 && errno != EINTR { return CommandResult(code: -1, output: "lostCommandChild", timedOut: true) }
        Thread.sleep(forTimeInterval: 0.01)
    }
    if !done {
        _ = kill(child, SIGKILL) // Still-owned, unreaped child only.
        while waitpid(child, &status, 0) < 0 && errno == EINTR {}
    }
    drain() // Never wait on pipe EOF from a descendant.
    let code = status & 0x7f == 0 ? (status >> 8) & 0xff : 128 + (status & 0x7f)
    return CommandResult(code: code, output: String(decoding: bytes, as: UTF8.self), timedOut: !done || tooLarge)
}
func atomicJSON(_ data: [String: Any], _ path: String) throws {
    let bytes = try JSONSerialization.data(withJSONObject: data, options: [.sortedKeys, .prettyPrinted])
    let temporary = path + "." + UUID().uuidString
    let fd = open(temporary, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o644)
    guard fd >= 0 else { try fail("createState:\(errno)") }
    defer { close(fd); unlink(temporary) }
    let count = bytes.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
    guard count == bytes.count, fsync(fd) == 0, rename(temporary, path) == 0 else { try fail("persistState:\(errno)") }
    let dir = open(URL(fileURLWithPath: path).deletingLastPathComponent().path, O_RDONLY)
    if dir >= 0 { _ = fsync(dir); close(dir) }
}

final class Worker {
    let session: String, directory: String, uid: UInt32, owner: Int32, ownerLife: [UInt64], vendors: Set<String>, deadline: Double
    var sequence = 0, state = "preparing", events: [[String: Any]] = [], changed: [[String: Any]] = [], guiBefore: Set<String> = []
    var lastTargets: [[String: Any]] = [], failures: [String] = [], restoreAttempted = false
    var guiEvidence: [[String: String]] = []
    var inventoryEvidence: [String: Any] = [:]
    var attempts: [Int32: (Target, Double, Int)] = [:]
    var mutationCount = 0
    init(session: String, uid: UInt32, owner: Int32, vendors: Set<String>, lease: Double) throws {
        guard geteuid() == 0, uid > 0, vendors.isSubset(of: Set(teams.keys)), !vendors.isEmpty, lease >= 10 && lease <= 600,
              let parsed = UUID(uuidString: session), let life = birth(owner), life[0] == UInt64(uid) else { try fail("invalidRootWorkerConfiguration") }
        self.session = parsed.uuidString; self.uid = uid; self.owner = owner; self.ownerLife = life; self.vendors = vendors
        self.directory = "/private/var/tmp/exam-remote-guard-" + parsed.uuidString
        self.deadline = continuous() + lease
        guard mkdir(directory, 0o755) == 0 else { try fail("sessionDirectoryMustBeNew:\(errno)") }
        let fd = open(directory + "/end.request", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { try fail("createEndRequest") }
        guard fchown(fd, uid, UInt32.max) == 0 else { close(fd); try fail("ownEndRequest") }
        close(fd)
        let binary = try Data(contentsOf: URL(fileURLWithPath: EmbeddedInventory.source))
        guard digest(binary) == EmbeddedInventory.sha256, let policy = Data(base64Encoded: EmbeddedInventory.policyBase64) else { try fail("embeddedInventoryMismatch") }
        for (name, bytes, mode) in [("Inventory", binary, mode_t(0o755)), ("policy.json", policy, mode_t(0o644))] {
            let handle = open(directory + "/" + name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, mode)
            guard handle >= 0 else { try fail("createProtectedAsset") }
            let count = bytes.withUnsafeBytes { write(handle, $0.baseAddress, $0.count) }
            let synced = fsync(handle); close(handle)
            guard count == bytes.count, synced == 0 else { try fail("writeProtectedAsset") }
        }
        try persist()
    }
    func event(_ name: String, _ details: [String: Any] = [:]) throws {
        events.append(["event": name, "atUTC": ISO8601DateFormatter().string(from: Date()), "continuousTime": continuous(), "details": details])
        guard events.count <= 2000 else { try fail("eventBudgetExceeded") }
        try persist()
    }
    func persist() throws {
        sequence += 1
        try atomicJSON(["schemaVersion": 1, "sessionID": session, "sequence": sequence, "state": state,
                        "mode": "reactiveTerminate", "backend": "development-root-worker", "productionReady": false,
                        "workerPID": getpid(), "workerBirth": birth(getpid()) ?? [], "ownerPID": owner, "ownerBirth": ownerLife, "uid": uid,
                        "updatedContinuousTime": continuous(), "expiresContinuousTime": deadline,
                        "vendors": vendors.sorted(), "targets": lastTargets, "events": events,
                        "changedJobs": changed, "guiBefore": guiBefore.sorted(), "guiEvidence": guiEvidence, "failures": failures,
                        "inventoryEvidence": inventoryEvidence,
                        "identityStrength": "pidBirthPathAndDynamicSignature_notAtomicExecIdentity",
                        "remoteSessionVerified": false, "serverReported": false], directory + "/status.json")
    }
    func ending() -> Bool {
        if continuous() >= deadline || birth(owner) != ownerLife { return true }
        let fd = open(directory + "/end.request", O_RDONLY | O_NOFOLLOW | O_NONBLOCK)
        guard fd >= 0 else { return true }; defer { close(fd) }
        var bytes = [UInt8](repeating: 0, count: 32); let n = read(fd, &bytes, bytes.count)
        return n > 0 && String(decoding: bytes.prefix(n), as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines) == "end"
    }
    func validatedJob(_ job: Job) throws -> (String, String) {
        var info = stat()
        guard lstat(job.plist, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
              info.st_uid == 0, info.st_mode & 0o022 == 0 else { try fail("jobDefinitionNotRootProtected:\(job.label)") }
        let bytes = try Data(contentsOf: URL(fileURLWithPath: job.plist))
        guard let d = try PropertyListSerialization.propertyList(from: bytes, format: nil) as? [String: Any],
              d["Label"] as? String == job.label,
              (d["Program"] as? String ?? (d["ProgramArguments"] as? [String])?.first) == job.program,
              staticallyValid(job.program, vendor: job.vendor, id: job.signingID) else { try fail("jobDefinitionUnverified:\(job.label)") }
        return (job.system ? "system" : "gui/\(uid)", digest(bytes))
    }
    func prepare() throws {
        try readInventory() // Validate pinned deployed tool/policy BEFORE any target change.
        let initialPIDs = pids()
        guard !initialPIDs.isEmpty else { try fail("baselineEnumerationFailed") }
        let initial = initialPIDs.compactMap { target($0, vendors: vendors, uid: uid) }
        for t in initial where guiIDs.contains(t.signingID) {
            guard let app = apps[t.vendor], t.path.hasPrefix(app + "/"), t.life[0] == UInt64(uid) else { try fail("unsupportedGUIRestoreLocationOrUser") }
            guard let bytes = try? Data(contentsOf: URL(fileURLWithPath: t.path)) else { try fail("guiBaselineUnreadable") }
            guiBefore.insert(t.vendor)
            guiEvidence.append(["vendor": t.vendor, "path": t.path, "sha256": digest(bytes), "signingID": t.signingID])
        }
        lastTargets = initial.map(\.json)
        try event("baselineSaved")
        for job in jobs where vendors.contains(job.vendor) {
            if ending() { return }
            if !FileManager.default.fileExists(atPath: job.plist) { continue }
            let (domain, hash) = try validatedJob(job)
            let current = command("/bin/launchctl", ["print", domain + "/" + job.label])
            if current.code != 0 {
                if !current.timedOut && current.output.contains("Could not find service") { continue }
                try fail("jobStateUnknown:\(job.label)")
            }
            guard current.output.contains("path = " + job.plist), current.output.contains("program = " + job.program) else { try fail("loadedJobMismatch:\(job.label)") }
            changed.append(["vendor": job.vendor, "label": job.label, "domain": domain, "plist": job.plist, "plistSHA256": hash,
                            "program": job.program, "signingID": job.signingID, "wasLoaded": true, "operation": "planned"])
            try event("jobStopPlanned", ["label": job.label]) // Durable intent BEFORE mutation.
            if ending() { return }
            changed[changed.count - 1]["operation"] = "bootoutPending"
            try persist()
            let result = command("/bin/launchctl", ["bootout", domain + "/" + job.label])
            mutationCount += 1
            changed[changed.count - 1]["operation"] = "bootoutReturned"
            changed[changed.count - 1]["returnCode"] = result.code
            changed[changed.count - 1]["timedOut"] = result.timedOut
            try event("jobStopResult", ["label": job.label, "code": result.code, "timedOut": result.timedOut])
            let after = command("/bin/launchctl", ["print", domain + "/" + job.label])
            guard !result.timedOut, after.code != 0, after.output.contains("Could not find service") else { try fail("jobStopUnconfirmed:\(job.label)") }
            changed[changed.count - 1]["operation"] = "bootoutConfirmed"
            try persist()
        }
        state = "monitoring"; try persist()
    }
    func scanAndEnforce() throws {
        try readInventory()
        let ids = pids(); guard !ids.isEmpty else { try fail("pidEnumerationFailed") }
        let targets = ids.compactMap { target($0, vendors: vendors, uid: uid) }
        lastTargets = targets.map(\.json)
        for t in targets {
            if ending() { return }
            guard same(t, target(t.pid, vendors: vendors, uid: uid)) else { try event("identityChanged", t.json); continue }
            let previous = attempts[t.pid]
            let existing = previous != nil && same(t, previous!.0)
            if existing && continuous() - previous!.1 < 1 { continue }
            let count = existing ? previous!.2 : 0
            if count >= 2 { try fail("terminationUnconfirmed:\(t.pid)") }
            if mutationCount >= 100 { try fail("mutationBudgetExceeded") }
            let sig = count == 0 ? SIGTERM : SIGKILL
            try event("terminationPlanned", t.json.merging(["signal": sig]) { _, v in v })
            if ending() { return }
            // Recheck immediately before signalling; PID signalling is still not atomic.
            guard same(t, target(t.pid, vendors: vendors, uid: uid)) else { continue }
            let result = kill(t.pid, sig), savedErrno = errno
            mutationCount += 1; attempts[t.pid] = (t, continuous(), count + 1)
            try event("signalSubmitted", t.json.merging(["signal": sig, "returnCode": result, "errno": result == 0 ? 0 : savedErrno]) { _, v in v })
            if result != 0 && savedErrno != ESRCH { try fail("signalFailed:\(savedErrno)") }
        }
        let remainingPIDs = Set(pids())
        guard !remainingPIDs.isEmpty else { try fail("exitVerificationEnumerationFailed") }
        for (pid, item) in Array(attempts) where !targets.contains(where: { same(item.0, $0) }) {
            // Absence from vendor matching alone is not proof of exit: inspect birth identity.
            let currentBirth = birth(pid)
            if !remainingPIDs.contains(pid) || (currentBirth != nil && currentBirth != item.0.life) || exitedAwaitingReap(pid, expected: item.0.life) {
                try event("terminationVerified", item.0.json)
                attempts.removeValue(forKey: pid)
            } else {
                try fail("targetBecameUnverifiable:\(pid)")
            }
        }
        try persist()
    }
    func readInventory() throws {
        let result = command(directory + "/Inventory", ["--policy", directory + "/policy.json", "--budget", "12", "--skip-static"], timeout: 16)
        guard !result.timedOut, result.code == 0 || result.code == 2,
              let d = try JSONSerialization.jsonObject(with: Data(result.output.utf8)) as? [String: Any],
              d["schemaVersion"] as? Int == 2, d["testPolicy"] as? Bool == false,
              d["policyFileUnchanged"] as? Bool == true else { try fail("privilegedInventoryUnavailable") }
        inventoryEvidence = d
        try persist()
    }
    func restore() {
        guard !restoreAttempted else { return }; restoreAttempted = true
        state = "restoring"; try? persist()
        var restorationFailures: [String] = []
        for entry in changed.reversed() {
            guard let label = entry["label"] as? String, let job = jobs.first(where: { $0.label == label }),
                  let domain = entry["domain"] as? String else { restorationFailures.append("journalInvalid"); continue }
            if entry["operation"] as? String == "planned" { continue }
            guard entry["operation"] as? String == "bootoutConfirmed" else {
                restorationFailures.append("lateBootoutCannotBeExcluded:\(label)")
                continue // Killing a launchctl client does not cancel a request already sent to launchd.
            }
            do {
                let (expectedDomain, hash) = try validatedJob(job)
                guard domain == expectedDomain, hash == entry["plistSHA256"] as? String else { try fail("restoreDefinitionChanged:\(label)") }
                let before = command("/bin/launchctl", ["print", domain + "/" + label])
                if before.code == 0 {
                    guard before.output.contains("path = " + job.plist), before.output.contains("program = " + job.program) else { try fail("restoreLoadedConflict:\(label)") }
                } else {
                    guard !before.timedOut, before.output.contains("Could not find service") else { try fail("restoreStateUnknown:\(label)") }
                    let result = command("/bin/launchctl", ["bootstrap", domain, job.plist])
                    guard !result.timedOut, result.code == 0 else { try fail("restoreBootstrapFailed:\(label)") }
                }
                let after = command("/bin/launchctl", ["print", domain + "/" + label])
                guard after.code == 0, after.output.contains("path = " + job.plist), after.output.contains("program = " + job.program) else { try fail("restoreVerificationFailed:\(label)") }
                try event("jobRestoreVerified", ["label": label])
            } catch { restorationFailures.append(String(describing: error)) }
        }
        for vendor in guiBefore.sorted() {
            guard let app = apps[vendor], let id = guiIDs.first(where: { identifiers[vendor]?.contains($0) == true }) else { continue }
            guard let saved = guiEvidence.first(where: { $0["vendor"] == vendor }), let path = saved["path"],
                  let bytes = try? Data(contentsOf: URL(fileURLWithPath: path)), digest(bytes) == saved["sha256"],
                  staticallyValid(path, vendor: vendor, id: id, resources: false) else { restorationFailures.append("guiRestoreIdentityFailed:\(vendor)"); continue }
            // asuser only switches bootstrap/audit context, so explicitly drop credentials as well.
            let result = command("/bin/launchctl", ["asuser", String(uid), "/usr/bin/sudo", "-n", "-H", "-u", "#\(uid)", "/usr/bin/open", "-a", app])
            if result.code != 0 || result.timedOut { restorationFailures.append("guiRestoreLaunchFailed:\(vendor)"); continue }
            let end = continuous() + 5
            var verified = false
            repeat {
                verified = pids().compactMap { target($0, vendors: [vendor], uid: uid) }.contains { $0.signingID == id && $0.life[0] == UInt64(uid) && $0.path == path }
                if !verified { Thread.sleep(forTimeInterval: 0.2) }
            } while !verified && continuous() < end
            if !verified { restorationFailures.append("guiRestoreProcessUnconfirmed:\(vendor)") }
        }
        failures += restorationFailures
        state = restorationFailures.isEmpty ? "finished" : "recoveryPending"
        try? event("restorationResult", ["launchJobsRestored": restorationFailures.isEmpty, "remoteConnectionVerified": false])
    }
    func run() {
        defer { restore() }
        do {
            try prepare()
            while !ending() { try scanAndEnforce(); Thread.sleep(forTimeInterval: 0.5) }
            try event("leaseEndedOrOwnerExited")
        } catch { failures.append(String(describing: error)); try? event("guardFailure", ["reason": String(describing: error)]) }
    }
    init(recover session: String) throws {
        guard geteuid() == 0, let parsed = UUID(uuidString: session) else { try fail("invalidRecovery") }
        self.session = parsed.uuidString
        self.directory = "/private/var/tmp/exam-remote-guard-" + parsed.uuidString
        var st = stat()
        guard lstat(directory, &st) == 0, st.st_uid == 0, st.st_mode & 0o022 == 0, st.st_mode & S_IFMT == S_IFDIR else { try fail("untrustedRecoveryDirectory") }
        let file = directory + "/status.json"
        guard lstat(file, &st) == 0, st.st_uid == 0, st.st_mode & 0o022 == 0, st.st_mode & S_IFMT == S_IFREG,
              let d = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: file))) as? [String: Any],
              d["sessionID"] as? String == self.session, let uid = d["uid"] as? UInt32,
              let owner = d["ownerPID"] as? Int32, let life = d["ownerBirth"] as? [UInt64],
              let selected = d["vendors"] as? [String], Set(selected).isSubset(of: Set(teams.keys)),
              let savedJobs = d["changedJobs"] as? [[String: Any]], savedJobs.count <= jobs.count else { try fail("invalidRecoveryJournal") }
        if let activePID = d["workerPID"] as? Int32, let activeBirth = d["workerBirth"] as? [UInt64],
           birth(activePID) == activeBirth, d["state"] as? String != "finished" { try fail("liveWorkerRecoveryRejected") }
        self.uid = uid; self.owner = owner; self.ownerLife = life; self.vendors = Set(selected); self.deadline = continuous()
        self.changed = savedJobs; self.guiBefore = Set(d["guiBefore"] as? [String] ?? [])
        self.guiEvidence = d["guiEvidence"] as? [[String: String]] ?? []
        self.events = d["events"] as? [[String: Any]] ?? []; self.sequence = d["sequence"] as? Int ?? 0
        self.failures = d["failures"] as? [String] ?? []
        if d["state"] as? String == "finished" { restoreAttempted = true }
    }
}

// An independent root parent owns/reaps its child and enforces an absolute bound.
// All launched command children share the worker's private process group; before
// recovery after a hang/crash the supervisor stops that group to avoid late bootout.
func supervise(_ args: [String], session: String, lease: Double) throws {
    let binary = URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL.path
    var argv = ([binary, "--worker"] + args).map { strdup($0) } + [nil]
    defer { argv.forEach { free($0) } }
    var attributes: posix_spawnattr_t?; posix_spawnattr_init(&attributes)
    defer { posix_spawnattr_destroy(&attributes) }
    posix_spawnattr_setflags(&attributes, Int16(POSIX_SPAWN_SETPGROUP))
    posix_spawnattr_setpgroup(&attributes, 0)
    var child: pid_t = 0
    var environment = [strdup("PATH=/usr/bin:/bin:/usr/sbin:/sbin"), strdup("LANG=C"), nil]
    defer { environment.forEach { free($0) } }
    let spawned = posix_spawn(&child, binary, nil, &attributes, &argv, &environment)
    guard spawned == 0 else { try fail("workerSpawn:\(spawned)") }
    let end = continuous() + lease + 30
    var status: Int32 = 0
    while continuous() < end {
        var information = siginfo_t()
        let result = waitid(P_PID, id_t(child), &information, WEXITED | WNOHANG | WNOWAIT)
        if result == 0 && information.si_pid == child { break }
        if result < 0 && errno != EINTR { try fail("supervisorLostChild") }
        Thread.sleep(forTimeInterval: 0.2)
    }
    // WNOWAIT keeps our child PID reserved, including after exit. Stop any
    // outstanding command in its group BEFORE reaping and before restoration.
    // On macOS getpgid() may fail for a zombie. Its PID is still reserved by
    // WNOWAIT and we created that private group, so use the recorded group ID.
    _ = kill(-child, SIGKILL)
    _ = kill(child, SIGKILL)
    while waitpid(child, &status, 0) < 0 && errno == EINTR {}
    let path = "/private/var/tmp/exam-remote-guard-" + session.uppercased() + "/status.json"
    if FileManager.default.fileExists(atPath: path) {
        let recovery = try Worker(recover: session); recovery.restore()
    }
}

do {
    var args = Array(CommandLine.arguments.dropFirst())
    let rootInspect = args.first == "--root-inspect"
    if rootInspect { args.removeFirst() }
    let internalWorker = args.first == "--worker"
    if internalWorker { args.removeFirst() }
    if args.count == 2 && args[0] == "--recover" {
        let recovery = try Worker(recover: args[1]); recovery.restore(); exit(0)
    }
    if args.count == 2 && args[0] == "--owner-identity", let pid = Int32(args[1]), let life = birth(pid) {
        let data = try JSONSerialization.data(withJSONObject: ["pid": pid, "birth": life])
        FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data("\n".utf8)); exit(0)
    }
    if args == ["--inspect"] {
        let found = pids().compactMap { target($0, vendors: Set(teams.keys), uid: getuid()) }.map(\.json)
        let data = try JSONSerialization.data(withJSONObject: ["mode": "inspectOnly", "targets": found, "productionReady": false], options: [.sortedKeys])
        FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data("\n".utf8))
    } else {
        guard args.count == 12, args[0] == "--session", args[2] == "--uid", args[4] == "--owner", args[6] == "--owner-birth", args[8] == "--vendors", args[10] == "--lease",
              let uid = UInt32(args[3]), let owner = Int32(args[5]), let lease = Double(args[11]), lease.isFinite,
              let life = birth(owner), args[7] == "\(life[1]):\(life[2])" else { try fail("usage: --inspect OR --session UUID --uid UID --owner PID --owner-birth SEC:USEC --vendors uu,todesk,sunlogin --lease 10..600") }
        guard geteuid() == 0, UUID(uuidString: args[1]) != nil, lease >= 10 && lease <= 600 else { try fail("rootAndFiniteLeaseRequired") }
        if rootInspect {
            let worker = try Worker(session: args[1], uid: uid, owner: owner, vendors: Set(args[9].split(separator: ",").map(String.init)), lease: lease)
            try worker.readInventory(); worker.state = "finished"; try worker.persist()
        } else if internalWorker {
            let worker = try Worker(session: args[1], uid: uid, owner: owner, vendors: Set(args[9].split(separator: ",").map(String.init)), lease: lease)
            worker.run()
        } else { try supervise(args, session: args[1], lease: lease) }
    }
} catch { FileHandle.standardError.write(Data("\(error)\n".utf8)); exit(1) }
