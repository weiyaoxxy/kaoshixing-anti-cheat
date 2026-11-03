#!/bin/zsh
set -euo pipefail
cd "${0:A:h}/.."
mkdir -p build
xcrun clang -c Sources/CaptureProbe/LegacyCapture.c -o build/LegacyCapture.o -mmacosx-version-min=12.3
xcrun swiftc -parse-as-library -swift-version 5 -O -target arm64-apple-macos13.0 -import-objc-header Sources/CaptureProbe/LegacyCapture.h Sources/CaptureProbe/CaptureProbe.swift build/LegacyCapture.o -o build/CaptureProbe -framework AppKit -framework ScreenCaptureKit -framework CoreImage -framework ImageIO -framework UniformTypeIdentifiers
codesign --force --sign - --identifier com.examcapture.probe build/CaptureProbe
print "Built: $PWD/build/CaptureProbe"
