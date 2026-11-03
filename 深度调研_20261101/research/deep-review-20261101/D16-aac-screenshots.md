<!--
{
  "availability" : [
    "iOS: 13.4.0 -",
    "iPadOS: 13.4.0 -",
    "macCatalyst: 26.1.0 -",
    "macOS: 26.1.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "AutomaticAssessmentConfiguration",
  "identifier" : "/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsScreenshots",
  "metadataVersion" : "0.1.0",
  "role" : "Instance Property",
  "symbol" : {
    "kind" : "Instance Property",
    "modules" : [
      "Automatic Assessment Configuration"
    ],
    "preciseIdentifier" : "c:objc(cs)AEAssessmentConfiguration(py)allowsScreenshots"
  },
  "title" : "allowsScreenshots"
}
-->

# allowsScreenshots

A Boolean value that indicates whether to allow screenshots copied to the clipboard during an assessment.

```
var allowsScreenshots: Bool { get set }
```

## Discussion

An assessment session disables the ability to take screenshots by default to maintain assessment integrity. This property specifically applies to screenshots that are copied to the clipboard, typically those taken using the Command+Control+Shift+3 and Command+Control+Shift+4 keyboard shortcuts. You can allow clipboard screenshots by setting `allowsScreenshots` to `true`.

> Note: The clipboard is cleared before the assessment session ends to prevent exporting captured content.

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)