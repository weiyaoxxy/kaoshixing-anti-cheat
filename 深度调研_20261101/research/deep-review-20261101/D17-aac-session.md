<!--
{
  "availability" : [
    "iOS: 13.4.0 -",
    "iPadOS: 13.4.0 -",
    "macCatalyst: 14.0.0 -",
    "macOS: 10.15.4 -"
  ],
  "documentType" : "symbol",
  "framework" : "AutomaticAssessmentConfiguration",
  "identifier" : "/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession",
  "metadataVersion" : "0.1.0",
  "role" : "Class",
  "symbol" : {
    "kind" : "Class",
    "modules" : [
      "Automatic Assessment Configuration"
    ],
    "preciseIdentifier" : "c:objc(cs)AEAssessmentSession"
  },
  "title" : "AEAssessmentSession"
}
-->

# AEAssessmentSession

A session that your app uses to protect an assessment.

```
class AEAssessmentSession
```

## Overview

Use the [`AEAssessmentSession`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession) class to manage an assessment session. The system allows only one active session at a time across all processes. The first session to run gets exclusive access to the system; subsequent session attempts fail until the first session ends.

To create an assessment session, pass a new [`AEAssessmentConfiguration`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration) instance to the [`init(configuration:)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/init(configuration:)) method. Then, provide the session with a delegate that conforms to the [`AEAssessmentSessionDelegate`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSessionDelegate) protocol:

```swift
let config = AEAssessmentConfiguration()
let session = AEAssessmentSession(configuration: config)
session.delegate = self
```

You can indicate exceptions to the restrictions imposed by an assessment session by setting the properties of the configuration instance, or you can use the default restrictions as shown above. The session tells its delegate about state changes during its life cycle. To start a session, call the session’s [`begin()`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/begin()) method:

```swift
session.begin()
```

The method returns immediately, and the session starts disabling system features. After achieving the desired state, the session calls its delegate’s [`assessmentSessionDidBegin(_:)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSessionDelegate/assessmentSessionDidBegin(_:)) method. Only after receiving this callback is it safe to begin your assessment. Be sure to keep a strong reference to the session as long as you want it to remain active. If the system deallocates an active session, the session automatically ends.

> Important:
> Prior to macOS 12.1, a DNS lookup that your app initiates during a session might fail. Be sure your app resolves all required domain names before beginning a session so that the system can cache the results. You can do this by using <doc://com.apple.documentation/documentation/Foundation/URLSession> to send a `HEAD` request to each domain name that your app needs to access.

After completing an assessment and hiding all sensitive information, call the session’s [`end()`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/end()) method:

```swift
session.end()
```

After making the call, wait for the session to call its delegate’s [`assessmentSessionDidEnd(_:)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSessionDelegate/assessmentSessionDidEnd(_:)) method before reporting assessment completion to the user.

During assessment, the session’s delegate might receive an [`assessmentSession(_:wasInterruptedWithError:)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSessionDelegate/assessmentSession(_:wasInterruptedWithError:)) callback to indicate a failure. If this happens, immediately stop the assessment, hide all sensitive content, and end the session. Because it might take time for your app to finalize the assessment, the session relies on your app to call the session’s [`end()`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/end()) method:

```swift
func assessmentSession(_ session: AEAssessmentSession, wasInterruptedWithError error: Error) {
    // Hide sensitive UI and optionally store assessment progress.

    // End the session.
    session.end()
}
```

## Topics

### Creating a session

[`init(configuration: AEAssessmentConfiguration)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/init(configuration:))

Creates a new assessment session.

### Managing session configuration

[`func update(to: AEAssessmentConfiguration)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/update(to:))

Changes the session to use the specified configuration.

[`var configuration: AEAssessmentConfiguration`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/configuration)

The current configuration of the session.

[`class var supportsMultipleParticipants: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/supportsMultipleParticipants)

A Boolean that indicates whether the current device or platform supports a configuration with one or more participant applications.

[`class var supportsConfigurationUpdates: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/supportsConfigurationUpdates)

A Boolean that indicates whether the current device or platform supports updating a session’s configuration after the session has begun.

### Responding to session updates

[`var delegate: (any AEAssessmentSessionDelegate)?`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/delegate)

A delegate to which the session provides state change updates.

[`protocol AEAssessmentSessionDelegate`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSessionDelegate)

An interface that the session uses to provide information about session state changes to a delegate.

### Starting and stopping a session

[`func begin()`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/begin())

Starts an assessment session.

[`func end()`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/end())

Ends an assessment session.

[`var isActive: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/isActive)

A Boolean that indicates whether an assessment session is running.

## Relationships

### Conforms To

[`CustomDebugStringConvertible`](/documentation/Swift/CustomDebugStringConvertible)

[`NSObjectProtocol`](/documentation/ObjectiveC/NSObjectProtocol)

[`Equatable`](/documentation/Swift/Equatable)

[`Hashable`](/documentation/Swift/Hashable)

[`CVarArg`](/documentation/Swift/CVarArg)

[`CustomStringConvertible`](/documentation/Swift/CustomStringConvertible)

### Inherits From

[`NSObject-swift.class`](/documentation/ObjectiveC/NSObject-swift.class)

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)