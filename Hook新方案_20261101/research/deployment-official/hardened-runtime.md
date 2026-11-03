<!--
{
  "documentType" : "article",
  "framework" : "Security",
  "identifier" : "/documentation/Security/hardened-runtime",
  "metadataVersion" : "0.1.0",
  "role" : "collectionGroup",
  "title" : "Hardened Runtime"
}
-->

# Hardened Runtime

Manage security protections and resource access for your macOS apps.

## Discussion

The Hardened Runtime, along with System Integrity Protection (SIP), protects the runtime integrity of your software by preventing certain classes of exploits, like code injection, dynamically linked library (DLL) hijacking, and process memory space tampering. To enable the Hardened Runtime for your app, navigate in Xcode to your target’s Signing & Capabilities information and click the + button. In the window that appears, choose Hardened Runtime.

![Screenshot highlighting where to click to add a new capability in Xcode’s Signing & Capabilities tab.](images/com.apple.security/media-3330446@2x.png)

The Hardened Runtime doesn’t affect the operation of most apps, but it does disallow certain less common capabilities, like just-in-time (JIT) compilation. If your app relies on a capability that the Hardened Runtime restricts, add an entitlement to disable an individual protection. You add an entitlement by enabling one of the runtime exceptions or access permissions listed in Xcode. Make sure to use only the entitlements that are absolutely necessary for your app’s functionality.

![Screenshot of Xcode showing some of the entitlements used for exceptions to the Hardened Runtime.](images/com.apple.security/media-3330445@2x.png)

You add entitlements only to executables. Shared libraries, frameworks, and in-process plug-ins inherit the entitlements of their host executable.

Due to their privileged position in the system, macOS refuses to load system extensions that use Hardened Runtime exception entitlements.  There’s one exception to this general rule: macOS allows the <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.cs.allow-jit> in non-DEXT system extensions.

The default value of these Boolean entitlements is false. When Xcode signs your code, it includes an entitlement only if the value is true. If you’re manually signing code, follow this convention to ensure maximum compatibility. Don’t include an entitlement if the value is false.

> Important:
> To upload a macOS app to be notarized, you must enable the Hardened Runtime capability. For more information about notarization, see <doc://com.apple.security/documentation/Security/notarizing-macos-software-before-distribution>.

## Topics

### Runtime Exceptions

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.cs.allow-jit>

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.cs.allow-unsigned-executable-memory>

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.cs.allow-dyld-environment-variables>

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.cs.disable-library-validation>

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.cs.disable-executable-page-protection>

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.cs.debugger>

### Resource Access

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.device.audio-input>

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.device.camera>

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.personal-information.location>

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.personal-information.addressbook>

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.personal-information.calendars>

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.personal-information.photos-library>

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.security.automation.apple-events>



---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)