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
  "identifier" : "/documentation/AutomaticAssessmentConfiguration/AEAssessmentApplication",
  "metadataVersion" : "0.1.0",
  "role" : "Class",
  "symbol" : {
    "kind" : "Class",
    "modules" : [
      "Automatic Assessment Configuration"
    ],
    "preciseIdentifier" : "c:objc(cs)AEAssessmentApplication"
  },
  "title" : "AEAssessmentApplication"
}
-->

# AEAssessmentApplication

A representation of an app that users can access during an assessment.

```
class AEAssessmentApplication
```

## Overview

Use an instance of this class when you want to make an app besides yours, like a calculator or a dictionary, available during an assessment. Create a representation of the app that you want to allow using the app’s bundle identifier and optionally the identifier of the team that distributes the app. You can get both identifiers for an app that you have installed using the `codesign` command line utility:

```shell
% codesign -v -d /Applications/MyApp.app
```

By default, the system requires that the app’s code signature is valid, and that either Apple distributes the app, or the developer notarizes the app or distributes it through the App Store. You can relax these requirements by setting the [`requiresSignatureValidation`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentApplication/requiresSignatureValidation) property to `false`, but that creates a potential security risk. In that case, the only requirement is that the app has the specified bundle and team identifiers. Prefer to keep the signature requirement.

Add the app to a session configuration by calling the `AEAssessmentConfiguration/setConfiguration(_:for:)` method, and then apply the configuration to either a new session that you create, or an existing session with the [`update(to:)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/update(to:)) method.

## Topics

### Creating an assessment application

[`init(bundleIdentifier: String, teamIdentifier: String?)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentApplication/init(bundleIdentifier:teamIdentifier:))

Creates a representation of an app using its bundle and team identifiers.

[`init(bundleIdentifier: String)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentApplication/init(bundleIdentifier:))

Creates a representation of an app using its bundle identifier.

[`var bundleIdentifier: String`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentApplication/bundleIdentifier)

The bundle identifier of the app.

[`var teamIdentifier: String?`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentApplication/teamIdentifier)

The team identifier of the app.

### Requiring code-signed apps

[`var requiresSignatureValidation: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentApplication/requiresSignatureValidation)

A Boolean that indicates whether the session requires the app to have a valid code signature to run.

## Relationships

### Inherits From

[`NSObject-swift.class`](/documentation/ObjectiveC/NSObject-swift.class)

### Conforms To

[`Equatable`](/documentation/Swift/Equatable)

[`NSCopying`](/documentation/Foundation/NSCopying)

[`CustomDebugStringConvertible`](/documentation/Swift/CustomDebugStringConvertible)

[`Hashable`](/documentation/Swift/Hashable)

[`CVarArg`](/documentation/Swift/CVarArg)

[`NSObjectProtocol`](/documentation/ObjectiveC/NSObjectProtocol)

[`CustomStringConvertible`](/documentation/Swift/CustomStringConvertible)

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)