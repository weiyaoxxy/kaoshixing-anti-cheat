#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
app="build/ClearKeyDemo.app"
mkdir -p "$app/Contents/MacOS"
xcrun swiftc -swift-version 5 -O -target arm64-apple-macos14.0 Sources/ClearKeyDemo/main.swift -o "$app/Contents/MacOS/ClearKeyDemo" -framework AppKit -framework AVFoundation -framework CoreImage
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.examcapture.clearkey</string>
<key>CFBundleName</key><string>ClearKeyDemo</string>
<key>CFBundleExecutable</key><string>ClearKeyDemo</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PLIST
codesign --force --sign - "$app"
printf '%s\n' "$app"
