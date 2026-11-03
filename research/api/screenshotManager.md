<!--
{
  "availability" : [
    "iOS: -",
    "iPadOS: -",
    "macCatalyst: 18.2.0 -",
    "macOS: 14.0.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "ScreenCaptureKit",
  "identifier" : "/documentation/ScreenCaptureKit/SCScreenshotManager",
  "metadataVersion" : "0.1.0",
  "role" : "Class",
  "symbol" : {
    "kind" : "Class",
    "modules" : [
      "ScreenCaptureKit"
    ],
    "preciseIdentifier" : "c:objc(cs)SCScreenshotManager"
  },
  "title" : "SCScreenshotManager"
}
-->

# SCScreenshotManager

An instance for the capture of single frames from a stream.

```
class SCScreenshotManager
```

## Topics

### Individual frame capture

[`class func captureImage(contentFilter: SCContentFilter, configuration: SCStreamConfiguration, completionHandler: ((CGImage?, (any Error)?) -> Void)?)`](/documentation/ScreenCaptureKit/SCScreenshotManager/captureImage(contentFilter:configuration:completionHandler:))

Captures a single frame from a stream as an image, using a filter.

[`class func captureSampleBuffer(contentFilter: SCContentFilter, configuration: SCStreamConfiguration, completionHandler: ((CMSampleBuffer?, (any Error)?) -> Void)?)`](/documentation/ScreenCaptureKit/SCScreenshotManager/captureSampleBuffer(contentFilter:configuration:completionHandler:))

Captures a single frame directly from a stream’s buffer, using a filter.

### Type Methods

[`class func captureImage(in: CGRect, completionHandler: ((CGImage?, (any Error)?) -> Void)?)`](/documentation/ScreenCaptureKit/SCScreenshotManager/captureImage(in:completionHandler:))

[`class func captureScreenshot(contentFilter: SCContentFilter, configuration: SCScreenshotConfiguration, completionHandler: ((SCScreenshotOutput?, (any Error)?) -> Void)?)`](/documentation/ScreenCaptureKit/SCScreenshotManager/captureScreenshot(contentFilter:configuration:completionHandler:))

[`class func captureScreenshot(rect: CGRect, configuration: SCScreenshotConfiguration, completionHandler: ((SCScreenshotOutput?, (any Error)?) -> Void)?)`](/documentation/ScreenCaptureKit/SCScreenshotManager/captureScreenshot(rect:configuration:completionHandler:))

## Relationships

### Conforms To

[`CVarArg`](/documentation/Swift/CVarArg)

[`Equatable`](/documentation/Swift/Equatable)

[`NSObjectProtocol`](/documentation/ObjectiveC/NSObjectProtocol)

[`CustomStringConvertible`](/documentation/Swift/CustomStringConvertible)

[`CustomDebugStringConvertible`](/documentation/Swift/CustomDebugStringConvertible)

[`Hashable`](/documentation/Swift/Hashable)

### Inherits From

[`NSObject-swift.class`](/documentation/ObjectiveC/NSObject-swift.class)

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)