<!--
{
  "availability" : [
    "iOS: 6.0.0 -",
    "iPadOS: 6.0.0 -",
    "macCatalyst: 13.1.0 -",
    "macOS: 10.12.0 -",
    "tvOS: 9.0.0 -",
    "visionOS: 1.0.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "AVFoundation",
  "identifier" : "/documentation/AVFoundation/AVPlayer/isOutputObscuredDueToInsufficientExternalProtection",
  "metadataVersion" : "0.1.0",
  "role" : "Instance Property",
  "symbol" : {
    "kind" : "Instance Property",
    "modules" : [
      "AVFoundation"
    ],
    "preciseIdentifier" : "c:objc(cs)AVPlayer(py)outputObscuredDueToInsufficientExternalProtection"
  },
  "title" : "isOutputObscuredDueToInsufficientExternalProtection"
}
-->

# isOutputObscuredDueToInsufficientExternalProtection

A Boolean value that indicates whether output is being obscured because of insufficient external protection.

```
nonisolated var isOutputObscuredDueToInsufficientExternalProtection: Bool { get }
```

## Discussion

Items that incorporate copy protection or other forms of security might have their visual content obscured by the player object if the current device configuration does not meet the requirements for protecting the item. This property reports whether the player is currently obscuring the item. If the current item does not require external protection or if the device configuration sufficiently protects the item, the value of this property is set to <doc://com.apple.documentation/documentation/Swift/false>.

You can use this property to determine whether to change your app’s user interface to reflect the change in visibility. You can observe changes to the value of this property using key-value observing.

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)