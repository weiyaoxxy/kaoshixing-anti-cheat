<!--
{
  "availability" : [
    "iOS: 27.0.0 -",
    "iPadOS: 27.0.0 -",
    "macCatalyst: 18.2.0 -",
    "macOS: 14.0.0 -",
    "tvOS: 27.0.0 -",
    "visionOS: 27.0.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "ScreenCaptureKit",
  "identifier" : "/documentation/ScreenCaptureKit/SCContentSharingPicker",
  "metadataVersion" : "0.1.0",
  "role" : "Class",
  "symbol" : {
    "kind" : "Class",
    "modules" : [
      "ScreenCaptureKit"
    ],
    "preciseIdentifier" : "c:objc(cs)SCContentSharingPicker"
  },
  "title" : "SCContentSharingPicker"
}
-->

# SCContentSharingPicker

An instance of a picker presented by the operating system for managing frame-capture streams.

```
class SCContentSharingPicker
```

## Overview> Important:
> Avoid creating your own sharing picker. Use the picker provided by the ``doc://com.apple.screencapturekit/documentation/ScreenCaptureKit/SCContentSharingPicker/shared`` static property.

## Topics

### Shared system picker

[`class var shared: SCContentSharingPicker`](/documentation/ScreenCaptureKit/SCContentSharingPicker/shared)

The system-provided picker UI instance for capturing display and audio content from someone’s Mac.

### Picker availability

[`var isActive: Bool`](/documentation/ScreenCaptureKit/SCContentSharingPicker/isActive)

A Boolean value that indicates if the picker is active.

### Stream configuration

[`func setConfiguration(SCContentSharingPickerConfiguration?, for: SCStream)`](/documentation/ScreenCaptureKit/SCContentSharingPicker/setConfiguration(_:for:))

Sets the configuration for the content capture picker for a capture stream, providing allowed selection modes and content excluded from selection.

[`var configuration: SCContentSharingPickerConfiguration?`](/documentation/ScreenCaptureKit/SCContentSharingPicker/configuration)

Sets the configuration for the content capture picker for all streams, providing allowed selection modes and content excluded from selection.

[`var defaultConfiguration: SCContentSharingPickerConfiguration`](/documentation/ScreenCaptureKit/SCContentSharingPicker/defaultConfiguration-94q2b)

The default configuration to use for the content capture picker.

[`var maximumStreamCount: Int?`](/documentation/ScreenCaptureKit/SCContentSharingPicker/maximumStreamCount-2kuaa)

The maximum number of streams the content capture picker allows.

[`- (void) setConfiguration:(SCContentSharingPickerConfiguration *) pickerConfig forStream:(SCStream *) stream;`](/documentation/ScreenCaptureKit/SCContentSharingPicker/setConfiguration:forStream:)

Sets the configuration for the content capture picker for a capture stream, providing allowed selection modes and content excluded from selection.

[`@property (nonatomic, copy) SCContentSharingPickerConfiguration * defaultConfiguration;`](/documentation/ScreenCaptureKit/SCContentSharingPicker/defaultConfiguration-9v5sa)

The default configuration to use for the content capture picker.

[`@property (nonatomic, strong, nullable) NSNumber * maximumStreamCount;`](/documentation/ScreenCaptureKit/SCContentSharingPicker/maximumStreamCount-66khx)

The maximum number of streams the content capture picker allows.

### Manage observers

[`func add(any SCContentSharingPickerObserver)`](/documentation/ScreenCaptureKit/SCContentSharingPicker/add(_:))

Adds an observer instance to notify of changes in the content-sharing picker.

[`func remove(any SCContentSharingPickerObserver)`](/documentation/ScreenCaptureKit/SCContentSharingPicker/remove(_:))

Removes an observer instance from the content-sharing picker.

### Picker display

[`func present()`](/documentation/ScreenCaptureKit/SCContentSharingPicker/present())

Displays the picker with no active selection for capture.

[`func present(for: SCStream)`](/documentation/ScreenCaptureKit/SCContentSharingPicker/present(for:))

Displays the picker with an already running capture stream.

[`func present(using: SCShareableContentStyle)`](/documentation/ScreenCaptureKit/SCContentSharingPicker/present(using:))

Displays the picker for a single type of capture selection.

[`func present(for: SCStream, using: SCShareableContentStyle)`](/documentation/ScreenCaptureKit/SCContentSharingPicker/present(for:using:))

Displays the picker with an existing capture stream, allowing for a single type of capture selection.

### Instance Properties

[`var isAvailable: Bool`](/documentation/ScreenCaptureKit/SCContentSharingPicker/isAvailable)

### Instance Methods

[`func presentForCurrentApplication()`](/documentation/ScreenCaptureKit/SCContentSharingPicker/presentForCurrentApplication())

## Relationships

### Conforms To

[`CVarArg`](/documentation/Swift/CVarArg)

[`Equatable`](/documentation/Swift/Equatable)

[`NSObjectProtocol`](/documentation/ObjectiveC/NSObjectProtocol)

[`CustomDebugStringConvertible`](/documentation/Swift/CustomDebugStringConvertible)

[`CustomStringConvertible`](/documentation/Swift/CustomStringConvertible)

[`Hashable`](/documentation/Swift/Hashable)

### Inherits From

[`NSObject-swift.class`](/documentation/ObjectiveC/NSObject-swift.class)

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)