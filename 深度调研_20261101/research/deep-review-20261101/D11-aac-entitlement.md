<!--
{
  "availability" : [
    "iOS: 13.4.0 -",
    "iPadOS: 13.4.0 -",
    "macOS: 10.15.4 -"
  ],
  "documentType" : "symbol",
  "framework" : "BundleResources",
  "identifier" : "/documentation/BundleResources/Entitlements/com.apple.developer.automatic-assessment-configuration",
  "metadataVersion" : "0.1.0",
  "role" : "Property List Key",
  "symbol" : {
    "kind" : "Property List Key",
    "modules" : [
      "Bundle Resources"
    ],
    "preciseIdentifier" : "entitlements:Entitlements.com.apple.developer.automatic-assessment-configuration"
  },
  "title" : "com.apple.developer.automatic-assessment-configuration"
}
-->

# com.apple.developer.automatic-assessment-configuration

A Boolean value that indicates whether an app may create an assessment session.

## Discussion

Use an <doc://com.apple.documentation/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession> instance to put a device into a state that prevents users from accessing certain system features during high-stakes assessment activities, such as administering an exam. Your app needs the [`com.apple.developer.automatic-assessment-configuration`](/documentation/BundleResources/Entitlements/com.apple.developer.automatic-assessment-configuration) entitlement to create an assessment session.

To add the entitlement to your app, set the entitlement’s type to Boolean in the Xcode property list editor, and the corresponding value to `YES`.

![A screenshot of Xcode with a project’s entitlements file in the property list editor, showing the com.apple.developer.automatic-assessment-configuration entitlement.](images/com.apple.bundleresources/media-3540004@2x.png)

Before your app can use this entitlement, you must first get permission to use it. Request permission by filling in the [Automatic Assessment Configuration Entitlement Request](https://developer.apple.com/contact/request/automatic-assessment-configuration/) form.

> Important:
> If your app has a deployment target earlier than macOS 11, to use the ``doc://com.apple.bundleresources/documentation/BundleResources/Entitlements/com.apple.developer.automatic-assessment-configuration`` entitlement, your app also needs the `com.apple.security.temporary-exception.mach-lookup.global-name` entitlement. Add this to your app’s entitlements file with a corresponding value that’s an array of strings containing the string `com.apple.assessmentagent`.

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)