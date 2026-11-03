#!/bin/bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
app_dir="${1:-$project_dir/build/native-guard-$build_stamp/NativeExamHookDemo.app}"
app_dir="$(/usr/bin/python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$app_dir")"
# Never replace a historical or running build. A new directory preserves the
# exact capture-test binaries and signatures used by prior evidence.
if [[ -e "$app_dir" ]]; then
  printf 'Output app must not exist; choose a new .app path.\n' >&2
  exit 1
fi
# Refuse to replace a live binary, including the existing capture-test Demo.
if /bin/ps -axo comm= | /usr/bin/grep -F -x "$app_dir/Contents/MacOS/NativeExamHookDemo" >/dev/null; then
  printf 'The target app is running; choose a different output .app path.\n' >&2
  exit 1
fi
build_tmp="$(mktemp -d "${TMPDIR:-/tmp}/exam-integrity-build.XXXXXX")"
trap 'rm -rf "$build_tmp"' EXIT
team_id="${EXAM_EXPECTED_TEAM_ID:-}"
if [[ -n "$team_id" && ! "$team_id" =~ ^[A-Z0-9]{10}$ ]]; then
  printf 'EXAM_EXPECTED_TEAM_ID must be a 10-character Apple Team ID.\n' >&2
  exit 1
fi
team_literal=nil
if [[ -n "$team_id" ]]; then team_literal="\"$team_id\""; fi
cat > "$build_tmp/IntegrityBuildPolicy.swift" <<POLICY
enum IntegrityBuildPolicy {
    static let bundleID = "local.examcapture.hook.native"
    static let expectedTeamID: String? = $team_literal
}
POLICY
swift_flags=(-D GUARDED_EXAM)
if [[ "${EXAM_ENABLE_GUARD_TESTING:-0}" == "1" ]]; then swift_flags+=(-D GUARD_TESTING); fi
if [[ "${EXAM_ENABLE_LEGACY_HOOK_DEMO:-0}" == "1" ]]; then swift_flags+=(-D LEGACY_HOOK_TESTING); fi
mkdir -p "$app_dir/Contents/MacOS"
/usr/bin/xcrun clang -O2 -target arm64-apple-macos13.0 -c \
  "$project_dir/Sources/NativeExamDemo/RuntimeImages.c" -o "$build_tmp/RuntimeImages.o"
/usr/bin/xcrun swiftc -swift-version 5 -O -target arm64-apple-macos13.0 "${swift_flags[@]}" \
  -framework AppKit -framework CoreGraphics -framework QuartzCore -framework Security -framework CryptoKit \
  -import-objc-header "$project_dir/Sources/NativeExamDemo/RuntimeImages.h" \
  "$project_dir/Sources/NativeExamDemo/"*.swift \
  "$build_tmp/IntegrityBuildPolicy.swift" "$build_tmp/RuntimeImages.o" \
  -o "$app_dir/Contents/MacOS/NativeExamHookDemo"
cat > "$app_dir/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>local.examcapture.hook.native</string>
  <key>CFBundleName</key><string>NativeExamHookDemo</string>
  <key>CFBundleDisplayName</key><string>考试进程管控验证 Demo</string>
  <key>CFBundleExecutable</key><string>NativeExamHookDemo</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>2.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSPrincipalClass</key><string>NSApplication</string>
</dict></plist>
PLIST
/usr/bin/codesign --force --sign "${EXAM_SIGN_IDENTITY:--}" "$app_dir"
printf '%s\n' "$app_dir"
