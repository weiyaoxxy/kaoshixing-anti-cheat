import AppKit
import CryptoKit
import Darwin
import ObjectiveC
import Security

/// Evidence collected inside an untrusted endpoint is a review signal, not an
/// attestation. In particular, a privileged attacker can replace this monitor.
final class RuntimeIntegrityMonitor {
    private let queue = DispatchQueue(label: "exam.integrity", qos: .utility)
    private let output: URL
    private let sessionID = UUID().uuidString
    private let started = ProcessInfo.processInfo.systemUptime
    private let executable = Bundle.main.executableURL?.resolvingSymlinksInPath().path ?? ""
    private var busy = false // access only from main thread
    private var seenImages = Set<String>()
    private var findings: [String: [String: Any]] = [:]
    private var sequence = 0
    private var lastStatus = ""
    private var previousChecks: [String: Data] = [:]
    private var logError: String?
    private var methodBaselines: [String: (UInt, String)] = [:]

    init(output: URL) {
        self.output = output
        exam_start_image_tracking()
    }

    func refresh(completion: @escaping ([String: Any]) -> Void) {
        dispatchPrecondition(condition: .onQueue(.main))
        guard !busy else { return }
        busy = true
        queue.async {
            let status = self.scan()
            DispatchQueue.main.async { self.busy = false; completion(status) }
        }
    }

    private func event(_ type: String, _ detail: [String: Any]) {
        sequence += 1
        var record = detail
        record["event"] = type
        record["sequence"] = sequence
        record["sessionID"] = sessionID
        record["pid"] = getpid()
        record["timestamp"] = ISO8601DateFormatter().string(from: Date())
        record["elapsedSeconds"] = ProcessInfo.processInfo.systemUptime - started
        do {
            var bytes = try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
            bytes.append(0x0a)
            let file = output.appendingPathComponent("integrity-events.jsonl")
            if !FileManager.default.fileExists(atPath: file.path) {
                guard FileManager.default.createFile(atPath: file.path, contents: nil,
                    attributes: [.posixPermissions: 0o600]) else { throw CocoaError(.fileWriteUnknown) }
            }
            let handle = try FileHandle(forWritingTo: file)
            defer { try? handle.close() }
            try handle.seekToEnd()
            try handle.write(contentsOf: bytes)
            try handle.synchronize()
        } catch { logError = error.localizedDescription }
    }

    private func flag(_ code: String, subject: String, detail: [String: Any] = [:]) {
        let key = code + ":" + subject
        guard findings[key] == nil else { return }
        var finding = detail
        finding["code"] = code
        finding["subject"] = subject
        finding["firstObservedAt"] = ISO8601DateFormatter().string(from: Date())
        finding["meaning"] = "requires_review_not_automatic_cheating_verdict"
        findings[key] = finding
        event("anomaly_observed", finding)
    }

    private func systemImage(_ path: String) -> Bool {
        // This app bundles no third-party plugins. These roots rely on the OS
        // trust boundary (SIP); paths alone are not proof on a compromised OS.
        ["/System/Library/", "/usr/lib/", "/System/Cryptexes/OS/System/Library/",
         "/System/Cryptexes/OS/usr/lib/", "/Library/Apple/System/Library/"].contains { path.hasPrefix($0) }
    }

    private func imageChecks() -> [String: Any] {
        for index in 0..<exam_image_count() {
            guard let cPath = exam_image_path(index) else { continue }
            // Do not resolve a user-controlled symlink after loading: it may
            // have been retargeted to a system library since the callback.
            let path = URL(fileURLWithPath: String(cString: cPath)).standardizedFileURL.path
            guard seenImages.insert(path).inserted else { continue }
            if path != executable && !systemImage(path) {
                flag("unexpected_loaded_image", subject: path,
                     detail: ["evidence": "dyld_add_image", "policy": "demo_has_no_external_plugins"])
            }
        }
        // Record only key names, never the full environment or credentials.
        let keys = ["DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
                    "DYLD_FORCE_FLAT_NAMESPACE"]
        for key in keys where !(ProcessInfo.processInfo.environment[key] ?? "").isEmpty {
            flag("loader_environment_present", subject: key,
                 detail: ["meaning": "injection_or_loader_override_requested_not_proof_of_execution"])
        }
        return ["status": exam_image_tracking_incomplete() == 0 ? "observed" : "unknown",
                "observedImageCount": seenImages.count, "includesUnloadedImageHistory": true]
    }

    private func signatureChecks() -> [String: Any] {
        var checks: [String: Any] = [:]
        var selfCode: SecCode?
        let selfResult = SecCodeCopySelf(SecCSFlags(), &selfCode)
        if selfResult == errSecSuccess, let selfCode {
            let result = SecCodeCheckValidity(selfCode, SecCSFlags(), nil)
            checks["runningCode"] = signatureResult(result, name: "running_code_signature")
        } else { checks["runningCode"] = ["status": "unknown", "osStatus": selfResult] }

        // A fresh object each poll avoids validating a previously cached bundle.
        var diskCode: SecStaticCode?
        let create = SecStaticCodeCreateWithPath(Bundle.main.bundleURL as CFURL, SecCSFlags(), &diskCode)
        if create == errSecSuccess, let diskCode {
            let flags = SecCSFlags(rawValue: kSecCSCheckAllArchitectures | kSecCSCheckNestedCode | kSecCSStrictValidate)
            let result = SecStaticCodeCheckValidity(diskCode, flags, nil)
            checks["bundleSeal"] = signatureResult(result, name: "bundle_seal")
            var info: CFDictionary?
            let infoResult = SecCodeCopySigningInformation(diskCode, SecCSFlags(rawValue: kSecCSSigningInformation), &info)
            if infoResult == errSecSuccess, let values = info as? [String: Any] {
                let identifier = values[kSecCodeInfoIdentifier as String] as? String ?? ""
                let team = values[kSecCodeInfoTeamIdentifier as String] as? String ?? ""
                checks["identifier"] = identifier
                checks["teamIdentifier"] = team
                if identifier != IntegrityBuildPolicy.bundleID {
                    flag("signing_identifier_changed", subject: identifier)
                }
            }
            if let team = IntegrityBuildPolicy.expectedTeamID {
                // Embedded at build time, never accepted from a launch argument
                // or editable runtime config. Still not an off-device trust root.
                let text = "anchor apple generic and identifier \"\(IntegrityBuildPolicy.bundleID)\" and certificate leaf[subject.OU] = \"\(team)\""
                var requirement: SecRequirement?
                let parsed = SecRequirementCreateWithString(text as CFString, SecCSFlags(), &requirement)
                if parsed == errSecSuccess, let requirement {
                    let result = SecStaticCodeCheckValidity(diskCode, flags, requirement)
                    checks["releaseIdentity"] = signatureResult(result, name: "release_identity")
                } else { checks["releaseIdentity"] = ["status": "unknown", "osStatus": parsed] }
            } else {
                checks["releaseIdentity"] = ["status": "unknown", "reason": "no_trusted_team_pinned_development_build"]
            }
        } else {
            checks["bundleSeal"] = ["status": "unknown", "osStatus": create]
            checks["releaseIdentity"] = ["status": "unknown", "reason": "bundle_unavailable"]
        }
        return checks
    }

    private func signatureResult(_ status: OSStatus, name: String) -> [String: Any] {
        if status == errSecSuccess { return ["status": "valid", "osStatus": status] }
        // Distinguish positive integrity failures from IO/permission/API errors.
        let invalid: Set<OSStatus> = [errSecCSSignatureFailed, errSecCSUnsigned, errSecCSReqFailed,
            errSecCSResourcesInvalid, errSecCSResourceRulesInvalid, errSecCSResourceDirectoryFailed,
            errSecCSBadResource, errSecCSResourceNotSupported, errSecCSStaticCodeChanged,
            errSecCSInfoPlistFailed, errSecCSNoMainExecutable, errSecCSBadMainExecutable,
            errSecCSGuestInvalid, errSecCSResourcesNotFound, errSecCSBadNestedCode, errSecCSUnsignedNestedCode,
            errSecCSResourcesNotSealed, errSecCSBadDictionaryFormat, errSecCSUnsealedAppRoot,
            errSecCSUnsealedFrameworkRoot, errSecCSBadFrameworkVersion, errSecCSInvalidSymlink,
            errSecCSRegularFile, errSecCSWeakResourceRules, errSecCSWeakResourceEnvelope,
            errSecCSBadTeamIdentifier, errSecCSInvalidTeamIdentifier, errSecCSInvalidEntitlements]
        if invalid.contains(status) {
            flag("signature_validation_failed", subject: name, detail: ["osStatus": status])
        }
        return ["status": invalid.contains(status) ? "invalid" : "unknown", "osStatus": status,
                "message": (SecCopyErrorMessageString(status, nil) as String?) ?? "validation unavailable"]
    }

    private func methodChecks() -> [String: Any] {
        let watches: [(String, String, Bool)] = [
            ("NativeExamAppDelegate", "persist", true),
            ("NativeExamAppDelegate", "tick", true),
            ("NativeExamAppDelegate", "submitAnswer:", true),
            ("NSApplication", "sendEvent:", false)
        ]
        var unavailable: [String] = []
        for (className, name, isOwn) in watches {
            let key = className + "." + name
            guard let type = NSClassFromString(className),
                  let method = class_getInstanceMethod(type, NSSelectorFromString(name)) else {
                unavailable.append(key); continue
            }
            let address = unsafeBitCast(method_getImplementation(method), to: UnsafeRawPointer.self)
            var info = Dl_info()
            guard dladdr(address, &info) != 0, let cPath = info.dli_fname else {
                flag("method_implementation_unattributed", subject: key)
                continue
            }
            let path = URL(fileURLWithPath: String(cString: cPath)).standardizedFileURL.path
            let expected = isOwn ? path == executable : path.hasPrefix("/System/Library/Frameworks/AppKit.framework/")
            if !expected { flag("method_implementation_outside_expected_image", subject: key, detail: ["image": path]) }
            // Compare a short entry prefix plus IMP. This is a sampled local
            // baseline, not a complete text-segment or arbitrary hook detector.
            var code = Data(count: 32)
            let readable = code.withUnsafeMutableBytes { exam_read_code(address, $0.baseAddress!, $0.count) != 0 }
            guard readable else { unavailable.append(key + ":unreadable_code"); continue }
            let hash = SHA256.hash(data: code).map { String(format: "%02x", $0) }.joined()
            let pointer = UInt(bitPattern: address)
            if let baseline = methodBaselines[key], baseline.0 != pointer || baseline.1 != hash {
                flag("method_implementation_changed", subject: key, detail: ["image": path])
            } else if methodBaselines[key] == nil { methodBaselines[key] = (pointer, hash) }
        }
        return ["status": unavailable.isEmpty ? "observed" : "unknown", "unavailable": unavailable,
                "watchedMethodCount": watches.count, "baselineTrust": "local_first_observation"]
    }

    private func scan() -> [String: Any] {
        let images = imageChecks()
        let methods = methodChecks()
        let signatures = signatureChecks()
        // Keep loss/recovery of individual checks even when a development build
        // already has an unknown release identity and its overall state is unchanged.
        var checkStates = signatures.compactMapValues { $0 as? [String: Any] }
        checkStates["images"] = ["status": images["status"] ?? "unknown"]
        checkStates["methods"] = methods
        for key in checkStates.keys.sorted() {
            guard let value = checkStates[key],
                  let bytes = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
                  previousChecks[key] != bytes else { continue }
            event("check_state_changed", ["check": key, "result": value])
            previousChecks[key] = bytes
        }
        let incomplete = images["status"] as? String == "unknown" || methods["status"] as? String == "unknown" ||
            signatures.values.contains { ($0 as? [String: Any])?["status"] as? String == "unknown" }
        let status = !findings.isEmpty ? "anomalyObserved" : incomplete ? "incomplete" : "noAnomalyObserved"
        if status != lastStatus {
            event("assessment_changed", ["status": status, "findingCount": findings.count])
            lastStatus = status
        }
        var snapshot: [String: Any] = [
            "schemaVersion": 1, "sessionID": sessionID, "pid": getpid(),
            "timestamp": ISO8601DateFormatter().string(from: Date()),
            "elapsedSeconds": ProcessInfo.processInfo.systemUptime - started,
            "status": status, "requiresReview": !findings.isEmpty, "checksIncomplete": incomplete || logError != nil,
            "findings": findings.keys.sorted().compactMap { findings[$0] },
            "images": images, "methods": methods, "signatures": signatures,
            "evidenceTrust": "local_only_not_remote_attestation", "serverReported": false,
            "allHooksDetectable": false, "pollIntervalSeconds": 5,
            "eventLog": "integrity-events.jsonl", "eventSequence": sequence
        ]
        if let logError {
            snapshot["recordingError"] = logError
            if findings.isEmpty { snapshot["status"] = "incomplete" }
        }
        do {
            let bytes = try JSONSerialization.data(withJSONObject: snapshot, options: [.prettyPrinted, .sortedKeys])
            try bytes.write(to: output.appendingPathComponent("integrity-status.json"), options: .atomic)
        } catch {
            logError = error.localizedDescription
            snapshot["recordingError"] = error.localizedDescription
            snapshot["checksIncomplete"] = true
            if findings.isEmpty { snapshot["status"] = "incomplete" }
        }
        return snapshot
    }
}
