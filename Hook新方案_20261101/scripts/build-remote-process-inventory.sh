#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# -gt 1 ]]; then
  printf '%s\n' 'Usage: build-remote-process-inventory.sh [NEW_OUTPUT_PATH]' >&2
  exit 64
fi
if [[ $# -eq 1 ]]; then
  OUTPUT="$1"
else
  mkdir -p "$ROOT/build"
  REMOTE_INVENTORY_BUILD_DIR="$(mktemp -d "$ROOT/build/remote-process-inventory.XXXXXX")"
  OUTPUT="$REMOTE_INVENTORY_BUILD_DIR/RemoteProcessInventory"
fi
if [[ -e "$OUTPUT" || -L "$OUTPUT" || -e "$(dirname "$OUTPUT")/policy.json" || -L "$(dirname "$OUTPUT")/policy.json" ]]; then
  printf '%s\n' "Refusing to overwrite an existing inventory artifact: $OUTPUT" >&2
  exit 64
fi
mkdir -p "$(dirname "$OUTPUT")"
xcrun swiftc -O -target arm64-apple-macosx13.0 \
  "$ROOT/Sources/RemoteProcessInventory/main.swift" \
  -framework Foundation -framework QuartzCore -framework Security -o "$OUTPUT"
cp "$ROOT/Sources/RemoteProcessInventory/policy.json" "$(dirname "$OUTPUT")/policy.json"
printf '%s\n' "$OUTPUT"
