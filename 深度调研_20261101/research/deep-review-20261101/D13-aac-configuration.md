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
  "identifier" : "/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration",
  "metadataVersion" : "0.1.0",
  "role" : "Class",
  "symbol" : {
    "kind" : "Class",
    "modules" : [
      "Automatic Assessment Configuration"
    ],
    "preciseIdentifier" : "c:objc(cs)AEAssessmentConfiguration"
  },
  "title" : "AEAssessmentConfiguration"
}
-->

# AEAssessmentConfiguration

Configuration information for an assessment session.

```
class AEAssessmentConfiguration
```

## Overview

Create a configuration instance and pass it to the [`init(configuration:)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession/init(configuration:)) initializer of an [`AEAssessmentSession`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentSession) instance to create a new assessment session. Before using the configuration, indicate which exceptions you want to allow for the assessment session’s restrictions by setting values on the configuration instance. For example, you can set values to allow dictation and certain aspects of autocorrect:

```objc
AEAssessmentConfiguration *config = [AEAssessmentConfiguration new];

#if TARGET_OS_IPHONE || TARGET_IPHONE_SIMULATOR // These exceptions available only on iOS and iPadOS.
config.allowsDictation = YES;
config.autocorrectMode = AEAutocorrectModePunctuation | AEAutocorrectModeSpelling;
#endif

AEAssessmentSession *session = [[AEAssessmentSession alloc] initWithConfiguration:config];
```

While you provide a configuration instance when creating a session on iOS, iPadOS, and macOS, specific exceptions apply only to certain platforms. In particular, on macOS, you can selectively make specific apps besides your own available during an assessment — for example, to allow users to access a calculator or a dictionary. All other exceptions apply only to iOS and iPadOS.

## Topics

### Allowing access to other apps

[`var configurationsByApplication: [AEAssessmentApplication : AEAssessmentParticipantConfiguration]`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/configurationsByApplication)

The collection of apps available during an assessment, along with their associated configurations.

[`var mainParticipantConfiguration: AEAssessmentParticipantConfiguration`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/mainParticipantConfiguration)

The app-specific configuration for the app that invokes the assessment.

[`class AEAssessmentApplication`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentApplication)

A representation of an app that users can access during an assessment.

[`class AEAssessmentParticipantConfiguration`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentParticipantConfiguration)

Configuration information for an app that’s available during an assessment.

### Allowing accessibility

[`var allowsAccessibilitySpeech: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilitySpeech)

A Boolean value that indicates whether to allow the speech-related accessibility features during an assessment.

[`var allowsDictation: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsDictation)

A Boolean value that indicates whether to allow the use of dictation during an assessment.

### Allowing typing assistance

[`var allowsContinuousPathKeyboard: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsContinuousPathKeyboard)

A Boolean value that indicates whether to allow Slide to Type to operate during an assessment.

[`var allowsKeyboardShortcuts: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsKeyboardShortcuts)

A Boolean value that indicates whether to allow keyboard shortcuts during an assessment.

[`var allowsPredictiveKeyboard: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsPredictiveKeyboard)

A Boolean value that indicates whether to enable the predictive keyboard during an assessment.

[`var allowsPasswordAutoFill: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsPasswordAutoFill)

A Boolean value that indicates whether to allow password autofill during an assessment.

### Allowing corrections

[`var allowsSpellCheck: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsSpellCheck)

A Boolean value that indicates whether to allow spell check during an assessment.

[`var autocorrectMode: AEAssessmentConfiguration.AutocorrectMode`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/autocorrectMode-swift.property)

A Boolean value that indicates whether to allow Autocorrect during an assessment.

[`struct AutocorrectMode`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/AutocorrectMode-swift.struct)

The set of autocorrect features that you can enable during an assessment.

### Allowing handoff

[`var allowsActivityContinuation: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsActivityContinuation)

A Boolean value that indicates whether to allow Handoff during an assessment.

### Instance Properties

[`var allowedAppleMenuItems: Set<AEAppleMenuItem>?`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowedAppleMenuItems)

The set of allowed Apple menu items during an assessment.

[`var allowedDirectoriesAndFiles: Set<URL>?`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowedDirectoriesAndFiles)

The set of directories and files that remain visible in the Finder during an assessment.

[`var allowedMenuBarItems: Set<AEMenuBarItem>?`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowedMenuBarItems)

The set of menu bar items that should remain visible during an assessment.

[`var allowsAccessibilityAlternativeInputMethods: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilityAlternativeInputMethods)

A Boolean value that indicates whether to allow alternative input methods for accessibility features during an assessment.

[`var allowsAccessibilityBackgroundSounds: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilityBackgroundSounds)

A Boolean value that indicates whether to allow Background Sounds during an assessment.

[`var allowsAccessibilityFullKeyboardAccess: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilityFullKeyboardAccess)

A Boolean value that indicates whether to allow Full Keyboard Access during an assessment.

[`var allowsAccessibilityHoverText: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilityHoverText)

A Boolean value that indicates whether to allow Hover Text during an assessment.

[`var allowsAccessibilityKeyboard: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilityKeyboard)

A Boolean value that indicates whether to allow the Accessibility Keyboard during an assessment.

[`var allowsAccessibilityLiveCaptions: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilityLiveCaptions)

A Boolean value that indicates whether to allow Live Captions during an assessment.

[`var allowsAccessibilityLiveSpeech: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilityLiveSpeech)

A Boolean value that indicates whether to allow Live Speech during an assessment.

[`var allowsAccessibilityReader: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilityReader)

A Boolean value that indicates whether to allow the Accessibility Reader during an assessment.

[`var allowsAccessibilitySpokenContent: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilitySpokenContent)

A Boolean value that indicates whether to allow Spoken Content during an assessment.

[`var allowsAccessibilitySwitchControl: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilitySwitchControl)

A Boolean value that indicates whether to allow Switch Control during an assessment.

[`var allowsAccessibilityTypingFeedback: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilityTypingFeedback)

A Boolean value that indicates whether to allow accessibility typing feedback during an assessment.

[`var allowsAccessibilityVoiceControl: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilityVoiceControl)

A Boolean value that indicates whether to allow Voice Control during an assessment.

[`var allowsAccessibilityVoiceOver: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilityVoiceOver)

A Boolean value that indicates whether to allow VoiceOver during an assessment.

[`var allowsAccessibilityZoom: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAccessibilityZoom)

A Boolean value that indicates whether to allow Zoom during an assessment.

[`var allowsAutoFill: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsAutoFill)

A Boolean value that indicates whether to allow autofill during an assessment.

[`var allowsDock: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsDock)

A Boolean value that indicates whether to allow the Dock during an assessment.

[`var allowsEmojiKeyboard: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsEmojiKeyboard)

A Boolean value that indicates whether to allow the emoji keyboard during an assessment.

[`var allowsForceQuitKeyboardShortcuts: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsForceQuitKeyboardShortcuts)

A Boolean value that indicates whether to allow force quitting apps during an assessment.

[`var allowsLockdownMode: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsLockdownMode)

A Boolean value that indicates whether the assessment allows Lockdown Mode to be active.

[`var allowsMenuBar: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsMenuBar)

A Boolean value that indicates whether to allow the menu bar during an assessment.

[`var allowsOnlyParticipantsToRun: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsOnlyParticipantsToRun)

A Boolean value that indicates whether only participant applications are allowed to run during an assessment.

[`var allowsPrivateRelay: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsPrivateRelay)

A Boolean value that indicates whether the assessment allows iCloud Private Relay to be active.

[`var allowsScreenshots: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsScreenshots)

A Boolean value that indicates whether to allow screenshots copied to the clipboard during an assessment.

[`var allowsStructuralInput: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsStructuralInput)

A Boolean value that indicates whether to allow Chinese and Japanese structural input during an assessment.

[`var allowsUserScriptExecution: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsUserScriptExecution)

A Boolean value that indicates whether to allow user script execution during an assessment.

[`var allowsVirtualMachine: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/allowsVirtualMachine)

A Boolean value that indicates whether the assessment allows running inside a virtual machine.

[`var configurationsByBinaryExecutable: [AEAssessmentBinaryExecutable : AEAssessmentBinaryExecutableConfiguration]`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/configurationsByBinaryExecutable)

The collection of executable participants available during an assessment, along with their associated configurations.

[`var requiresManagedDevice: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/requiresManagedDevice)

A Boolean value that indicates whether the device must be managed to start an assessment.

[`var requiresReleaseOS: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/requiresReleaseOS)

A Boolean value that indicates whether the device must be running a final customer release of the operating system to start an assessment.

[`var requiresSIP: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/requiresSIP)

A Boolean value that indicates whether System Integrity Protection (SIP) must be enabled to start an assessment.

[`var requiresSingleUser: Bool`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/requiresSingleUser)

A Boolean value that indicates whether only a single user account must be logged in to start an assessment.

[`var requiresUserAccountType: AEUserAccountType`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/requiresUserAccountType)

Specifies the type of user account required to start an assessment.

### Instance Methods

[`func remove(AEAssessmentApplication)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/remove(_:)-313bq)

Removes the availability of a previously allowed app.

[`func remove(AEAssessmentBinaryExecutable)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/remove(_:)-9pylg)

Removes the availability of a previously added executable participant.

[`func setConfiguration(AEAssessmentBinaryExecutableConfiguration, for: AEAssessmentBinaryExecutable)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/setConfiguration(_:for:)-16sed)

Adds an executable participant to the list of participants available during an assessment.

[`func setConfiguration(AEAssessmentParticipantConfiguration, for: AEAssessmentApplication)`](/documentation/AutomaticAssessmentConfiguration/AEAssessmentConfiguration/setConfiguration(_:for:)-2tjgb)

Adds an app to the list of apps available during an assessment.

## Relationships

### Inherits From

[`NSObject-swift.class`](/documentation/ObjectiveC/NSObject-swift.class)

### Conforms To

[`CustomDebugStringConvertible`](/documentation/Swift/CustomDebugStringConvertible)

[`CVarArg`](/documentation/Swift/CVarArg)

[`NSCopying`](/documentation/Foundation/NSCopying)

[`Hashable`](/documentation/Swift/Hashable)

[`NSObjectProtocol`](/documentation/ObjectiveC/NSObjectProtocol)

[`Equatable`](/documentation/Swift/Equatable)

[`CustomStringConvertible`](/documentation/Swift/CustomStringConvertible)

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)