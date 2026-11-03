#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x build/ExamCaptureDemo.app/Contents/MacOS/ExamCaptureDemo ]]; then
  ./scripts/build-demo.sh
fi
open build/ExamCaptureDemo.app
