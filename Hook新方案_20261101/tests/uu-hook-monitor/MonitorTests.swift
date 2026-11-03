import Foundation
import Darwin

@main
struct MonitorTests {
    static var checks = 0
    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        checks += 1
        if !condition() {
            fputs("FAIL: \(message)\n", stderr)
            exit(1)
        }
    }

    static func main() throws {
        if CommandLine.arguments.contains("--live") {
            try live()
            return
        }
        let process = UUHMProcess(pid: 1234, parentPID: 1, uid: 501,
            executable: "/Applications/UURemote.app/Contents/Helpers/UURemoteServer",
            startSeconds: 1_800_000_000, startMicroseconds: 123456, role: "server")
        let header = "Process: UURemoteServer [1234]\nPath: \(process.executable)\n"
        let executable = "__TEXT 104c34000-10554c000 [ 9312K 4544K 0K 0K] r-x/r-x SM=COW \(process.executable)\n"
        let hook = "__TEXT 107320000-107d40000 [ 48K 16K 0K 0K] r-x/rwx SM=COW /tmp/fixture/libCaptureHook-v1.2.dylib\n"
        let witness = hook.replacingOccurrences(of: "libCaptureHook-v1.2", with: "libLoadWitness-v2")
        func inspect(_ text: String, result: UUHMCommandResult? = nil, current: UUHMProcess? = process) -> [String: Any] {
            UUHMInspection.classify(result ?? UUHMCommandResult(exitCode: 0, stdout: text), process: process, current: current)
        }
        expect(inspect(header + executable + hook)["status"] as? String == "observedLoaded", "current executable Hook mapping")
        expect(inspect(header + executable)["status"] as? String == "noKnownHookObserved", "usable mapping without known library")
        expect(inspect(header + executable + witness)["status"] as? String == "noKnownHookObserved", "witness is not a capture Hook")
        expect(inspect(header + executable + witness)["witnessStatus"] as? String == "observedLoaded", "witness evidence is separate")
        expect(inspect(header + executable + hook.replacingOccurrences(of: ".dylib", with: ".dylib.bak"))["status"] as? String == "noKnownHookObserved", "filename suffix cannot spoof match")
        expect(inspect(header + executable + hook.replacingOccurrences(of: "__TEXT", with: "mapped file"))["status"] as? String == "noKnownHookObserved", "ordinary file map is not a loaded executable image")
        expect(inspect(header + executable + hook.replacingOccurrences(of: "r-x/rwx", with: "r--/r--"))["status"] as? String == "noKnownHookObserved", "read-only mapping is not executable evidence")
        expect(inspect(header + "Summary only\n")["status"] as? String == "unknown", "empty mapping output is unknown")
        expect(inspect((header + executable + hook).replacingOccurrences(of: "[1234]", with: "[1235]"))["status"] as? String == "unknown", "reported PID must match")
        expect(inspect(header + executable + hook, current: nil)["status"] as? String == "unknown", "process exit is unknown")
        let recycled = UUHMProcess(pid: process.pid, parentPID: 1, uid: 501, executable: process.executable,
            startSeconds: process.startSeconds, startMicroseconds: process.startMicroseconds + 1, role: "server")
        expect(inspect(header + executable + hook, current: recycled)["status"] as? String == "unknown", "PID reuse is unknown")
        for failed in [UUHMCommandResult(exitCode: 1, stdout: header + executable + hook, stderr: "task_for_pid permission denied"),
                       UUHMCommandResult(exitCode: 0, stdout: header + executable + hook, timedOut: true),
                       UUHMCommandResult(exitCode: 0, stdout: header + executable + hook, truncated: true)] {
            expect(inspect("", result: failed)["status"] as? String == "unknown", "failed, timed out, or truncated inspection cannot become loaded/clean")
        }
        let loaded = inspect(header + executable + hook)
        expect(loaded["actualHookInvocationVerified"] as? Bool == false, "loading does not establish invocation")
        expect(loaded["captureBlockingVerified"] as? Bool == false, "loading does not establish blocking")
        let redacted = UUHMInspection.safePath("/tmp/12345678-abcd-1234-abcd-123456789abc/libCaptureHook.dylib")
        expect(!redacted.contains("12345678-abcd"), "UUID path component redacted")
        expect(JSONSerialization.isValidJSONObject(loaded), "classification is valid JSON")
        expect(loaded["knownHookIdentityVerified"] as? Bool == false && loaded["moduleNameMatchOnly"] as? Bool == true,
               "filename match never authenticates our library")

        let historyDirectory = FileManager.default.temporaryDirectory.appendingPathComponent("uu-monitor-history-\(getpid())")
        try FileManager.default.createDirectory(at: historyDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: historyDirectory) }
        let historyFile = historyDirectory.appendingPathComponent("uu-hook-events.jsonl")
        var history = UUHMHistory()
        func snapshot(_ rows: [[String: Any]], at time: String) -> [String: Any] {
            ["processes": rows, "status": rows.isEmpty ? "notRunning" : "observedLoaded", "components": [],
             "observedAtUTC": time, "enumerationComplete": true]
        }
        var row = process.identity.merging(loaded) { _, new in new }
        expect(history.record(snapshot([row], at: "2026-01-01T00:00:00Z"), to: historyFile), "initial history persisted")
        expect(history.record(snapshot([row], at: "2026-01-01T00:00:05Z"), to: historyFile), "unchanged history accepted")
        row["executableRegionCount"] = 999
        expect(history.record(snapshot([row], at: "2026-01-01T00:00:10Z"), to: historyFile), "region count omitted from dedup")
        var historyLines = try String(contentsOf: historyFile, encoding: .utf8).split(separator: "\n")
        expect(historyLines.count == 1, "time and region-count changes do not append duplicate events")
        row["status"] = "noKnownHookObserved"
        row["moduleEvidence"] = [[String: String]]()
        expect(history.record(snapshot([row], at: "2026-01-01T00:00:15Z"), to: historyFile), "loaded-to-not-observed transition persisted")
        row["startTimeMicroseconds"] = process.startMicroseconds + 1
        expect(history.record(snapshot([row], at: "2026-01-01T00:00:20Z"), to: historyFile), "PID reuse birth identity transition persisted")
        expect(history.record(snapshot([], at: "2026-01-01T00:00:25Z"), to: historyFile), "exit transition persisted")
        historyLines = try String(contentsOf: historyFile, encoding: .utf8).split(separator: "\n")
        expect(historyLines.count == 4, "all three state transitions retained")
        for line in historyLines {
            let event = try JSONSerialization.jsonObject(with: Data(line.utf8)) as! [String: Any]
            expect(event["locallyMutable"] as? Bool == true && event["captureBlockingVerified"] as? Bool == false,
                   "history states local trust and blocking limits")
        }

        let began = ProcessInfo.processInfo.systemUptime
        let timeout = UUHMCommand.run("/bin/sleep", ["10"], timeout: 0.2)
        expect(timeout.timedOut, "owned helper times out")
        expect(ProcessInfo.processInfo.systemUptime - began < 2, "timeout return bounded")
        let flood = UUHMCommand.run("/usr/bin/yes", ["fixture-output"], timeout: 2, maximumBytes: 1024)
        expect(flood.truncated && !flood.succeeded, "output bound terminates noisy owned helper")
        let dual = UUHMCommand.run("/usr/bin/python3", ["-c", "import os; os.write(1,b'x'*131072); os.write(2,b'y'*131072)"], timeout: 3)
        expect(dual.succeeded && dual.stdout.utf8.count == 131072 && dual.stderr.utf8.count == 131072, "stdout and stderr both drain without deadlock")
        let missing = UUHMCommand.run("/nonexistent/uu-monitor-fixture", [], timeout: 0.2)
        expect(missing.launchFailed, "unavailable tool is explicit")

        guard CommandLine.arguments.count > 1 else { fatalError("pass fixture dylib path") }
        // Load a harmless, self-owned fixture into this test process only. No UU process is altered.
        let library = CommandLine.arguments[1]
        guard let handle = dlopen(library, RTLD_NOW | RTLD_LOCAL) else { fatalError("fixture dlopen failed") }
        defer { dlclose(handle) }
        guard let own = UUHMNative.process(getpid(), role: "fixture") else { fatalError("own process identity unavailable") }
        let maps = UUHMCommand.run("/usr/bin/vmmap", ["-w", String(getpid())], timeout: 5)
        let actual = UUHMInspection.classify(maps, process: own, current: UUHMNative.process(getpid(), role: "fixture"))
        if actual["status"] as? String != "observedLoaded" {
            print("Fixture inspection diagnostic: \(actual)")
            for line in maps.stdout.split(separator: "\n") where line.hasPrefix("Process:") || line.hasPrefix("Path:") || line.contains("libCaptureHook-test") {
                print(line)
            }
        }
        expect(actual["status"] as? String == "observedLoaded", "real vmmap detects loaded fixture in own process")
        print("PASS: \(checks) checks; no UU process launched, signaled, injected, or reconfigured")
    }

    static func live() throws {
        guard let index = CommandLine.arguments.firstIndex(of: "--output"), index + 1 < CommandLine.arguments.count else {
            fatalError("--live requires --output JSON_FILE")
        }
        let output = URL(fileURLWithPath: CommandLine.arguments[index + 1])
        let before = UUHMNative.enumerate()
        let monitor = UUHookMonitor(output: output)
        var reports: [[String: Any]] = []
        for _ in 0..<2 {
            monitor.refresh { report in
                expect(Thread.isMainThread, "refresh callback runs on main thread")
                reports.append(report)
            }
        }
        let deadline = Date().addingTimeInterval(12)
        while reports.count < 2 && Date() < deadline { _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.05)) }
        expect(reports.count == 2, "both coalesced callbacks completed within twelve seconds")
        expect(reports[0]["scanStartedAtUTC"] as? String == reports[1]["scanStartedAtUTC"] as? String, "concurrent requests share one scan")
        expect(reports[0]["reportWriteSucceeded"] as? Bool == true, "JSON report atomically written")
        expect(JSONSerialization.isValidJSONObject(reports[0]), "complete report is valid JSON")
        let saved = try JSONSerialization.jsonObject(with: Data(contentsOf: output)) as! [String: Any]
        expect(saved["actualHookInvocationVerified"] as? Bool == false, "live inspection does not claim capture invocation")
        let after = UUHMNative.enumerate()
        let unchanged = before.processes.count == after.processes.count && before.processes.allSatisfy { old in after.processes.contains { old.sameLifetime(as: $0) } }
        print("PASS: \(checks) live checks; UU process lifetimes unchanged=\(unchanged); status=\(saved["status"] ?? "unknown")")
        print("Report: \(output.path)")
    }
}
