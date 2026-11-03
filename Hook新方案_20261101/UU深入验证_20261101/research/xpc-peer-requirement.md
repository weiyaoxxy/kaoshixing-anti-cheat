<!--
{
  "availability" : [
    "macOS: 13.0.0 -"
  ],
  "documentType" : "symbol",
  "framework" : "Foundation",
  "identifier" : "/documentation/Foundation/NSXPCConnection/setCodeSigningRequirement(_:)",
  "metadataVersion" : "0.1.0",
  "role" : "Instance Method",
  "symbol" : {
    "kind" : "Instance Method",
    "modules" : [
      "Foundation"
    ],
    "preciseIdentifier" : "c:objc(cs)NSXPCConnection(im)setCodeSigningRequirement:"
  },
  "title" : "setCodeSigningRequirement(_:)"
}
-->

# setCodeSigningRequirement(_:)

Sets the code signing requirement for this connection.

```
func setCodeSigningRequirement(_ requirement: String)
```

## Parameters

`requirement`

A string that describes requirements expected of the connection peer. See [Code Signing Guide](https://developer.apple.com/library/archive/documentation/Security/Conceptual/CodeSigningGuide/) for more information on the code signing format.

## Discussion

Use this method to enforce a code-signing requirement on the peer process of an XPC connection.

The following example shows how a client can ensure that the XPC service on the other end of a connection has a specific entitlement.

```objc
NSXPCConnection *c = [[NSXPCConnection alloc] initWithServiceName:@"com.example.ExampleService"];
c.remoteObjectInterface = getServerInterface();    
[c setCodeSigningRequirement:@"entitlement [com.example.testentitlement] exists"];
[c resume];

[[c remoteObjectProxyWithErrorHandler:^(NSError *error) {
    // If there is a code signing error, this block receives NSXPCConnectionCodeSigningRequirementFailure here.
}] myMessageWithReply:^(BOOL arg) {
    // Handle success case here.
}];
```

Calling this method with a malformed `requirement` results in a fatal error in Swift, or throws an exception in Objective-C. If new messages don’t match the requirement, the connection becomes invalidated.

Call this method before calling [`resume()`](/documentation/Foundation/NSXPCConnection/resume()), since it’s an XPC error to call this method more than once.

---

Copyright &copy; 2026 Apple Inc. All rights reserved. | [Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)