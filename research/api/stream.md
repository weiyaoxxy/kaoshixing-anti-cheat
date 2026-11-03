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
  "identifier" : "/documentation/ScreenCaptureKit/SCStream",
  "metadataVersion" : "0.1.0",
  "role" : "Class",
  "symbol" : {
    "kind" : "Class",
    "modules" : [
      "ScreenCaptureKit"
    ],
    "preciseIdentifier" : "c:objc(cs)SCStream"
  },
  "title" : "SCStream"
}
-->

# SCStream

An instance that represents a stream of shareable content.

```
class SCStream
```

## Overview

Use a stream to capture video of screen content like apps and windows. Create a content stream by passing it an instance of [`SCContentFilter`](/documentation/ScreenCaptureKit/SCContentFilter) and an [`SCStreamConfiguration`](/documentation/ScreenCaptureKit/SCStreamConfiguration) object. The stream uses the filter to determine which screen content to capture, and uses the configuration data to configure the output.

## Topics

### Creating a stream

[`init(filter: SCContentFilter, configuration: SCStreamConfiguration, delegate: (any SCStreamDelegate)?)`](/documentation/ScreenCaptureKit/SCStream/init(filter:configuration:delegate:))

Creates a stream with a content filter and configuration.

### Updating stream configuration

[`func updateConfiguration(SCStreamConfiguration, completionHandler: (((any Error)?) -> Void)?)`](/documentation/ScreenCaptureKit/SCStream/updateConfiguration(_:completionHandler:))

Updates the stream with a new configuration.

[`func updateContentFilter(SCContentFilter, completionHandler: (((any Error)?) -> Void)?)`](/documentation/ScreenCaptureKit/SCStream/updateContentFilter(_:completionHandler:))

Updates the stream by applying a new content filter.

### Adding and removing stream output

[`func addStreamOutput(any SCStreamOutput, type: SCStreamOutputType, sampleHandlerQueue: dispatch_queue_t?) throws`](/documentation/ScreenCaptureKit/SCStream/addStreamOutput(_:type:sampleHandlerQueue:))

Adds a destination that receives the stream output.

[`func removeStreamOutput(any SCStreamOutput, type: SCStreamOutputType) throws`](/documentation/ScreenCaptureKit/SCStream/removeStreamOutput(_:type:))

Removes a destination from receiving stream output.

### Adding and removing recording output

[`func addRecordingOutput(SCRecordingOutput) throws`](/documentation/ScreenCaptureKit/SCStream/addRecordingOutput(_:))

[`func removeRecordingOutput(SCRecordingOutput) throws`](/documentation/ScreenCaptureKit/SCStream/removeRecordingOutput(_:))

[`class SCRecordingOutput`](/documentation/ScreenCaptureKit/SCRecordingOutput)

### Starting and stopping a stream

[`func startCapture(completionHandler: (((any Error)?) -> Void)?)`](/documentation/ScreenCaptureKit/SCStream/startCapture(completionHandler:))

Starts the stream with a callback to indicate whether it successfully starts.

[`func stopCapture(completionHandler: (((any Error)?) -> Void)?)`](/documentation/ScreenCaptureKit/SCStream/stopCapture(completionHandler:))

Stops the stream.

### Stream synchronization

[`var synchronizationClock: CMClock?`](/documentation/ScreenCaptureKit/SCStream/synchronizationClock)

A clock to use for output synchronization.

### Instance Properties

[`var isCapturing: Bool`](/documentation/ScreenCaptureKit/SCStream/isCapturing)

### Instance Methods

[`func addClipBufferingOutput(SCClipBufferingOutput) throws`](/documentation/ScreenCaptureKit/SCStream/addClipBufferingOutput(_:))

[`func addVideoEffectOutput(SCVideoEffectOutput) throws`](/documentation/ScreenCaptureKit/SCStream/addVideoEffectOutput(_:))

[`func removeClipBufferingOutput(SCClipBufferingOutput) throws`](/documentation/ScreenCaptureKit/SCStream/removeClipBufferingOutput(_:))

[`func removeVideoEffectOutput(SCVideoEffectOutput) throws`](/documentation/ScreenCaptureKit/SCStream/removeVideoEffectOutput(_:))

## Relationships

### Conforms To

[`Hashable`](/documentation/Swift/Hashable)

[`CVarArg`](/documentation/Swift/CVarArg)

[`CustomStringConvertible`](/documentation/Swift/CustomStringConvertible)

[`CustomDebugStringConvertible`](/documentation/Swift/CustomDebugStringConvertible)

[`NSObjectProtocol`](/documentation/ObjectiveC/NSObjectProtocol)

[`Equatable`](/documentation/Swift/Equatable)

### Inherits From

[`NSObject-swift.class`](/documentation/ObjectiveC/NSObject-swift.class)

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)