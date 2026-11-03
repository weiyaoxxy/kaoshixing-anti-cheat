<!--
{
  "availability" : [

  ],
  "documentType" : "symbol",
  "framework" : "AutomaticAssessmentConfiguration",
  "identifier" : "/documentation/AutomaticAssessmentConfiguration",
  "metadataVersion" : "0.1.0",
  "role" : "Framework",
  "symbol" : {
    "kind" : "Framework",
    "modules" : [
      "Automatic Assessment Configuration"
    ],
    "preciseIdentifier" : "AutomaticAssessmentConfiguration"
  },
  "title" : "Automatic Assessment Configuration"
}
-->

# Automatic Assessment Configuration

Enter single-app mode and prevent students from accessing specific system features while taking an exam.

## Overview

Use the AutomaticAssessmentConfiguration framework to create an assessment session that limits access to system features. The session prevents a user from using the device to retrieve information beyond that which your app provides, or distributing sensitive information from within your app. This limited access helps you protect the integrity of an assessment, like an exam, conducted by your app.

Apps that use the AutomaticAssessmentConfiguration framework must have the <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.developer.automatic-assessment-configuration> entitlement. With the entitlement set, use an instance of the [`AEAssessmentSession`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession) class to start and stop assessment sessions.

A session provides protections by preventing access to desktop elements like:

- The Dock
- The Application Menu Bar
- Mission Control
- Notification Center
- Spaces other than the current one
- Other apps, except those that you selectively allow

Additionally, a session:

- Prevents screen recording and screen capture
- Disables Siri
- Stops media playing
- Allows network access for only your app
- Disables Handoff
- Clears the pasteboard buffer when starting and stopping the session

> Note:
> If you publish an educational app that delivers exams to students, you can request permission to use the <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.developer.automatic-assessment-configuration> entitlement by filling in the [Automatic Assessment Configuration Entitlement Request](https://developer.apple.com/contact/request/automatic-assessment-configuration/) form.

The framework reports an error if you try to start an assessment from an app running in visionOS.

## Topics

### Essentials

  <doc://com.apple.documentation/documentation/BundleResources/Entitlements/com.apple.developer.automatic-assessment-configuration>

### Sessions

[Preparing an educational assessment app for distribution](/documentation/AutomaticAssessmentConfiguration/preparing-an-educational-assessment-app-for-distribution)

Ensure your app maintains academic integrity by reviewing assessment practices and managing system capabilities.

[Build an Educational Assessment App](/documentation/AutomaticAssessmentConfiguration/build-an-educational-assessment-app)

Ensure the academic integrity of your assessment app by using Automatic Assessment Configuration.

[`class AEAssessmentConfiguration`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration)

Configuration information for an assessment session.

[`class AEAssessmentSession`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession)

A session that your app uses to protect an assessment.

### Errors

[`struct AEAssessmentError`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentError)

Errors issued by an assessment session to its delegate.

[`enum Code`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentError/Code)

Error codes that the framework returns if a session fails.

[`let AEAssessmentErrorDomain: String`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentErrorDomain)

A constant representing the error domain that the framework uses when issuing errors.

### Classes

[`class AEAssessmentBinaryExecutable`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentBinaryExecutable)

A non-bundled, non-UI executable (e.g. a launchd daemon) designated as an assessment participant
by its on-disk path.

[`class AEAssessmentBinaryExecutableConfiguration`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentBinaryExecutableConfiguration)

The configuration applied to an [`AEAssessmentBinaryExecutable`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentBinaryExecutable) participant.

### Structures

[`struct AEAppleMenuItem`](/documentation/AutomaticAssessmentConfiguration/AEAppleMenuItem)

Identifies an item in the Apple menu.

[`struct AEMenuBarItem`](/documentation/AutomaticAssessmentConfiguration/AEMenuBarItem)

Identifies a menu bar item that can remain visible during an assessment session.

### Enumerations

[`enum AEUserAccountType`](/documentation/AutomaticAssessmentConfiguration/AEUserAccountType)

Specifies the type of account required for an assessment session.

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)