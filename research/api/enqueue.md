<!--
{
  "availability" : [
    "iOS: 8.0.0 - 18.0.0",
    "iPadOS: 8.0.0 - 18.0.0",
    "macCatalyst: 13.1.0 - 18.0.0",
    "macOS: 10.8.0 - 15.0.0",
    "tvOS: 10.2.0 - 18.0.0",
    "visionOS: 1.0.0 - 2.0.0"
  ],
  "documentType" : "symbol",
  "framework" : "AVFoundation",
  "identifier" : "/documentation/AVFoundation/AVSampleBufferDisplayLayer/enqueue(_:)",
  "metadataVersion" : "0.1.0",
  "role" : "Instance Method",
  "symbol" : {
    "kind" : "Instance Method",
    "modules" : [
      "AVFoundation"
    ],
    "preciseIdentifier" : "c:objc(cs)AVSampleBufferDisplayLayer(im)enqueueSampleBuffer:"
  },
  "title" : "enqueue(_:)"
}
-->

# enqueue(_:)

Sends a sample buffer for display.

```
func enqueue(_ sampleBuffer: CMSampleBuffer)
```

## Parameters

`sampleBuffer`

The sample buffer to display.

## Discussion

Apple discourages the use of this symbol in iOS 17, tvOS 17, and macOS 14 and later. Use [`enqueue(_:)`](/documentation/AVFoundation/AVQueuedSampleBufferRendering/enqueue(_:)) on the [`sampleBufferRenderer`](/documentation/AVFoundation/AVSampleBufferDisplayLayer/sampleBufferRenderer) instead.

If `sampleBuffer` has the <doc://com.apple.documentation/documentation/CoreMedia/kCMSampleAttachmentKey_DoNotDisplay> attachment set to <doc://com.apple.documentation/documentation/CoreFoundation/kCFBooleanTrue>, the frame will be decoded but not displayed.

If `sampleBuffer` has the <doc://com.apple.documentation/documentation/CoreMedia/kCMSampleAttachmentKey_DisplayImmediately> attachment set to <doc://com.apple.documentation/documentation/CoreFoundation/kCFBooleanTrue>, the decoded image will be displayed as soon as possible, replacing all previously enqueued images regardless of their timestamps.

Otherwise, the decoded image will be displayed at the `sampleBuffer` output presentation timestamp, as interpreted by the [`controlTimebase`](/documentation/AVFoundation/AVSampleBufferDisplayLayer/controlTimebase) property (or the `mach_absolute_time` timeline if there is no control timebase).

To schedule the removal of previous images at a specific timestamp, enqueue a marker sample buffer containing no samples, with the <doc://com.apple.documentation/documentation/CoreMedia/kCMSampleBufferAttachmentKey_EmptyMedia> attachment set to <doc://com.apple.documentation/documentation/CoreFoundation/kCFBooleanTrue>.

> Important:
> Attachments with the `kCMSampleAttachmentKey_*` prefix must be set via <doc://com.apple.documentation/documentation/CoreMedia/CMSampleBufferGetSampleAttachmentsArray(_:createIfNecessary:)> and <doc://com.apple.documentation/documentation/CoreFoundation/CFDictionarySetValue(_:_:_:)>. Attachments with the `kCMSampleBufferAttachmentKey_*` prefix must be set via <doc://com.apple.documentation/documentation/CoreMedia/CMSetAttachment(_:key:value:attachmentMode:)>.

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)