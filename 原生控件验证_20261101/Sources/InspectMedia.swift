import Foundation
import AppKit
import AVFoundation
import Vision
import ImageIO

// Decodes a representative MP4 frame and OCRs actual PNG pixels, independent of Demo metadata.
var paths = Array(CommandLine.arguments.dropFirst())
var sampleTime: Double = 1
if let i = paths.firstIndex(of: "--time"), i + 1 < paths.count {
    sampleTime = Double(paths[i + 1]) ?? 1
    paths.removeSubrange(i...i+1)
}
for path in paths {
    var row: [String: Any] = ["path": path]
    do {
        let url = URL(fileURLWithPath: path)
        let image: CGImage
        if ["mp4", "mov"].contains(url.pathExtension.lowercased()) {
            let asset = AVURLAsset(url: url)
            let generator = AVAssetImageGenerator(asset: asset)
            generator.appliesPreferredTrackTransform = true
            let seconds = sampleTime < 0 ? max(0, CMTimeGetSeconds(asset.duration) + sampleTime) : sampleTime
            var actualTime = CMTime.invalid
            image = try generator.copyCGImage(at: CMTime(seconds: seconds, preferredTimescale: 600), actualTime: &actualTime)
            if CMTimeGetSeconds(actualTime).isFinite { row["actualSampleTimeSeconds"] = CMTimeGetSeconds(actualTime) }
            row["sampleTimeSeconds"] = seconds
            row["durationSeconds"] = CMTimeGetSeconds(asset.duration)
            let png = url.deletingPathExtension().appendingPathExtension("decoded.png")
            try NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:])?.write(to: png)
            row["decodedPNG"] = png.path
        } else {
            guard let source = CGImageSourceCreateWithURL(url as CFURL, nil), let decoded = CGImageSourceCreateImageAtIndex(source, 0, nil) else { throw NSError(domain: "Decode", code: 1) }
            image = decoded
        }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["en-US", "zh-Hans"]
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: image).perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        row["width"] = image.width; row["height"] = image.height; row["lines"] = lines
        row["textObservationCoordinateSpace"] = "Vision normalized image coordinates, bottom-left origin"
        row["textObservations"] = (request.results ?? []).compactMap { observation -> [String: Any]? in
            guard let candidate = observation.topCandidates(1).first else { return nil }
            let box = observation.boundingBox
            return ["text": candidate.string, "confidence": candidate.confidence,
                "boundingBox": ["x": box.origin.x, "y": box.origin.y, "width": box.width, "height": box.height]]
        }
        let all = lines.joined(separator: " ")
        row["secretDetected"] = all.contains("EXAM-SECRET") || all.contains("7K9Q")
        row["publicDetected"] = all.contains("PUBLIC-CONTROL") || all.contains("4M2P")
        row["nativeLeakDetected"] = all.contains("NATIVE-LEAK") || all.contains("8R3T")
    } catch { row["error"] = error.localizedDescription }
    let data = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
}
