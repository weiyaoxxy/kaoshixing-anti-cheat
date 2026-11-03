<!--
{
  "availability" : [
    "iOS: -",
    "iPadOS: -",
    "macCatalyst: 18.2.0 -",
    "macOS: 12.3.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "ScreenCaptureKit",
  "identifier" : "/documentation/ScreenCaptureKit/SCShareableContent",
  "metadataVersion" : "0.1.0",
  "role" : "Class",
  "symbol" : {
    "kind" : "Class",
    "modules" : [
      "ScreenCaptureKit"
    ],
    "preciseIdentifier" : "c:objc(cs)SCShareableContent"
  },
  "title" : "SCShareableContent"
}
-->

# SCShareableContent

An instance that represents a set of displays, apps, and windows that your app can capture.

```
class SCShareableContent
```

## Overview

Use the [`displays`](/documentation/ScreenCaptureKit/SCShareableContent/displays), [`windows`](/documentation/ScreenCaptureKit/SCShareableContent/windows), and [`applications`](/documentation/ScreenCaptureKit/SCShareableContent/applications) properties to create a [`SCContentFilter`](/documentation/ScreenCaptureKit/SCContentFilter) object that specifies what display content to capture. You apply the filter to an instance of [`SCStream`](/documentation/ScreenCaptureKit/SCStream) to limit its output to only the content matching your filter.

## Topics

### Retrieving shareable content

[`class func getWithCompletionHandler((SCShareableContent?, (any Error)?) -> Void)`](/documentation/ScreenCaptureKit/SCShareableContent/getWithCompletionHandler(_:))

Retrieves the displays, apps, and windows that your app can capture.

[`class func getExcludingDesktopWindows(Bool, onScreenWindowsOnly: Bool, completionHandler: (SCShareableContent?, (any Error)?) -> Void)`](/documentation/ScreenCaptureKit/SCShareableContent/getExcludingDesktopWindows(_:onScreenWindowsOnly:completionHandler:))

Retrieves the displays, apps, and windows that match your criteria.

[`class func getExcludingDesktopWindows(Bool, onScreenWindowsOnlyAbove: SCWindow, completionHandler: (SCShareableContent?, (any Error)?) -> Void)`](/documentation/ScreenCaptureKit/SCShareableContent/getExcludingDesktopWindows(_:onScreenWindowsOnlyAbove:completionHandler:))

Retrieves the displays, apps, and windows that are in front of the specified window.

[`class func getExcludingDesktopWindows(Bool, onScreenWindowsOnlyBelow: SCWindow, completionHandler: (SCShareableContent?, (any Error)?) -> Void)`](/documentation/ScreenCaptureKit/SCShareableContent/getExcludingDesktopWindows(_:onScreenWindowsOnlyBelow:completionHandler:))

Retrieves the displays, apps, and windows that are behind the specified window.

[`class func info(for: SCContentFilter) -> SCShareableContentInfo`](/documentation/ScreenCaptureKit/SCShareableContent/info(for:))

Retrieves any available sharable content information that matches the provided filter.

### Inspecting shareable content

[`var windows: [SCWindow]`](/documentation/ScreenCaptureKit/SCShareableContent/windows)

The windows available for capture.

[`var displays: [SCDisplay]`](/documentation/ScreenCaptureKit/SCShareableContent/displays)

The displays available for capture.

[`var applications: [SCRunningApplication]`](/documentation/ScreenCaptureKit/SCShareableContent/applications)

The apps available for capture.

### Type Methods

[`class func getCurrentProcessShareableContent(completionHandler: (SCShareableContent?, (any Error)?) -> Void)`](/documentation/ScreenCaptureKit/SCShareableContent/getCurrentProcessShareableContent(completionHandler:))

## Relationships

### Inherits From

[`NSObject-swift.class`](/documentation/ObjectiveC/NSObject-swift.class)

### Conforms To

[`CustomStringConvertible`](/documentation/Swift/CustomStringConvertible)

[`Hashable`](/documentation/Swift/Hashable)

[`Equatable`](/documentation/Swift/Equatable)

[`CustomDebugStringConvertible`](/documentation/Swift/CustomDebugStringConvertible)

[`NSObjectProtocol`](/documentation/ObjectiveC/NSObjectProtocol)

[`CVarArg`](/documentation/Swift/CVarArg)

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)