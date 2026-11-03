import AppKit
import ScreenCaptureKit
import CoreMedia
import CoreImage
import ImageIO
import UniformTypeIdentifiers

func savePNG(_ image: CGImage, to url: URL) throws {
    guard let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        throw NSError(domain: "CaptureProbe", code: 1, userInfo: [NSLocalizedDescriptionKey: "Cannot create PNG destination"])
    }
    CGImageDestinationAddImage(dest, image, nil)
    guard CGImageDestinationFinalize(dest) else {
        throw NSError(domain: "CaptureProbe", code: 2, userInfo: [NSLocalizedDescriptionKey: "PNG encoding failed"])
    }
}
func nonFiniteToken(_ value: Double) -> String {
    value.isNaN ? "NaN" : (value < 0 ? "-Infinity" : "+Infinity")
}
func sanitizeJSON(_ value: Any, path: String = "$", substitutions: inout [String]) -> Any {
    if let number = value as? NSNumber {
        if number.doubleValue.isFinite { return number }
        substitutions.append(path)
        return nonFiniteToken(number.doubleValue)
    }
    if let dictionary = value as? [String: Any] {
        return dictionary.mapValues { _ in NSNull() } .merging(dictionary.reduce(into: [String: Any]()) { result, pair in
            result[pair.key] = sanitizeJSON(pair.value, path: path + "." + pair.key, substitutions: &substitutions)
        }) { _, new in new }
    }
    if let array = value as? [Any] {
        return array.enumerated().map { index, item in sanitizeJSON(item, path: path + "[\(index)]", substitutions: &substitutions) }
    }
    if value is String || value is NSNull { return value }
    substitutions.append(path + " (unsupported type)")
    return "unsupported(\(type(of: value))): \(String(describing: value))"
}
func safeJSONData(_ dictionary: [String: Any]) throws -> Data {
    var paths: [String] = []
    var sanitized = sanitizeJSON(dictionary, substitutions: &paths) as! [String: Any]
    sanitized["jsonEncodingPolicy"] = "Non-finite numeric values are encoded as NaN/+Infinity/-Infinity strings, never zero. CGRect non-finite coordinates additionally name nonFiniteFields."
    sanitized["jsonSanitizedPaths"] = paths.sorted()
    guard JSONSerialization.isValidJSONObject(sanitized) else {
        throw NSError(domain: "CaptureProbe.JSON", code: 74, userInfo: [NSLocalizedDescriptionKey: "Sanitized report is not a valid JSON object; serialization was not attempted"])
    }
    return try JSONSerialization.data(withJSONObject: sanitized, options: [.prettyPrinted, .sortedKeys])
}
func rectJSON(_ r: CGRect) -> [String: Any] {
    let components = ["x": Double(r.origin.x), "y": Double(r.origin.y), "width": Double(r.width), "height": Double(r.height)]
    var result = components.mapValues { $0.isFinite ? $0 as Any : nonFiniteToken($0) as Any }
    let invalid = components.filter { !$0.value.isFinite }.map(\.key).sorted()
    if !invalid.isEmpty { result["nonFiniteFields"] = invalid; result["isNull"] = r.isNull; result["isInfinite"] = r.isInfinite }
    return result
}
func errorJSON(_ e: Error) -> [String: Any] {
    let n = e as NSError
    return ["status": "error", "domain": n.domain, "code": n.code, "message": n.localizedDescription]
}
func attachmentRect(_ value: Any) -> [String: Any]? {
    if let rect = value as? CGRect { return rectJSON(rect) }
    if let dictionary = value as? [String: Any], let rect = CGRect(dictionaryRepresentation: dictionary as CFDictionary) { return rectJSON(rect) }
    if let value = value as? NSValue, String(cString: value.objCType).contains("CGRect") { return rectJSON(value.rectValue) }
    return nil
}
func frameMetadata(_ attachment: [SCStreamFrameInfo: Any]) -> [String: Any] {
    var result: [String: Any] = [:]
    for (name, key) in [("scaleFactor", SCStreamFrameInfo.scaleFactor), ("contentScale", .contentScale), ("displayTime", .displayTime)] {
        if let value = attachment[key] as? NSNumber { result[name] = value }
    }
    var rectKeys: [(String, SCStreamFrameInfo)] = [("contentRect", .contentRect)]
    if #available(macOS 13.1, *) { rectKeys.append(("screenRect", .screenRect)) }
    if #available(macOS 14.0, *) { rectKeys.append(("boundingRect", .boundingRect)) }
    if #available(macOS 14.2, *) { rectKeys.append(("presenterOverlayContentRect", .presenterOverlayContentRect)) }
    for (name, key) in rectKeys {
        if let value = attachment[key] {
            if let rect = attachmentRect(value) { result[name] = rect }
            else { result[name + "Unparsed"] = String(describing: value) }
        }
    }
    if let values = attachment[.dirtyRects] as? [Any] { result["dirtyRects"] = values.compactMap(attachmentRect) }
    return result
}
struct ProbeOptions {
    let flags: Set<String>
    let values: [String: String]
    var only: String { values["--only"] ?? "all" }
    var scope: String { values["--scope"] ?? "all" }
    var extended: Bool { flags.contains("--extended") }
    var captureApplication: Bool { flags.contains("--capture-application") || scope == "application" }
    var duration: Double { Double(values["--duration"] ?? "2")! }
    static func parse(_ args: [String]) throws -> ProbeOptions {
        let booleanFlags: Set<String> = ["--help", "--permission", "--request-permission", "--list", "--exercise-filter-update", "--extended", "--capture-application", "--omit-cursor", "--json-self-test"]
        let valueFlags: Set<String> = ["--window-id", "--target-name", "--output", "--duration", "--only", "--scope"]
        var flags = Set<String>(), values: [String: String] = [:], i = 0
        func invalid(_ message: String) -> NSError { NSError(domain: "CaptureProbe.Arguments", code: 64, userInfo: [NSLocalizedDescriptionKey: message]) }
        while i < args.count {
            let key = args[i]
            guard !flags.contains(key), values[key] == nil else { throw invalid("Duplicate option: " + key) }
            if booleanFlags.contains(key) { flags.insert(key); i += 1 }
            else if valueFlags.contains(key) {
                guard i + 1 < args.count, !args[i + 1].hasPrefix("--"), !args[i + 1].isEmpty else { throw invalid("Missing value for " + key) }
                values[key] = args[i + 1]; i += 2
            } else { throw invalid("Unknown argument: " + key) }
        }
        let option = ProbeOptions(flags: flags, values: values)
        guard ["all", "cg", "screenshot", "stream"].contains(option.only) else { throw invalid("--only must be all, cg, screenshot, or stream") }
        guard ["all", "window", "display", "application"].contains(option.scope) else { throw invalid("--scope must be all, window, display, or application") }
        guard let duration = Double(values["--duration"] ?? "2"), duration.isFinite, (0.5...30).contains(duration) else { throw invalid("--duration must be finite and between 0.5 and 30 seconds") }
        if let id = values["--window-id"], UInt32(id) == nil || UInt32(id) == 0 { throw invalid("--window-id must be a positive UInt32") }
        if option.captureApplication && !option.extended { throw invalid("Application capture requires --extended") }
        if option.captureApplication && !["all", "stream"].contains(option.only) { throw invalid("Application capture requires --only stream or all") }
        if flags.contains("--exercise-filter-update") && !["all", "stream"].contains(option.only) { throw invalid("Filter update exercise requires --only stream or all") }
        return option
    }
}
final class StreamSink: NSObject, SCStreamOutput, SCStreamDelegate, @unchecked Sendable {
    let directory: URL
    let queue = DispatchQueue(label: "CaptureProbe.frames")
    let context = CIContext(options: [.cacheIntermediates: false])
    var frames: [[String: Any]] = []
    var errors: [[String: Any]] = []
    var count = 0
    var saved = 0
    var phase = "initial"
    var phaseEvents: [[String: Any]] = []
    init(_ directory: URL) { self.directory = directory }
    func markPhase(_ name: String) {
        queue.sync {
            phase = name
            phaseEvents.append(["phase": name, "hostUptimeSeconds": ProcessInfo.processInfo.systemUptime, "at": ISO8601DateFormatter().string(from: Date())])
        }
    }
    func stream(_ stream: SCStream, didStopWithError error: Error) { queue.async { self.errors.append(errorJSON(error)) } }
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen else { return }
        let pts = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sampleBuffer))
        var item: [String: Any] = ["sampleValid": CMSampleBufferIsValid(sampleBuffer), "phase": phase, "callbackHostUptimeSeconds": ProcessInfo.processInfo.systemUptime]
        if pts.isFinite { item["ptsSeconds"] = pts } else { item["ptsInvalid"] = true }
        let attachments = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]]
        if let first = attachments?.first { item["attachments"] = frameMetadata(first) }
        let rawStatus = attachments?.first?[.status] as? Int
        if let rawStatus { item["SCFrameStatusRaw"] = rawStatus }
        guard rawStatus == SCFrameStatus.complete.rawValue, let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else {
            item["saved"] = false; frames.append(item); return
        }
        count += 1
        let ci = CIImage(cvPixelBuffer: pixelBuffer)
        guard let image = context.createCGImage(ci, from: ci.extent) else {
            item["saved"] = false; item["error"] = "CIContext createCGImage failed"; frames.append(item); return
        }
        let name = String(format: "frame-%03d.png", count)
        do {
            try savePNG(image, to: directory.appendingPathComponent(name))
            saved += 1
            item["saved"] = true; item["file"] = name; item["width"] = image.width; item["height"] = image.height
        } catch { item["saveError"] = errorJSON(error) }
        frames.append(item)
    }
    func result() -> [String: Any] { queue.sync { ["completeFramesReceived": count, "completeFramesSaved": saved, "frames": frames, "streamErrors": errors, "phaseEvents": phaseEvents] } }
}


// Phase labels use callback delivery time. The update request/completion timestamps
// and sample PTS are retained so the transition is not mistaken for an exact PTS boundary.
func runStream(filter: SCContentFilter, configuration: SCStreamConfiguration, directory: URL, duration: Double, exerciseUpdate: Bool, initialPhase: String = "initial") async -> [String: Any] {
    do { try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true) }
    catch { return errorJSON(error) }
    let sink = StreamSink(directory)
    let stream = SCStream(filter: filter, configuration: configuration, delegate: sink)
    var lifecycle: [String: Any] = ["directory": directory.lastPathComponent, "durationPerPhaseRequestedSeconds": duration, "durationRequestedSeconds": duration * (exerciseUpdate ? 2 : 1), "filterUpdateRequested": exerciseUpdate]
    var started = false
    do {
        try stream.addStreamOutput(sink, type: .screen, sampleHandlerQueue: sink.queue)
        sink.markPhase(initialPhase)
        try await stream.startCapture()
        started = true
        try await Task.sleep(nanoseconds: UInt64(duration * 1_000_000_000))
        if exerciseUpdate {
            sink.markPhase("update-requested")
            try await stream.updateContentFilter(filter)
            sink.markPhase("after-update")
            lifecycle["filterUpdateCompleted"] = true
            try await Task.sleep(nanoseconds: UInt64(duration * 1_000_000_000))
        }
        try await stream.stopCapture()
        started = false
        lifecycle["status"] = "completed"
    } catch {
        lifecycle["status"] = "error"
        lifecycle["lifecycleError"] = errorJSON(error)
        if started {
            do { try await stream.stopCapture() }
            catch { lifecycle["stopAfterError"] = errorJSON(error) }
        }
    }
    var result = sink.result()
    result.merge(lifecycle) { _, new in new }
    return result
}

@main struct CaptureProbe {
    static func main() async {
        let args = Array(CommandLine.arguments.dropFirst())
        let options: ProbeOptions
        do { options = try ProbeOptions.parse(args) }
        catch {
            if let data = try? JSONSerialization.data(withJSONObject: errorJSON(error), options: [.sortedKeys]) { print(String(decoding: data, as: UTF8.self)) }
            exit(64)
        }
        func value(_ key: String) -> String? { options.values[key] }
        if args.contains("--help") {
            print("CaptureProbe [--permission] [--request-permission] [--list] [--window-id ID | --target-name ExamCaptureDemo] [--output DIR] [--duration 2] [--only cg|screenshot|stream|all] [--exercise-filter-update] [--extended] [--capture-application] [--omit-cursor] [--scope window|display|application|all]")
            return
        }
        if args.contains("--json-self-test") {
            do {
                let fixture: [String: Any] = ["nullRect": rectJSON(.null), "infiniteRect": rectJSON(.infinite), "finiteRect": rectJSON(CGRect(x: 1, y: 2, width: 3, height: 4)), "nested": [["nan": Double.nan, "positiveInfinity": Double.infinity, "negativeInfinity": -Double.infinity, "finite": 7.5]], "boolean": true]
                let data = try safeJSONData(fixture)
                let parsed = try JSONSerialization.jsonObject(with: data) as! [String: Any]
                let nested = (parsed["nested"] as! [[String: Any]])[0]
                precondition(nested["nan"] as? String == "NaN")
                precondition(nested["positiveInfinity"] as? String == "+Infinity")
                precondition(nested["negativeInfinity"] as? String == "-Infinity")
                precondition(nested["finite"] as? Double == 7.5)
                precondition(parsed["boolean"] as? Bool == true)
                precondition((parsed["nullRect"] as? [String: Any])?["x"] as? String == "+Infinity")
                print(String(decoding: data, as: UTF8.self))
            } catch { fputs("JSON self-test failed: \(error)\n", stderr); exit(74) }
            return
        }
        let fm = FileManager.default
        let out = URL(fileURLWithPath: value("--output") ?? "artifacts/probe-\(Int(Date().timeIntervalSince1970))-\(UUID().uuidString.prefix(8))", isDirectory: true)
        // Reserve a clean directory before doing any capture or permission request.
        // An interrupted run also stays nonempty and cannot silently contaminate a rerun.
        do {
            if fm.fileExists(atPath: out.path), !(try fm.contentsOfDirectory(atPath: out.path)).isEmpty {
                throw NSError(domain: "CaptureProbe.Output", code: 73, userInfo: [NSLocalizedDescriptionKey: "Output directory is not empty; use a new directory: " + out.path])
            }
            try fm.createDirectory(at: out, withIntermediateDirectories: true)
            let lockPath = out.appendingPathComponent(".capture-probe-reservation").path
            let descriptor = open(lockPath, O_WRONLY | O_CREAT | O_EXCL, 0o600)
            guard descriptor >= 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
            close(descriptor)
        } catch {
            if let data = try? JSONSerialization.data(withJSONObject: errorJSON(error), options: [.sortedKeys]) { print(String(decoding: data, as: UTF8.self)) }
            exit(73)
        }
        var report: [String: Any] = [
            "startedAt": ISO8601DateFormatter().string(from: Date()),
            "processID": ProcessInfo.processInfo.processIdentifier,
            "operatingSystem": ProcessInfo.processInfo.operatingSystemVersionString,
            "arguments": args,
            "scope": options.scope,
            "extended": options.extended,
            "omitCursorRequested": args.contains("--omit-cursor"),
            "cursorPolicyNote": "--omit-cursor controls SCStreamConfiguration for filter screenshots/streams. Rectangle capture and legacy CG APIs expose no cursor argument here; their results retain their API defaults.",
            "permissionBefore": CGPreflightScreenCaptureAccess(),
            "interpretation": "Images and frame status are observations only. Black/empty/missing output alone does not prove protection; compare an unprotected control and verify visible content independently."
        ]
        func finish() {
            report["finishedAt"] = ISO8601DateFormatter().string(from: Date())
            do {
                try fm.createDirectory(at: out, withIntermediateDirectories: true)
                let data = try safeJSONData(report)
                try data.write(to: out.appendingPathComponent("report.json"), options: .atomic)
                print(String(decoding: data, as: UTF8.self)); print("Report: \(out.path)/report.json")
            } catch { fputs("Report write error: \(error)\n", stderr); exit(74) }
        }
        if args.contains("--request-permission") { report["permissionRequestResult"] = CGRequestScreenCaptureAccess() }
        report["permissionAfter"] = CGPreflightScreenCaptureAccess()
        if args.contains("--permission") { finish(); return }
        do { try fm.createDirectory(at: out, withIntermediateDirectories: true) } catch { report["setupError"] = errorJSON(error); finish(); return }
        let rawWindows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
        let windows = rawWindows.map { w -> [String: Any] in
            ["id": w[kCGWindowNumber as String] ?? 0, "owner": w[kCGWindowOwnerName as String] ?? "", "title": w[kCGWindowName as String] ?? "", "ownerPID": w[kCGWindowOwnerPID as String] ?? 0, "bounds": w[kCGWindowBounds as String] ?? [:], "sharingState": w[kCGWindowSharingState as String] ?? -1, "layer": w[kCGWindowLayer as String] ?? -1]
        }
        report["cgWindows"] = windows
        let only = options.only
        var content: SCShareableContent?
        if only != "cg" || args.contains("--list") {
            do { content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true) }
            catch { report["shareableContentError"] = errorJSON(error) }
        }
        if let content {
            report["scWindows"] = content.windows.map { w -> [String: Any] in ["id": w.windowID, "title": w.title ?? "", "owner": w.owningApplication?.applicationName ?? "", "ownerPID": w.owningApplication?.processID ?? 0, "frame": rectJSON(w.frame), "onScreen": w.isOnScreen] }
            report["scDisplays"] = content.displays.map { ["id": $0.displayID, "width": $0.width, "height": $0.height, "frame": rectJSON($0.frame)] as [String: Any] }
        }
        if args.contains("--list") { finish(); return }
        let targetName = value("--target-name") ?? "ExamCaptureDemo"
        let suppliedID = value("--window-id").flatMap(UInt32.init)
        let scTarget = content?.windows.first { w in suppliedID.map { w.windowID == $0 } ?? ((w.title ?? "").contains(targetName) || (w.owningApplication?.applicationName ?? "").contains(targetName)) }
        let cgTarget = windows.first { w in suppliedID.map { (w["id"] as? NSNumber)?.uint32Value == $0 } ?? ((w["title"] as? String ?? "").contains(targetName) || (w["owner"] as? String ?? "").contains(targetName)) }
        let targetID = suppliedID ?? scTarget?.windowID ?? (cgTarget?["id"] as? NSNumber)?.uint32Value
        let targetRectCG = (cgTarget?["bounds"] as? [String: Any]).flatMap { CGRect(dictionaryRepresentation: $0 as CFDictionary) }
        let targetRect = targetRectCG ?? scTarget?.frame
        if let targetRect { report["targetRectangle"] = rectJSON(targetRect); report["targetRectangleSource"] = targetRectCG == nil ? "SCWindow.frame fallback" : "CGWindow bounds" }
        var directDisplayID = CGMainDisplayID()
        var directDisplayMatchCount: UInt32 = 0
        if let targetRect { _ = CGGetDisplaysWithRect(targetRect, 1, &directDisplayID, &directDisplayMatchCount) }
        report["legacyDirectDisplayID"] = directDisplayID
        report["legacyDirectDisplayMatchedTargetRect"] = directDisplayMatchCount > 0
        report["targetFoundInCGList"] = cgTarget != nil
        report["targetFoundInSCList"] = scTarget != nil
        if let targetID { report["targetWindowID"] = targetID }
        else { report["targetError"] = "Target window not found. Display paths may still run; never interpret this as protection." }
        if only == "all" || only == "cg" {
            var cg: [String: Any] = ["symbolAvailable": ProbeLegacyCaptureAvailable(), "invocation": "dlsym of public legacy CGWindowListCreateImage; direct declaration unavailable in macOS 15+ SDK; runtime behavior is recorded without claiming supported deployment."]
            func capture(_ path: String, rect: CGRect, options: CGWindowListOption, windowID: CGWindowID) -> [String: Any] {
                guard let image = ProbeLegacyCapture(rect, options.rawValue, windowID, CGWindowImageOption.boundsIgnoreFraming.rawValue) else { return ["status": "nil_image"] }
                do { try savePNG(image, to: out.appendingPathComponent(path)); return ["status": "saved", "file": path, "width": image.width, "height": image.height] }
                catch { return errorJSON(error) }
            }
            if let targetID { cg["window"] = capture("cg-window.png", rect: .null, options: .optionIncludingWindow, windowID: targetID) }
            cg["display"] = capture("cg-display.png", rect: .infinite, options: [.optionOnScreenOnly, .excludeDesktopElements], windowID: kCGNullWindowID)
            if options.extended {
                var direct: [String: Any] = ["symbolAvailable": ProbeLegacyDisplayCaptureAvailable(), "displayID": directDisplayID, "invocation": "dlsym of historical public CGDisplayCreateImage; runtime compatibility experiment"]
                if let image = ProbeLegacyDisplayCapture(directDisplayID) {
                    do {
                        let file = "cg-direct-display.png"
                        try savePNG(image, to: out.appendingPathComponent(file))
                        direct.merge(["status": "saved", "file": file, "width": image.width, "height": image.height]) { _, new in new }
                    } catch { direct.merge(errorJSON(error)) { _, new in new } }
                } else { direct["status"] = "nil_image" }
                cg["directDisplay"] = direct
            }
            report["coreGraphics"] = cg
        }
        if options.extended && ["all", "screenshot"].contains(only) {
            if #available(macOS 15.2, *) {
                if let rect = targetRect, !rect.isEmpty, !rect.isInfinite, !rect.isNull {
                    do {
                        let image = try await SCScreenshotManager.captureImage(in: rect)
                        let file = "sck-screenshot-rectangle.png"
                        try savePNG(image, to: out.appendingPathComponent(file))
                        report["screenshot_rectangle"] = ["status": "saved", "file": file, "rectangle": rectJSON(rect), "width": image.width, "height": image.height]
                    } catch { report["screenshot_rectangle"] = errorJSON(error) }
                } else { report["screenshot_rectangle"] = ["status": "skipped", "reason": "No valid target window rectangle"] }
            } else { report["screenshot_rectangle"] = ["status": "unavailable", "requires": "macOS 15.2"] }
        }
        if scTarget == nil && only != "cg" && ["all", "window"].contains(options.scope) {
            let skipped: [String: Any] = ["status": "skipped", "reason": "Target SCWindow unavailable; no window content filter could be created. Missing output is not evidence of protection."]
            if only == "all" || only == "screenshot" { report["screenshot_window"] = skipped }
            if only == "all" || only == "stream" { report["stream_window"] = skipped }
        }
        if let content {
            var filters: [(String, SCContentFilter)] = []
            if let scTarget, ["all", "window"].contains(options.scope) { filters.append(("window", SCContentFilter(desktopIndependentWindow: scTarget))) }
            let display = content.displays.first(where: { d in scTarget.map { d.frame.intersects($0.frame) } ?? (d.displayID == CGMainDisplayID()) }) ?? content.displays.first
            if let display, ["all", "display"].contains(options.scope) { filters.append(("display", SCContentFilter(display: display, excludingWindows: []))) }
            if options.captureApplication && ["all", "application"].contains(options.scope) {
                if let display, let application = scTarget?.owningApplication {
                    // An empty exceptingWindows list keeps every window belonging to
                    // this application included; passing the target window here would exclude it.
                    filters.append(("application", SCContentFilter(display: display, including: [application], exceptingWindows: [])))
                    report["applicationFilter"] = ["processID": application.processID, "bundleIdentifier": application.bundleIdentifier, "displayID": display.displayID, "exceptingWindows": []] as [String: Any]
                } else { report["stream_application"] = ["status": "skipped", "reason": "Target owning application or display unavailable"] }
            }
            for (name, filter) in filters {
                let config = SCStreamConfiguration()
                if #available(macOS 14.0, *) {
                    config.width = max(2, Int((filter.contentRect.width * CGFloat(filter.pointPixelScale)).rounded()))
                    config.height = max(2, Int((filter.contentRect.height * CGFloat(filter.pointPixelScale)).rounded()))
                } else if name == "window", let scTarget {
                    config.width = max(2, Int(scTarget.frame.width * 2)); config.height = max(2, Int(scTarget.frame.height * 2))
                } else if let display { config.width = display.width; config.height = display.height }
                config.showsCursor = !args.contains("--omit-cursor"); config.capturesAudio = false
                config.pixelFormat = kCVPixelFormatType_32BGRA
                config.minimumFrameInterval = CMTime(value: 1, timescale: 10)
                config.queueDepth = 3
                if (only == "all" || only == "screenshot") && name != "application" {
                    if #available(macOS 14.0, *) {
                        do {
                            let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
                            let file = "sck-screenshot-\(name).png"
                            try savePNG(image, to: out.appendingPathComponent(file))
                            report["screenshot_\(name)"] = ["status": "saved", "file": file, "width": image.width, "height": image.height]
                        } catch { report["screenshot_\(name)"] = errorJSON(error) }
                    } else { report["screenshot_\(name)"] = ["status": "unavailable", "requires": "macOS 14.0"] }
                }
                if only == "all" || only == "stream" {
                    let directory = out.appendingPathComponent("sck-stream-\(name)", isDirectory: true)
                    let duration = options.duration
                    let exerciseUpdate = args.contains("--exercise-filter-update")
                    report["configuration_\(name)"] = ["width": config.width, "height": config.height, "showsCursor": config.showsCursor, "pixelFormat": config.pixelFormat, "queueDepth": config.queueDepth, "requestedFPS": 10] as [String: Any]
                    report["stream_\(name)"] = await runStream(filter: filter, configuration: config, directory: directory, duration: duration, exerciseUpdate: exerciseUpdate)
                    if exerciseUpdate {
                        let recreated = out.appendingPathComponent("sck-stream-\(name)-recreated", isDirectory: true)
                        report["stream_\(name)_recreated"] = await runStream(filter: filter, configuration: config, directory: recreated, duration: duration, exerciseUpdate: false, initialPhase: "recreated")
                    }
                }
            }
        }
        finish()
    }
}
