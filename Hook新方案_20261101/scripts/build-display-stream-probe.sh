#!/bin/bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$project_dir/build"
/usr/bin/xcrun clang -arch arm64 -mmacosx-version-min=13.0 -fobjc-arc -fblocks -O1 -g \
  -Wall -Wextra -Wno-deprecated-declarations -Wno-unused-parameter \
  "$project_dir/Sources/DisplayStreamProbe/main.m" \
  -framework Foundation -framework CoreGraphics -framework CoreVideo -framework IOSurface -framework ImageIO \
  -o "$project_dir/build/DisplayStreamProbe"
/usr/bin/codesign --force --sign - "$project_dir/build/DisplayStreamProbe"
printf '%s\n' "$project_dir/build/DisplayStreamProbe"
