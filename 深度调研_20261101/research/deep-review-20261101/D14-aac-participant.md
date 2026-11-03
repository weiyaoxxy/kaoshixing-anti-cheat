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
  "identifier" : "/documentation/AutomaticAssessmentConfiguration/AEAssessmentParticipantConfiguration",
  "metadataVersion" : "0.1.0",
  "role" : "Class",
  "symbol" : {
    "kind" : "Class",
    "modules" : [
      "Automatic Assessment Configuration"
    ],
    "preciseIdentifier" : "c:objc(cs)AEAssessmentParticipantConfiguration"
  },
  "title" : "AEAssessmentParticipantConfiguration"
}
-->

# AEAssessmentParticipantConfiguration

Configuration information for an app that’s available during an assessment.

```
class AEAssessmentParticipantConfiguration
```

## Overview

Use an instance of this class to configure the properties of an app that you allow to run during an assessment. Associate the participant configuration with an app (an [`AEAssessmentApplication`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentApplication) instance) when you call the `AEAssessmentConfiguration/setConfiguration(_:for:)` method of a session configuration.

## Topics

### Creating participant configuration instances

[`init()`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentParticipantConfiguration/init())

Initializes an assessment participant configuration instance.

[`class func new() -> Self`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentParticipantConfiguration/new())

Creates a new assessment participant configuration instance.

### Allowing network access

[`var allowsNetworkAccess: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentParticipantConfiguration/allowsNetworkAccess)

A Boolean that indicates whether an app can access network resources during an assessment.

### Instance Properties

[`var allowedMenuItemLanguages: Set<Locale.Language>`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentParticipantConfiguration/allowedMenuItemLanguages)

The set of languages for which allowed menu items have been
configured.

[`var configurationInfo: [String : Any]`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentParticipantConfiguration/configurationInfo)

[`var isRequired: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentParticipantConfiguration/isRequired)

### Instance Methods

[`func allowedMenuItems(for: Locale.Language) -> Set<String>?`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentParticipantConfiguration/allowedMenuItems(for:))

Returns the set of allowed menu item titles for the given language,
or `nil` if no items have been configured for that language.

[`func setAllowedMenuItems(Set<String>?, for: Locale.Language)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentParticipantConfiguration/setAllowedMenuItems(_:for:))

Sets the allowed menu item titles for the given language.

## Relationships

### Conforms To

[`Equatable`](/documentation/Swift/Equatable)

[`NSCopying`](/documentation/Foundation/NSCopying)

[`Hashable`](/documentation/Swift/Hashable)

[`CVarArg`](/documentation/Swift/CVarArg)

[`CustomDebugStringConvertible`](/documentation/Swift/CustomDebugStringConvertible)

[`NSObjectProtocol`](/documentation/ObjectiveC/NSObjectProtocol)

[`CustomStringConvertible`](/documentation/Swift/CustomStringConvertible)

### Inherits From

[`NSObject-swift.class`](/documentation/ObjectiveC/NSObject-swift.class)

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)