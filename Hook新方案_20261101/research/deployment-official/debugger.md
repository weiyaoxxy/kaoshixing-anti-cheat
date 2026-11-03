<!--
{
  "availability" : [
    "macOS: 10.7.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "BundleResources",
  "identifier" : "/documentation/BundleResources/Entitlements/com.apple.security.cs.debugger",
  "metadataVersion" : "0.1.0",
  "role" : "Property List Key",
  "symbol" : {
    "kind" : "Property List Key",
    "modules" : [
      "Bundle Resources"
    ],
    "preciseIdentifier" : "entitlements:Entitlements.com.apple.security.cs.debugger"
  },
  "title" : "Debugging tool entitlement"
}
-->

# Debugging tool entitlement

A Boolean value that indicates whether the app is a debugger and may attach to other processes or get task ports.

## Discussion

Apps with the `Debugging tool entitlement` can call `task_for_pid()` to retrieve a valid task port for unsigned and third-party apps with the `Get task allow` entitlement set to `true`. However, even with the debugging tool entitlement, a debugger can’t get the task ports of processes that don’t have the `Get task allow` entitlement, and that are therefore protected by System Integrity Protection. See the man page for `taskgated(8)` for more information about getting task ports.

Xcode automatically adds the `Get task allow` entitlement to apps that you build for debugging, while removing the entitlement before App Store submission. This enables Xcode itself to attach to and debug your app during development.

When a non-root user runs an app with the debugging tool entitlement, the system presents an authorization dialog asking for a system administrator’s credentials. If authorization succeeds, the debugger receives a 10-hour session before authorization expires.

To add this entitlement to your app, first enable the Hardened Runtime capability in Xcode, and then under Runtime Exceptions, select Debugging Tool.

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)