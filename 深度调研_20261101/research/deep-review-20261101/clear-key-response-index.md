<!--
{
  "availability" : [
    "iOS: 10.3.0 -",
    "iPadOS: 10.3.0 -",
    "macCatalyst: 13.1.0 -",
    "macOS: 10.12.4 -",
    "tvOS: 10.2.0 -",
    "visionOS: 1.0.0 -",
    "watchOS: 7.0.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "AVFoundation",
  "identifier" : "/documentation/AVFoundation/AVContentKeyResponse",
  "metadataVersion" : "0.1.0",
  "role" : "Class",
  "symbol" : {
    "kind" : "Class",
    "modules" : [
      "AVFoundation"
    ],
    "preciseIdentifier" : "c:objc(cs)AVContentKeyResponse"
  },
  "title" : "AVContentKeyResponse"
}
-->

# AVContentKeyResponse

An object that encapsulates information about a response to a content decryption key request.

```
class AVContentKeyResponse
```

## Topics

### Creating new content key responses

[`convenience init(clearKeyData: Data, initializationVector: Data?)`](/documentation/AVFoundation/AVContentKeyResponse/init(clearKeyData:initializationVector:))

Creates a new key response object for key data and initialization vector sent in the clear.

[`convenience init(fairPlayStreamingKeyResponseData: Data)`](/documentation/AVFoundation/AVContentKeyResponse/init(fairPlayStreamingKeyResponseData:))

Creates a content key response with an encrypted key response data blob when FairPlay Streaming is the key delivery method.

[`convenience init(authorizationTokenData: Data)`](/documentation/AVFoundation/AVContentKeyResponse/init(authorizationTokenData:))

Creates a content key response with an authorization token.

## Relationships

### Conforms To

[`Equatable`](/documentation/Swift/Equatable)

[`CustomDebugStringConvertible`](/documentation/Swift/CustomDebugStringConvertible)

[`Sendable`](/documentation/Swift/Sendable)

[`NSObjectProtocol`](/documentation/ObjectiveC/NSObjectProtocol)

[`CustomStringConvertible`](/documentation/Swift/CustomStringConvertible)

[`SendableMetatype`](/documentation/Swift/SendableMetatype)

[`Hashable`](/documentation/Swift/Hashable)

[`CVarArg`](/documentation/Swift/CVarArg)

### Inherits From

[`NSObject-swift.class`](/documentation/ObjectiveC/NSObject-swift.class)

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)