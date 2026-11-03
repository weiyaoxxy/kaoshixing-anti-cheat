#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/build"
xcrun clang -arch arm64 -mmacosx-version-min=11.0 -std=c11 -Wall -Wextra -Werror -O2 \
  -dynamiclib "$ROOT/Sources/LoadWitness/LoadWitness.c" \
  -install_name @rpath/libLoadWitness.dylib -o "$ROOT/build/libLoadWitness.dylib"
xcrun clang -arch arm64 -mmacosx-version-min=11.0 -std=c11 -Wall -Wextra -Werror -O2 \
  "$ROOT/Sources/LoadWitness/LoadWitnessHost.c" -o "$ROOT/build/LoadWitnessHost"
codesign --force --sign - "$ROOT/build/libLoadWitness.dylib"
codesign --force --sign - "$ROOT/build/LoadWitnessHost"
printf '%s\n' "$ROOT/build/libLoadWitness.dylib" "$ROOT/build/LoadWitnessHost"
