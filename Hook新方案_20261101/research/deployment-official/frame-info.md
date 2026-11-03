<!--
{
  "availability" : [
    "iOS: 27.0.0 -",
    "iPadOS: 27.0.0 -",
    "macCatalyst: 18.2.0 -",
    "macOS: 12.3.0 -",
    "tvOS: 27.0.0 -",
    "visionOS: 27.0.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "ScreenCaptureKit",
  "identifier" : "/documentation/ScreenCaptureKit/SCStreamFrameInfo",
  "metadataVersion" : "0.1.0",
  "role" : "Structure",
  "symbol" : {
    "kind" : "Structure",
    "modules" : [
      "ScreenCaptureKit"
    ],
    "preciseIdentifier" : "c:@T@SCStreamFrameInfo"
  },
  "title" : "SCStreamFrameInfo"
}
-->

# SCStreamFrameInfo

An instance that defines metadata keys for a stream frame.

```
struct SCStreamFrameInfo
```

## Overview

Use [`SCStreamFrameInfo`](/documentation/ScreenCaptureKit/SCStreamFrameInfo) keys to retrieve values from the dictionary of metadata attached to the sample buffers that a stream produces. For example, you can retrieve the display time, content scale, and scaling factor, as shown below:

```swift
// A dictionary of attachments for a streamed sample buffer.
let attachments: [SCStreamFrameInfo: Any] = // Retrieve attachments from a sample buffer.

let displayTime = attachments[.displayTime] as? UInt64 ?? 0
let contentScale = attachments[.contentScale] as? Double ?? 0.0
let scaleFactor = attachments[.scaleFactor] as? Double ?? 0.0
```

## Topics

### Frame information constants

[`static let status: SCStreamFrameInfo`](/documentation/ScreenCaptureKit/SCStreamFrameInfo/status)

A key to retrieve the status of a video frame.

[`static let displayTime: SCStreamFrameInfo`](/documentation/ScreenCaptureKit/SCStreamFrameInfo/displayTime)

A key to retrieve the display time of a video frame.

[`static let scaleFactor: SCStreamFrameInfo`](/documentation/ScreenCaptureKit/SCStreamFrameInfo/scaleFactor)

A key to retrieve the scale factor of a video frame.

[`static let contentScale: SCStreamFrameInfo`](/documentation/ScreenCaptureKit/SCStreamFrameInfo/contentScale)

A key to retrieve the content scale of a video frame.

[`static let contentRect: SCStreamFrameInfo`](/documentation/ScreenCaptureKit/SCStreamFrameInfo/contentRect)

A key to retrieve the content rectangle of a video frame.

[`static let boundingRect: SCStreamFrameInfo`](/documentation/ScreenCaptureKit/SCStreamFrameInfo/boundingRect)

A key to retrieve the bounding rectangle for a video frame.

[`static let screenRect: SCStreamFrameInfo`](/documentation/ScreenCaptureKit/SCStreamFrameInfo/screenRect)

A key to retrieve the onscreen location of captured content.

[`static let dirtyRects: SCStreamFrameInfo`](/documentation/ScreenCaptureKit/SCStreamFrameInfo/dirtyRects)

A key to retrieve the areas of a video frame that contain changes.

[`static let presenterOverlayContentRect: SCStreamFrameInfo`](/documentation/ScreenCaptureKit/SCStreamFrameInfo/presenterOverlayContentRect)

### Initializers

[`init(rawValue: String)`](/documentation/ScreenCaptureKit/SCStreamFrameInfo/init(rawValue:))

Creates a new instance with a raw value.

### Type Properties

[`static let videoOrientation: SCStreamFrameInfo`](/documentation/ScreenCaptureKit/SCStreamFrameInfo/videoOrientation)

## Relationships

### Conforms To

[`Equatable`](/documentation/Swift/Equatable)

[`Hashable`](/documentation/Swift/Hashable)

[`SendableMetatype`](/documentation/Swift/SendableMetatype)

[`Sendable`](/documentation/Swift/Sendable)

[`RawRepresentable`](/documentation/Swift/RawRepresentable)

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)