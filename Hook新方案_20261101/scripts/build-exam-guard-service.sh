#!/bin/bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
output="${1:?Usage: build-exam-guard-service.sh NEW_OUTPUT_PATH}"
inventory="${2:?Specify the validated native inventory binary}"
policy="${3:-$project_dir/Sources/RemoteProcessInventory/policy.json}"
if [[ -e "$output" ]]; then echo 'Refusing to overwrite an existing worker.' >&2; exit 1; fi
mkdir -p "$(dirname "$output")"
build_tmp="$(mktemp -d "${TMPDIR:-/tmp}/exam-guard-build.XXXXXX")"
trap 'rm -rf "$build_tmp"' EXIT
/usr/bin/python3 - "$inventory" "$policy" "$build_tmp/EmbeddedInventory.swift" <<'PY'
import base64, hashlib, json, pathlib, sys, tempfile, os
binary, policy, output = map(pathlib.Path, sys.argv[1:])
data = policy.read_bytes()
parsed = json.loads(data)
if parsed.get('testOnly') is True or parsed.get('testPolicy') is True or parsed.get('testPolicyEnabled') is True:
    raise SystemExit('Refusing to embed a test identity policy')
if parsed.get('schemaVersion') != 2 or set(parsed.get('vendors', {})) != {'uu', 'todesk', 'sunlogin'}:
    raise SystemExit('Expected v2 production vendor catalogue')
binary_data = binary.read_bytes()
stage = pathlib.Path(tempfile.mkdtemp(prefix='exam-remote-inventory-', dir='/private/var/tmp'))
staged = stage / 'Inventory'
staged.write_bytes(binary_data)
staged.chmod(0o700)
output.write_text('enum EmbeddedInventory {\n'
    ' static let source = ' + json.dumps(str(staged), ensure_ascii=False) + '\n'
    ' static let sha256 = "' + hashlib.sha256(binary_data).hexdigest() + '"\n'
    ' static let policyBase64 = "' + base64.b64encode(data).decode() + '"\n}\n')
PY
/usr/bin/xcrun swiftc -swift-version 5 -O -target arm64-apple-macos13.0 \
  -framework Foundation -framework Security -framework CryptoKit \
  "$project_dir/Sources/ExamGuardService/main.swift" "$build_tmp/EmbeddedInventory.swift" -o "$output"
/usr/bin/codesign --sign - --options runtime "$output"
printf '%s\n' "$output"
