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
func rectJSON(_ r: CGRect) -> [String: Double] { ["x": r.origin.x, "y": r.origin.y, "width": r.width, "height": r.height] }
func errorJSON(_ e: Error) -> [String: Any] {
    let n = e as NSError
    return ["status": "error", "domain": n.domain, "code": n.code, "message": n.localizedDescription]
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
        func value(_ key: String) -> String? { guard let i = args.firstIndex(of: key), i + 1 < args.count else { return nil }; return args[i+1] }
        if args.contains("--help") {
            print("CaptureProbe [--permission] [--request-permission] [--list] [--window-id ID | --target-name ExamCaptureDemo] [--output DIR] [--duration 2] [--only cg|screenshot|stream|all] [--exercise-filter-update]")
            return
        }
        let fm = FileManager.default
        let out = URL(fileURLWithPath: value("--output") ?? "artifacts/probe-\(Int(Date().timeIntervalSince1970))", isDirectory: true)
        var report: [String: Any] = [
            "startedAt": ISO8601DateFormatter().string(from: Date()),
            "processID": ProcessInfo.processInfo.processIdentifier,
            "operatingSystem": ProcessInfo.processInfo.operatingSystemVersionString,
            "arguments": args,
            "permissionBefore": CGPreflightScreenCaptureAccess(),
            "interpretation": "Images and frame status are observations only. Black/empty/missing output alone does not prove protection; compare an unprotected control and verify visible content independently."
        ]
        func finish() {
            report["finishedAt"] = ISO8601DateFormatter().string(from: Date())
            do {
                try fm.createDirectory(at: out, withIntermediateDirectories: true)
                let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys, .fragmentsAllowed])
                try data.write(to: out.appendingPathComponent("report.json"))
                print(String(decoding: data, as: UTF8.self)); print("Report: \(out.path)/report.json")
            } catch { fputs("Report write error: \(error)\n", stderr) }
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
        let only = value("--only") ?? "all"
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
            report["coreGraphics"] = cg
        }
        if scTarget == nil && only != "cg" {
            let skipped: [String: Any] = ["status": "skipped", "reason": "Target SCWindow unavailable; no window content filter could be created. Missing output is not evidence of protection."]
            if only == "all" || only == "screenshot" { report["screenshot_window"] = skipped }
            if only == "all" || only == "stream" { report["stream_window"] = skipped }
        }
        if let content {
            var filters: [(String, SCContentFilter)] = []
            if let scTarget { filters.append(("window", SCContentFilter(desktopIndependentWindow: scTarget))) }
            let display = content.displays.first(where: { d in scTarget.map { d.frame.intersects($0.frame) } ?? (d.displayID == CGMainDisplayID()) }) ?? content.displays.first
            if let display { filters.append(("display", SCContentFilter(display: display, excludingWindows: []))) }
            for (name, filter) in filters {
                let config = SCStreamConfiguration()
                if #available(macOS 14.0, *) {
                    config.width = max(2, Int((filter.contentRect.width * CGFloat(filter.pointPixelScale)).rounded()))
                    config.height = max(2, Int((filter.contentRect.height * CGFloat(filter.pointPixelScale)).rounded()))
                } else if name == "window", let scTarget {
                    config.width = max(2, Int(scTarget.frame.width * 2)); config.height = max(2, Int(scTarget.frame.height * 2))
                } else if let display { config.width = display.width; config.height = display.height }
                config.showsCursor = true; config.capturesAudio = false
                config.pixelFormat = kCVPixelFormatType_32BGRA
                config.minimumFrameInterval = CMTime(value: 1, timescale: 10)
                config.queueDepth = 3
                if only == "all" || only == "screenshot" {
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
                    let duration = min(30.0, max(0.5, Double(value("--duration") ?? "2") ?? 2))
                    let exerciseUpdate = args.contains("--exercise-filter-update")
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
