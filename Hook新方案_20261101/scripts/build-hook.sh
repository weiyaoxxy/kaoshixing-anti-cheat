#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/build"
OUTPUT="${1:-$ROOT/build/libCaptureHook-v1.4.dylib}"
if [[ -e "$OUTPUT" || -L "$OUTPUT" ]]; then
  printf '%s\n' "Refusing to overwrite an existing Hook artifact: $OUTPUT" >&2
  exit 64
fi
xcrun clang -arch arm64 -mmacosx-version-min=14.0 -fobjc-arc -fblocks -O1 -g -dynamiclib \
  -Wno-deprecated-declarations -Wno-unguarded-availability-new \
  "$ROOT/Sources/CaptureHook/CaptureHook.m" \
  -framework Foundation -framework AppKit -framework ScreenCaptureKit \
  -framework CoreGraphics -framework CoreMedia -framework CoreVideo -framework IOSurface -framework QuartzCore \
  -install_name @rpath/libCaptureHook-v1.4.dylib -o "$OUTPUT"
# Local development identity only. Does not resign or modify any target app.
codesign --force --sign - "$OUTPUT"
printf '%s\n' "$OUTPUT"
