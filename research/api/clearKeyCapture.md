<!--
{
  "availability" : [
    "iOS: 26.4.0 -",
    "iPadOS: 26.4.0 -",
    "macCatalyst: 26.4.0 -",
    "macOS: 26.4.0 -",
    "tvOS: 26.4.0 -",
    "visionOS: 26.4.0 -",
    "watchOS: 26.4.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "AVFoundation",
  "identifier" : "/documentation/AVFoundation/AVPlayer/allowsCaptureOfClearKeyVideo",
  "metadataVersion" : "0.1.0",
  "role" : "Instance Property",
  "symbol" : {
    "kind" : "Instance Property",
    "modules" : [
      "AVFoundation"
    ],
    "preciseIdentifier" : "c:objc(cs)AVPlayer(py)allowsCaptureOfClearKeyVideo"
  },
  "title" : "allowsCaptureOfClearKeyVideo"
}
-->

# allowsCaptureOfClearKeyVideo

Indicates whether the video output of ClearKey Encrypted Video can be captured

```
nonisolated var allowsCaptureOfClearKeyVideo: Bool { get set }
```

## Discussion

When set to YES, and the video being played by AVPlayer is Clear Key encrypted, allows video to be captured in screenshots and screen recordings, and via APIs like AVPlayerItemVideoOutput and ScreenCaptureKit. When NO, Clear Key encrypted video will not be included in such captured video. This property has no effect on content protected by FairPlay Streaming.
Default is NO.

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)