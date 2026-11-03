#!/bin/bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_build_dir="$(mktemp -d "${TMPDIR:-/tmp}/uu-hook-monitor.XXXXXX")"
trap 'rm -rf "$test_build_dir"' EXIT
/usr/bin/xcrun clang -dynamiclib "$project_dir/tests/uu-hook-monitor/fixture.c" \
  -o "$test_build_dir/libCaptureHook-test.dylib"
/usr/bin/xcrun swiftc -swift-version 5 -parse-as-library \
  "$project_dir/Sources/NativeExamDemo/UUHookMonitor.swift" \
  "$project_dir/tests/uu-hook-monitor/MonitorTests.swift" \
  -o "$test_build_dir/UUHookMonitorTests"
"$test_build_dir/UUHookMonitorTests" "$test_build_dir/libCaptureHook-test.dylib"
if [[ "${1:-}" == "--live" ]]; then
  if [[ -z "${2:-}" ]]; then
    printf '%s\n' 'Usage: test-uu-hook-monitor.sh [--live OUTPUT_JSON]' >&2
    exit 64
  fi
  "$test_build_dir/UUHookMonitorTests" --live --output "$2"
fi
