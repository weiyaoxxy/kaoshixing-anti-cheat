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
  "identifier" : "/documentation/ScreenCaptureKit",
  "metadataVersion" : "0.1.0",
  "role" : "Framework",
  "symbol" : {
    "kind" : "Framework",
    "modules" : [
      "ScreenCaptureKit"
    ],
    "preciseIdentifier" : "ScreenCaptureKit"
  },
  "title" : "ScreenCaptureKit"
}
-->

# ScreenCaptureKit

Stream screen content and audio to your app with fine-grained control over what you capture.

## Overview

Use ScreenCaptureKit to capture high-performance video and audio across iOS, iPadOS, macOS, tvOS, and visionOS. The framework gives you fine-grained control to select and stream only the content you want to capture, delivering media to your app as <doc://com.apple.documentation/documentation/CoreMedia/CMSampleBuffer> objects with the associated metadata.

> Important: ScreenCaptureKit replaces ReplayKit for screen streaming and mirroring. A broadcast extension is no longer necessary.

Use [`SCContentSharingPicker`](/documentation/ScreenCaptureKit/SCContentSharingPicker), the system screen-sharing control, as the recommended approach for letting people select content sources and manage active streams, rather than building your own selection UI. To capture content while your app is in the background, configure the appropriate <doc://com.apple.documentation/documentation/Xcode/configuring-background-execution-modes> in the Signing & Capabilities pane in Xcode.

Request screen recording permission from the person before capturing content. In the Info pane of the Xcode target editor, add a `NSScreenCaptureUsageDescription` key with a description of why your app requires screen recording access.

> Note: For related WWDC sessions, see [Meet ScreenCaptureKit](https://developer.apple.com/wwdc22/10156) (WWDC22 Session 10156), [Take ScreenCaptureKit to the next level](https://developer.apple.com/wwdc22/10155) (WWDC22 Session 10155), and [What’s new in ScreenCaptureKit](https://developer.apple.com/videos/play/wwdc2023/10136/) (WWDC23 Session 10136).

## Topics

### Essentials

  <doc://com.apple.documentation/documentation/Updates/ScreenCaptureKit>

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.developer.persistent-content-capture>

[Capturing screen content on iOS](/documentation/ScreenCaptureKit/capturing-screen-content-on-ios)

Record and share screen captures on iOS by presenting the system content-sharing picker.

[Capturing screen content in macOS](/documentation/ScreenCaptureKit/capturing-screen-content-in-macos)

Stream desktop content like displays, apps, and windows by adopting screen capture in your app.

### Shareable content

[`class SCShareableContent`](/documentation/ScreenCaptureKit/SCShareableContent)

An instance that represents a set of displays, apps, and windows that your app can capture.

[`class SCShareableContentInfo`](/documentation/ScreenCaptureKit/SCShareableContentInfo)

An instance that provides information for the content in a given stream.

[`enum SCShareableContentStyle`](/documentation/ScreenCaptureKit/SCShareableContentStyle)

The style of content presented in a stream.

[`class SCDisplay`](/documentation/ScreenCaptureKit/SCDisplay)

An instance that represents a display device.

[`class SCRunningApplication`](/documentation/ScreenCaptureKit/SCRunningApplication)

An instance that represents an app running on a device.

[`class SCWindow`](/documentation/ScreenCaptureKit/SCWindow)

An instance that represents an onscreen window.

### Content capture

[`class SCStream`](/documentation/ScreenCaptureKit/SCStream)

An instance that represents a stream of shareable content.

[`class SCStreamConfiguration`](/documentation/ScreenCaptureKit/SCStreamConfiguration)

An instance that provides the output configuration for a stream.

[`class SCContentFilter`](/documentation/ScreenCaptureKit/SCContentFilter)

An instance that filters the content a stream captures.

[`protocol SCStreamDelegate`](/documentation/ScreenCaptureKit/SCStreamDelegate)

A delegate protocol your app implements to respond to stream events.

[`class SCScreenshotManager`](/documentation/ScreenCaptureKit/SCScreenshotManager)

An instance for the capture of single frames from a stream.

[`class SCScreenshotConfiguration`](/documentation/ScreenCaptureKit/SCScreenshotConfiguration)

An object that contains screenshot properties such as output width, height, and image quality specifications.

[`class SCScreenshotOutput`](/documentation/ScreenCaptureKit/SCScreenshotOutput)

An object that contains all images requested by the client.

[`class SCVideoEffectOutput`](/documentation/ScreenCaptureKit/SCVideoEffectOutput)

### Output processing

[`protocol SCStreamOutput`](/documentation/ScreenCaptureKit/SCStreamOutput)

A delegate protocol your app implements to receive capture stream output events.

[`enum SCStreamOutputType`](/documentation/ScreenCaptureKit/SCStreamOutputType)

Constants that represent output types for a stream frame.

[`struct SCStreamFrameInfo`](/documentation/ScreenCaptureKit/SCStreamFrameInfo)

An instance that defines metadata keys for a stream frame.

[`enum SCFrameStatus`](/documentation/ScreenCaptureKit/SCFrameStatus)

Status values for a frame from a stream.

[`class SCClipBufferingOutput`](/documentation/ScreenCaptureKit/SCClipBufferingOutput)

### System content-sharing picker

[`class SCContentSharingPicker`](/documentation/ScreenCaptureKit/SCContentSharingPicker)

An instance of a picker presented by the operating system for managing frame-capture streams.

[`struct SCContentSharingPickerConfiguration`](/documentation/ScreenCaptureKit/SCContentSharingPickerConfiguration-swift.struct)

An instance for configuring the system content-sharing picker.

[`@interface SCContentSharingPickerConfiguration : NSObject`](/documentation/ScreenCaptureKit/SCContentSharingPickerConfiguration-c.class)

An instance for configuring the system content-sharing picker.

[`struct SCContentSharingPickerMode`](/documentation/ScreenCaptureKit/SCContentSharingPickerMode)

Available modes for selecting streaming content from a picker presented by the operating system.

[`protocol SCContentSharingPickerObserver`](/documentation/ScreenCaptureKit/SCContentSharingPickerObserver)

An observer protocol your app implements to receive messages from the operating system’s content picker.

### Stream errors (Swift)

[`let SCStreamErrorDomain: String`](/documentation/ScreenCaptureKit/SCStreamErrorDomain)

A string representation of the error domain.

[`struct SCStreamError`](/documentation/ScreenCaptureKit/SCStreamError)

An instance representing a ScreenCaptureKit framework error.

### Stream errors (Objective-C)

[`let SCStreamErrorDomain: String`](/documentation/ScreenCaptureKit/SCStreamErrorDomain)

A string representation of the error domain.

[`enum Code`](/documentation/ScreenCaptureKit/SCStreamError/Code)

Codes for user cancellation events and errors that can occur in ScreenCaptureKit.

### Classes

[`class SCRecordingEditor`](/documentation/ScreenCaptureKit/SCRecordingEditor)

### Protocols

[`protocol SCClipBufferingOutputDelegate`](/documentation/ScreenCaptureKit/SCClipBufferingOutputDelegate)

[`protocol SCRecordingEditorDelegate`](/documentation/ScreenCaptureKit/SCRecordingEditorDelegate)

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)