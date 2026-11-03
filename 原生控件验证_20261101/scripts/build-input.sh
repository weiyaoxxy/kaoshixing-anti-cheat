#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
xcrun swiftc -swift-version 5 -O -target arm64-apple-macos13.0 Sources/NativeInputProbe.swift -o build/NativeInputProbe -framework AppKit -framework ApplicationServices -framework CoreGraphics
codesign --force --sign - --identifier local.examcapture.nativeinput build/NativeInputProbe
printf 'Built NativeInputProbe\n'
