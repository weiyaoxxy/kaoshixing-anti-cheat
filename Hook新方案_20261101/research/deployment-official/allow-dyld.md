<!--
{
  "availability" : [
    "macOS: 10.7.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "BundleResources",
  "identifier" : "/documentation/BundleResources/Entitlements/com.apple.security.cs.allow-dyld-environment-variables",
  "metadataVersion" : "0.1.0",
  "role" : "Property List Key",
  "symbol" : {
    "kind" : "Property List Key",
    "modules" : [
      "Bundle Resources"
    ],
    "preciseIdentifier" : "entitlements:Entitlements.com.apple.security.cs.allow-dyld-environment-variables"
  },
  "title" : "Allow DYLD environment variables entitlement"
}
-->

# Allow DYLD environment variables entitlement

A Boolean value that indicates whether the app may be affected by dynamic linker environment variables, which you can use to inject code into your app’s process.

## Discussion

If your app relies on dynamic linker variables to modify its behavior at runtime, add the `Allow DYLD environment variables entitlement` to your app. This causes the macOS dynamic linker (`dyld`) to read from environment variables that begin with `DYLD_`. See the `dyld` man page for a list of these variables.

Injecting libraries or changing search paths with this feature may still require another entitlement. For example, you also need the [`Disable Library Validation Entitlement`](/documentation/BundleResources/Entitlements/com.apple.security.cs.disable-library-validation) if an injected library isn’t signed with the expected team ID.

To add the entitlement to your app, first enable the Hardened Runtime capability in Xcode, and then under Runtime Exceptions, select Allow DYLD Environment Variables.

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)