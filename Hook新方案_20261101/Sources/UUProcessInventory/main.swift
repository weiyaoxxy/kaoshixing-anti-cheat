import Foundation
import Darwin

// Reuse the read-only native process identity reader. No arguments, environments,
// memory, account information, termination or launchd mutation are collected.
let result = UUHMNative.enumerate()
let report: [String: Any] = [
    "schemaVersion": 1,
    "observedAtUTC": ISO8601DateFormatter().string(from: Date()),
    "enumerationComplete": result.complete,
    "processes": result.processes.map { $0.identity },
    "unresolved": result.unresolved,
    "systemMutationPerformed": false
]
do {
    let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([10]))
} catch {
    fputs("Process inventory serialization failed\n", stderr)
    exit(1)
}
