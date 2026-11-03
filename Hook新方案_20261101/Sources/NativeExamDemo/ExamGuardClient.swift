import Foundation
import CoreFoundation
import Darwin

enum ExamGuardClock {
    private static let timebase: mach_timebase_info_data_t = {
        var info = mach_timebase_info_data_t()
        mach_timebase_info(&info)
        return info
    }()
    static func now() -> TimeInterval {
        guard timebase.denom != 0 else { return .infinity }
        return Double(mach_continuous_time()) * Double(timebase.numer) / Double(timebase.denom) / 1_000_000_000
    }
}

/// Local UI transport only. A pipe is not remote attestation, and this ordinary
/// user process does not confer root privileges on the GUI or its requests.
struct ExamGuardStatus {
    let sessionID: String
    let sequence: Int64
    let state: String
    let canStart: Bool
    let examAllowed: Bool
    let health: String
    let message: String
    let detail: [String: Any]

    static func parse(_ data: Data, sessionID: String) throws -> ExamGuardStatus {
        guard data.count <= 65_536,
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              integer(object["protocolVersion"]) == 1,
              object["type"] as? String == "status",
              object["sessionID"] as? String == sessionID,
              let seq = integer(object["sequence"]), seq > 0,
              let state = object["state"] as? String,
              ["preparing", "ready", "exam", "paused", "restoring", "recoveryPending", "finished"].contains(state),
              let canStart = boolean(object["canStart"]),
              let examAllowed = boolean(object["examAllowed"]),
              let health = object["health"] as? String,
              let message = object["message"] as? String, message.utf8.count <= 8_192 else {
            throw ExamGuardError.invalidStatus
        }
        guard !(examAllowed && (state != "exam" || health != "healthy")),
              !(canStart && (state != "ready" || health != "healthy")) else {
            throw ExamGuardError.invalidStatus
        }
        return ExamGuardStatus(sessionID: sessionID, sequence: seq, state: state,
                               canStart: canStart, examAllowed: examAllowed, health: health,
                               message: message, detail: object)
    }

    private static func boolean(_ value: Any?) -> Bool? {
        guard let n = value as? NSNumber, CFGetTypeID(n) == CFBooleanGetTypeID() else { return nil }
        return n.boolValue
    }
    private static func integer(_ value: Any?) -> Int64? {
        guard let n = value as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID(),
              n.doubleValue.isFinite, n.doubleValue.rounded() == n.doubleValue,
              n.doubleValue >= 0, n.doubleValue < Double(Int64.max) else { return nil }
        return n.int64Value
    }
}

enum ExamGuardError: Error { case invalidStatus, replayedStatus, oversizedFrame, unavailable, invalidCommand }

struct ExamGuardGate {
    let sessionID: String
    let heartbeatTimeout: TimeInterval
    private(set) var status: ExamGuardStatus?
    private(set) var lastReceived: TimeInterval?
    private(set) var lastSequence: Int64 = 0
    private(set) var localStartRequested = false
    private(set) var ending = false
    private(set) var faultReason: String?

    init(sessionID: String, heartbeatTimeout: TimeInterval = 3) {
        self.sessionID = sessionID
        self.heartbeatTimeout = heartbeatTimeout
    }
    mutating func accept(_ data: Data, now: TimeInterval) throws {
        let parsed: ExamGuardStatus
        do { parsed = try ExamGuardStatus.parse(data, sessionID: sessionID) }
        catch { fail("invalidStatus"); throw error }
        guard parsed.sequence > lastSequence else {
            fail("replayedStatus")
            throw ExamGuardError.replayedStatus
        }
        // A fresh message after a gap cannot silently resume an earlier exam,
        // even if it runs before the watchdog callback after wake/main-loop lag.
        if let previous = lastReceived, now - previous >= heartbeatTimeout || now < previous {
            localStartRequested = false
        }
        let newlyPaused = parsed.state == "paused" && status?.state == "exam"
        status = parsed
        lastSequence = parsed.sequence
        lastReceived = now
        faultReason = nil
        if parsed.health != "healthy" || newlyPaused
            || ["preparing", "restoring", "recoveryPending", "finished"].contains(parsed.state) {
            localStartRequested = false
        }
        // A user-requested resume may be followed by another healthy paused
        // heartbeat before its command is processed. Do not lose that intent;
        // a new fault/transition out of exam still cancels it above.
    }
    mutating func fail(_ reason: String) {
        faultReason = reason
        localStartRequested = false
    }
    mutating func requestStart() { if !ending { localStartRequested = true } }
    mutating func requestEnd() { ending = true; localStartRequested = false }
    func fresh(at now: TimeInterval) -> Bool {
        guard faultReason == nil, let lastReceived else { return false }
        let elapsed = now - lastReceived
        return elapsed >= 0 && elapsed < heartbeatTimeout
    }
    func canStart(at now: TimeInterval) -> Bool {
        !ending && fresh(at: now) && status?.health == "healthy" && status?.canStart == true
    }
    func canResume(at now: TimeInterval) -> Bool {
        !ending && fresh(at: now) && status?.health == "healthy"
            && (status?.state == "paused" || (status?.state == "exam" && !localStartRequested))
    }
    func showQuestions(at now: TimeInterval) -> Bool {
        !ending && localStartRequested && fresh(at: now)
            && status?.health == "healthy" && status?.state == "exam" && status?.examAllowed == true
    }
}

struct ExamGuardLaunchConfiguration {
    let python: URL
    let runner: URL
    let inventory: URL
    let policy: URL
    let worker: URL?
    let vendors: [String]
    let workerLease: Int
    let sessionDirectory: URL
    let sessionID: String
    let testMode: Bool

    static var projectRoot: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    }
}

final class ExamGuardClient {
    let configuration: ExamGuardLaunchConfiguration
    private(set) var gate: ExamGuardGate
    private(set) var submittedCommandCount = 0
    var onChange: (() -> Void)?
    private var process: Process?
    private var input: FileHandle?
    private var output: FileHandle?
    private var watchdog: Timer?
    private let readerQueue = DispatchQueue(label: "exam.guard.stdout")
    private var buffer = Data() // readerQueue only
    private var stopped = false

    init(configuration: ExamGuardLaunchConfiguration) {
        self.configuration = configuration
        self.gate = ExamGuardGate(sessionID: configuration.sessionID)
    }

    var now: TimeInterval { ExamGuardClock.now() }
    var questionsAllowed: Bool { gate.showQuestions(at: now) }
    var canStart: Bool { gate.canStart(at: now) }
    var canResume: Bool { gate.canResume(at: now) }
    var isRunning: Bool { process?.isRunning == true }

    func launch() {
        precondition(Thread.isMainThread)
        guard process == nil else { return }
        do {
            // The parent output directory is already private. The runner owns
            // creation of its session subdirectory, which must not preexist.
            for file in [configuration.python, configuration.runner, configuration.inventory, configuration.policy] {
                guard FileManager.default.fileExists(atPath: file.path) else { throw ExamGuardError.unavailable }
            }
            let child = Process()
            child.executableURL = configuration.python
            child.arguments = [configuration.runner.path, "--ui-protocol", "--session-dir", configuration.sessionDirectory.path,
                               "--ui-session-id", configuration.sessionID, "--inventory", configuration.inventory.path,
                               "--policy", configuration.policy.path]
            if let worker = configuration.worker { child.arguments?.append(contentsOf: ["--worker", worker.path]) }
            child.arguments?.append(contentsOf: ["--vendors", configuration.vendors.joined(separator: ","),
                                                "--worker-lease", String(configuration.workerLease)])
            if configuration.testMode { child.arguments?.append("--ui-test-mode") }
            var environment = ProcessInfo.processInfo.environment
            // The runner must not inherit optional hook experiments from this GUI.
            for key in Array(environment.keys) where key.hasPrefix("DYLD_") { environment.removeValue(forKey: key) }
            for key in ["PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT"] { environment.removeValue(forKey: key) }
            environment["PYTHONUNBUFFERED"] = "1"
            child.environment = environment
            let stdinPipe = Pipe(), stdoutPipe = Pipe()
            child.standardInput = stdinPipe
            child.standardOutput = stdoutPipe
            child.standardError = FileHandle.standardError
            input = stdinPipe.fileHandleForWriting
            if let input {
                let flags = fcntl(input.fileDescriptor, F_GETFL)
                guard flags >= 0, fcntl(input.fileDescriptor, F_SETFL, flags | O_NONBLOCK) == 0 else {
                    throw ExamGuardError.unavailable
                }
            }
            // A failed command pipe must not terminate the GUI before it hides
            // questions and reports the missing recovery acknowledgement.
            signal(SIGPIPE, SIG_IGN)
            output = stdoutPipe.fileHandleForReading
            output?.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                guard let self else { return }
                self.readerQueue.async { self.consume(data) }
            }
            child.terminationHandler = { [weak self] completed in
                DispatchQueue.main.async {
                    guard let self else { return }
                    if self.gate.status?.state != "finished" {
                        self.fail("检测服务已退出（\(completed.terminationStatus)），恢复结果待确认")
                    }
                }
            }
            process = child
            try child.run()
            let timer = Timer(timeInterval: 0.25, repeats: true) { [weak self] _ in
                guard let self else { return }
                if self.gate.status?.state != "finished" && !self.gate.fresh(at: self.now) {
                    let message = self.gate.lastReceived == nil ? "等待检测服务；试题尚未加载" : "检测服务心跳中断，考试已暂停"
                    if self.gate.faultReason != message { self.fail(message) }
                }
            }
            RunLoop.main.add(timer, forMode: .common)
            watchdog = timer
        } catch {
            process = nil
            output?.readabilityHandler = nil
            fail("检测服务未就绪：\(error.localizedDescription)。请核对构建产物与启动配置。")
        }
    }

    private func consume(_ data: Data) {
        if data.isEmpty {
            output?.readabilityHandler = nil
            DispatchQueue.main.async { [weak self] in
                guard let self, self.gate.status?.state != "finished" else { return }
                self.fail("检测服务通信已关闭，考试已暂停；恢复结果待确认")
            }
            return
        }
        buffer.append(data)
        while let newline = buffer.firstIndex(of: 0x0a) {
            let line = Data(buffer[..<newline])
            buffer.removeSubrange(...newline)
            guard line.count <= 65_536 else {
                DispatchQueue.main.async { [weak self] in self?.fail("检测消息超过限制，考试已暂停") }
                continue
            }
            DispatchQueue.main.async { [weak self] in
                guard let self, !self.stopped else { return }
                do {
                    try self.gate.accept(line, now: self.now)
                    self.onChange?()
                } catch { self.fail("检测消息无效或顺序异常，考试已暂停") }
            }
        }
        if buffer.count > 65_536 {
            buffer.removeAll(keepingCapacity: false)
            DispatchQueue.main.async { [weak self] in self?.fail("检测消息未结束且超过限制，考试已暂停") }
        }
    }

    func send(_ command: String, reason: String? = nil) -> Bool {
        precondition(Thread.isMainThread)
        guard ["inspect", "requestAuthorization", "start", "resume", "pause", "end"].contains(command),
              process?.isRunning == true, let input else {
            fail("检测服务不可用；操作未提交")
            return false
        }
        if command == "start" && !canStart { return false }
        if command == "resume" && !canResume { return false }
        if command == "start" || command == "resume" { gate.requestStart() }
        if command == "end" { gate.requestEnd() }
        var message: [String: Any] = ["protocolVersion": 1, "command": command,
                                    "requestID": UUID().uuidString, "sessionID": configuration.sessionID]
        if let reason { message["reason"] = String(reason.prefix(200)) }
        do {
            var data = try JSONSerialization.data(withJSONObject: message, options: [.sortedKeys])
            data.append(0x0a)
            let atomicLimit = fpathconf(input.fileDescriptor, _PC_PIPE_BUF)
            guard atomicLimit > 0, data.count <= atomicLimit else { throw ExamGuardError.invalidCommand }
            let written = data.withUnsafeBytes { raw -> Int in
                Darwin.write(input.fileDescriptor, raw.baseAddress, raw.count)
            }
            guard written == data.count else { throw ExamGuardError.unavailable }
            submittedCommandCount += 1
            onChange?()
            return true
        } catch { fail("检测命令发送失败，考试已暂停"); return false }
    }

    func localPause(_ reason: String) { fail(reason) }

    private func fail(_ reason: String) {
        gate.fail(reason)
        onChange?()
    }

    /// Called only once AppKit actually terminates. EOF asks the independent
    /// runner to end/recover; the UI never kills the recovery process.
    func closeTransport() {
        stopped = true
        watchdog?.invalidate()
        output?.readabilityHandler = nil
        try? input?.close()
        input = nil
    }
}
