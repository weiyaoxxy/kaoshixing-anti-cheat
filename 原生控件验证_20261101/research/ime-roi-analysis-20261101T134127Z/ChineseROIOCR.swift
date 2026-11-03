import Foundation
import Vision
import ImageIO
for path in CommandLine.arguments.dropFirst() {
    var output: [String: Any] = ["path":path, "recognitionLanguages":["zh-Hans"], "recognitionLevel":"accurate", "usesLanguageCorrection":false]
    do {
        guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath:path) as CFURL,nil), let image = CGImageSourceCreateImageAtIndex(source,0,nil) else { throw NSError(domain:"PNGDecode",code:1) }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hans"]
        request.usesLanguageCorrection = false
        output["revision"] = request.revision
        output["supportedLanguages"] = try request.supportedRecognitionLanguages()
        try VNImageRequestHandler(cgImage:image).perform([request])
        output["lines"] = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        output["observations"] = (request.results ?? []).compactMap { o -> [String:Any]? in
            guard let c=o.topCandidates(1).first else { return nil }
            return ["text":c.string,"confidence":c.confidence,"box":[o.boundingBox.minX,o.boundingBox.minY,o.boundingBox.width,o.boundingBox.height]]
        }
    } catch { output["error"] = error.localizedDescription }
    let data = try JSONSerialization.data(withJSONObject:output,options:[.sortedKeys])
    print(String(decoding:data,as:UTF8.self))
}
