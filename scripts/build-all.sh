#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/build-demo.sh
./scripts/build-probe.sh
xcrun swiftc -swift-version 5 -O scripts/inspect-media.swift -o build/InspectMedia -framework AppKit -framework AVFoundation -framework Vision
printf 'Ready: open build/ExamCaptureDemo.app; python3 scripts/run-matrix.py\n'
