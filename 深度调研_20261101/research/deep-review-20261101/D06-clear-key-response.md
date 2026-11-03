<!--
{
  "availability" : [
    "iOS: 11.0.0 -",
    "iPadOS: 11.0.0 -",
    "macCatalyst: 13.1.0 -",
    "macOS: 10.13.0 -",
    "tvOS: 11.0.0 -",
    "visionOS: 1.0.0 -",
    "watchOS: 7.0.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "AVFoundation",
  "identifier" : "/documentation/AVFoundation/AVContentKeyResponse/init(clearKeyData:initializationVector:)",
  "metadataVersion" : "0.1.0",
  "role" : "Initializer",
  "symbol" : {
    "kind" : "Initializer",
    "modules" : [
      "AVFoundation"
    ],
    "preciseIdentifier" : "c:objc(cs)AVContentKeyResponse(cm)contentKeyResponseWithClearKeyData:initializationVector:"
  },
  "title" : "init(clearKeyData:initializationVector:)"
}
-->

# init(clearKeyData:initializationVector:)

Creates a new key response object for key data and initialization vector sent in the clear.

```
convenience init(clearKeyData keyData: Data, initializationVector: Data?)
```

## Parameters

`keyData`

The key used for decrypting content.

`initializationVector`

The initialization vector used for decrypting content. This value is `nil` when the initialization vector is contained in the media to be decrypted.

## Return Value

Returns a new [`AVContentKeyResponse`](/documentation/AVFoundation/AVContentKeyResponse) object to decrypt content.

## Discussion

Use the results of this initializer when the content key session creates a key request using the [`clearKey`](/documentation/AVFoundation/AVContentKeySystem/clearKey) parameter. The results are then passed to the [`processContentKeyResponse(_:)`](/documentation/AVFoundation/AVContentKeyRequest/processContentKeyResponse(_:)) method to supply the decrypter with key data.

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)