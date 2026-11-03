#!/bin/bash
set -euo pipefail
WITNESS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$WITNESS_ROOT/build"
xcrun clang -arch arm64 -mmacosx-version-min=11.0 -std=c11 -Wall -Wextra -Werror -O2 \
  -dynamiclib "$WITNESS_ROOT/Sources/LoadWitnessV2/LoadWitnessV2.c" \
  -install_name @rpath/libLoadWitness-v2.dylib -o "$WITNESS_ROOT/build/libLoadWitness-v2.dylib"
xcrun clang -arch arm64 -mmacosx-version-min=11.0 -std=c11 -Wall -Wextra -Werror -O2 \
  "$WITNESS_ROOT/Sources/LoadWitnessV2/LoadWitnessV2Host.c" \
  -o "$WITNESS_ROOT/build/LoadWitnessV2Host-runtime"
codesign --force --sign - "$WITNESS_ROOT/build/libLoadWitness-v2.dylib"
codesign --force --sign - --options runtime \
  --entitlements "$WITNESS_ROOT/Sources/LoadWitnessV2/runtime-entitlements.plist" \
  "$WITNESS_ROOT/build/LoadWitnessV2Host-runtime"
printf '%s\n' "$WITNESS_ROOT/build/libLoadWitness-v2.dylib" "$WITNESS_ROOT/build/LoadWitnessV2Host-runtime"
