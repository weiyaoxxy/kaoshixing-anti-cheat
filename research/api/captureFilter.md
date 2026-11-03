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
  "identifier" : "/documentation/ScreenCaptureKit/SCContentFilter",
  "metadataVersion" : "0.1.0",
  "role" : "Class",
  "symbol" : {
    "kind" : "Class",
    "modules" : [
      "ScreenCaptureKit"
    ],
    "preciseIdentifier" : "c:objc(cs)SCContentFilter"
  },
  "title" : "SCContentFilter"
}
-->

# SCContentFilter

An instance that filters the content a stream captures.

```
class SCContentFilter
```

## Overview

Use a content filter to limit an [`SCStream`](/documentation/ScreenCaptureKit/SCStream) object’s output to only that matching your filter criteria. Retrieve the displays, apps, and windows that your app can capture from an instance of [`SCShareableContent`](/documentation/ScreenCaptureKit/SCShareableContent).

## Topics

### Creating a filter

[`init(desktopIndependentWindow: SCWindow)`](/documentation/ScreenCaptureKit/SCContentFilter/init(desktopIndependentWindow:))

Creates a filter that captures only the specified window.

[`init(display: SCDisplay, including: [SCWindow])`](/documentation/ScreenCaptureKit/SCContentFilter/init(display:including:))

Creates a filter that captures only specific windows from a display.

[`init(display: SCDisplay, excludingWindows: [SCWindow])`](/documentation/ScreenCaptureKit/SCContentFilter/init(display:excludingWindows:))

Creates a filter that captures the contents of a display, excluding the specified windows.

[`init(display: SCDisplay, including: [SCRunningApplication], exceptingWindows: [SCWindow])`](/documentation/ScreenCaptureKit/SCContentFilter/init(display:including:exceptingWindows:))

Creates a filter that captures a display, including only windows of the specified apps.

[`init(display: SCDisplay, excludingApplications: [SCRunningApplication], exceptingWindows: [SCWindow])`](/documentation/ScreenCaptureKit/SCContentFilter/init(display:excludingApplications:exceptingWindows:))

Creates a filter that captures a display, excluding windows of the specified apps.

### Filter properties

[`var contentRect: CGRect`](/documentation/ScreenCaptureKit/SCContentFilter/contentRect)

The size and location of the content to filter, in screen points.

[`var pointPixelScale: Float`](/documentation/ScreenCaptureKit/SCContentFilter/pointPixelScale)

The scaling factor used to translate screen points into pixels.

[`var streamType: SCStreamType`](/documentation/ScreenCaptureKit/SCContentFilter/streamType)

The type of the streaming content.

[`enum SCStreamType`](/documentation/ScreenCaptureKit/SCStreamType)

The display type of the presented stream.

[`var style: SCShareableContentStyle`](/documentation/ScreenCaptureKit/SCContentFilter/style)

The display style of the sharable content.

### Initializers

[`init(display: SCDisplay, includingApplications: [SCRunningApplication], exceptingWindows: [SCWindow])`](/documentation/ScreenCaptureKit/SCContentFilter/init(display:includingApplications:exceptingWindows:))

[`init(display: SCDisplay, includingWindows: [SCWindow])`](/documentation/ScreenCaptureKit/SCContentFilter/init(display:includingWindows:))

### Instance Properties

[`var includeMenuBar: Bool`](/documentation/ScreenCaptureKit/SCContentFilter/includeMenuBar)

[`var includedApplications: [SCRunningApplication]`](/documentation/ScreenCaptureKit/SCContentFilter/includedApplications)

[`var includedDisplays: [SCDisplay]`](/documentation/ScreenCaptureKit/SCContentFilter/includedDisplays)

[`var includedWindows: [SCWindow]`](/documentation/ScreenCaptureKit/SCContentFilter/includedWindows)

[`var isCameraEnabled: Bool`](/documentation/ScreenCaptureKit/SCContentFilter/isCameraEnabled)

[`var isMicrophoneEnabled: Bool`](/documentation/ScreenCaptureKit/SCContentFilter/isMicrophoneEnabled)

## Relationships

### Conforms To

[`CustomDebugStringConvertible`](/documentation/Swift/CustomDebugStringConvertible)

[`Hashable`](/documentation/Swift/Hashable)

[`NSObjectProtocol`](/documentation/ObjectiveC/NSObjectProtocol)

[`CVarArg`](/documentation/Swift/CVarArg)

[`CustomStringConvertible`](/documentation/Swift/CustomStringConvertible)

[`Equatable`](/documentation/Swift/Equatable)

### Inherits From

[`NSObject-swift.class`](/documentation/ObjectiveC/NSObject-swift.class)

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)