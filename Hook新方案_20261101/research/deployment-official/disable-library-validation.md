<!--
{
  "availability" : [
    "macOS: 10.7.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "BundleResources",
  "identifier" : "/documentation/BundleResources/Entitlements/com.apple.security.cs.disable-library-validation",
  "metadataVersion" : "0.1.0",
  "role" : "Property List Key",
  "symbol" : {
    "kind" : "Property List Key",
    "modules" : [
      "Bundle Resources"
    ],
    "preciseIdentifier" : "entitlements:Entitlements.com.apple.security.cs.disable-library-validation"
  },
  "title" : "Disable Library Validation Entitlement"
}
-->

# Disable Library Validation Entitlement

A Boolean value that indicates whether the app loads arbitrary plug-ins or frameworks, without requiring code signing.

## Discussion

The <doc://com.apple.documentation/documentation/Security/hardened-runtime> enables library validation by default. This security-hardening feature prevents a program from loading frameworks, plug-ins, or libraries unless they’re either signed by Apple or signed with the same Team ID as the main executable. The macOS dynamic linker (`dyld`) provides a detailed error message when the system prevents code from loading due to library validation. Use the [`Disable Library Validation Entitlement`](/documentation/BundleResources/Entitlements/com.apple.security.cs.disable-library-validation) if your program loads plug-ins that are signed by other third-party developers.

To add this entitlement to your app, first enable the Hardened Runtime capability in Xcode, and then under Runtime Exceptions, select Disable Library Validation.

> Important:
> Because library validation is such an important security-hardening feature, Gatekeeper runs extra security checks on programs that have it disabled. If your program is blocked by Gatekeeper, check whether you’ve unnecessarily disabled library validation.

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)