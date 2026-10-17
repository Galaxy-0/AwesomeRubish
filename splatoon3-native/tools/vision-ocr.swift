// Local screenshot text recognition for the Mac integration gates.
import Foundation
import Vision
for path in CommandLine.arguments.dropFirst() {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["en-US"]
    request.usesLanguageCorrection = false
    do {
        try VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:]).perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        let data = try JSONSerialization.data(withJSONObject: ["path": path, "lines": lines], options: [.sortedKeys])
        print(String(data: data, encoding: .utf8)!)
        fflush(stdout)
    } catch {
        fputs("OCR failed: \(path): \(error)\n", stderr)
        exit(1)
    }
}
