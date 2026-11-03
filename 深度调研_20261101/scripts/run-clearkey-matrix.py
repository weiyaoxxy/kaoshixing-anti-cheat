#!/usr/bin/env python3
from pathlib import Path
import datetime
import json
import subprocess
import time

root = Path(__file__).resolve().parents[1]
out = root / "artifacts" / ("clearkey-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
out.mkdir(parents=True)
(root / "research/clearkey/latest-run.txt").write_text(str(out) + "\n")
for name, media, allow in [("plain-false", "plain", False), ("sample-aes-false", "encrypted", False), ("sample-aes-true", "encrypted", True)]:
    case = out / name
    case.mkdir()
    args = [str(root / "build/ClearKeyDemo.app/Contents/MacOS/ClearKeyDemo"), "--url", f"http://127.0.0.1:8766/{media}/stream.m3u8",
            "--allow-capture", str(allow).lower(), "--duration", "24", "--output", str(case)]
    with (case / "demo-console.log").open("w") as log:
        process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, cwd=root)
        state = {}
        for _ in range(100):
            time.sleep(0.1)
            try:
                state = json.loads((case / "player-state.json").read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                continue
            if state.get("isReadyForDisplay") and state.get("currentTimeSeconds", 0) > 1:
                break
            if state.get("itemError") or process.poll() is not None:
                break
        ready = state.get("isReadyForDisplay", False) and state.get("currentTimeSeconds", 0) > 1
        (case / "state-before-capture.json").write_text(json.dumps({"playbackReadyAndAdvanced": ready, "state": state}, indent=2) + "\n")
        if state.get("windowID"):
            result = subprocess.run(["/usr/sbin/screencapture", "-x", "-l", str(state["windowID"]), str(case / "system-window.png")], capture_output=True, text=True, timeout=10)
            (case / "system-capture.json").write_text(json.dumps({"returncode": result.returncode, "stderr": result.stderr}, indent=2) + "\n")
            with (case / "probe-console.log").open("w") as probe_log:
                subprocess.run([str(root.parent / "build/CaptureProbe"), "--window-id", str(state["windowID"]), "--duration", "2", "--output", str(case / "capture")],
                               stdout=probe_log, stderr=subprocess.STDOUT, check=True, timeout=30)
        process.wait(timeout=30)
    files = sorted(case.glob("*.png")) + sorted((case / "capture").rglob("*.png"))
    with (case / "media-inspection.jsonl").open("w") as report:
        subprocess.run([str(root.parent / "build/InspectMedia")] + [str(p) for p in files], stdout=report, check=True, timeout=120)
    print(name, "playbackReadyAndAdvanced=", ready, case, flush=True)
print(out, flush=True)
