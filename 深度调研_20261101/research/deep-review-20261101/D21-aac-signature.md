<!--
{
  "availability" : [
    "iOS: 15.0.0 -",
    "iPadOS: 15.0.0 -",
    "macCatalyst: 15.0.0 -",
    "macOS: 12.0.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "AutomaticAssessmentConfiguration",
  "identifier" : "/documentation/AutomaticAssessmentConfiguration/AEAssessmentApplication/requiresSignatureValidation",
  "metadataVersion" : "0.1.0",
  "role" : "Instance Property",
  "symbol" : {
    "kind" : "Instance Property",
    "modules" : [
      "Automatic Assessment Configuration"
    ],
    "preciseIdentifier" : "c:objc(cs)AEAssessmentApplication(py)requiresSignatureValidation"
  },
  "title" : "requiresSignatureValidation"
}
-->

# requiresSignatureValidation

A Boolean that indicates whether the session requires the app to have a valid code signature to run.

```
var requiresSignatureValidation: Bool { get set }
```

## Discussion

When this property is `true`, as it is by default, the system requires that the app’s code signature is valid, and that either Apple distributes the app, or the developer notarizes the app or distributes it through the App Store. You can set the value to `false` to relax these requirements, but do so with caution, because that greatly reduces the security of your assessment session.

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)