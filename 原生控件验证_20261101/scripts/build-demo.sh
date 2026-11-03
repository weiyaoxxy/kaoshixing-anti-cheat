#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
APP="build/NativeControlDemo.app"
mkdir -p "$APP/Contents/MacOS"
xcrun swiftc -swift-version 5 -O -target arm64-apple-macosx13.0 Sources/NativeControlDemo/main.swift -o "$APP/Contents/MacOS/NativeControlDemo" -framework AppKit -framework AVFoundation -framework CoreMedia -framework CoreVideo -framework QuartzCore
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>NativeControlDemo</string>
<key>CFBundleIdentifier</key><string>local.examcapture.nativecontrols</string>
<key>CFBundleName</key><string>NativeControlDemo</string>
<key>CFBundleVersion</key><string>1</string>
<key>CFBundleShortVersionString</key><string>0.1</string>
<key>NSHighResolutionCapable</key><true/>
<key>LSMinimumSystemVersion</key><string>13.0</string>
</dict></plist>
PLIST
codesign --force --sign - "$APP"
printf 'Built %s\n' "$APP"
