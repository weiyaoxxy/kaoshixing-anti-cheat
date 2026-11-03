#!/usr/bin/env python3
"""Verify complete JSON lines under own-process/own-thread concurrency; no capture."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

project = Path(__file__).resolve().parents[1]
library = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
output.mkdir(parents=True, exist_ok=False)
host = output / "ConcurrentLog"
subprocess.run(["xcrun", "clang", "-fobjc-arc", "-fblocks", "-framework", "Foundation",
                str(project / "tests/hook-invocations/ConcurrentLog.m"), "-o", str(host)], check=True)
env = {k: v for k, v in os.environ.items() if not k.startswith(("DYLD_", "HOOK_DEMO_"))}
env.update(DYLD_INSERT_LIBRARIES=str(library), HOOK_DEMO_MODE="audit", HOOK_DEMO_SESSION_ID=str(uuid.uuid4()))
env["HOOK_DEMO_LOG"] = str(output / "single.jsonl")
subprocess.run([str(host)], env=env, check=True, timeout=30)
single = [json.loads(line) for line in (output / "single.jsonl").read_bytes().splitlines()]
assert [row["sequence"] for row in single] == list(range(1, len(single) + 1))
assert all(row["priorLogWriteFailures"] == 0 for row in single)
assert sum(row["event"] == "log_self_test" for row in single) == 200
env["HOOK_DEMO_LOG"] = str(output / "shared.jsonl")
hosts = [subprocess.Popen([str(host)], env=env) for _ in range(8)]
try:
    for process in hosts:
        assert process.wait(timeout=30) == 0
finally:
    for process in hosts:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
raw = (output / "shared.jsonl").read_bytes()
assert raw.endswith(b"\n")
shared = [json.loads(line) for line in raw.splitlines()]
assert len({row["pid"] for row in shared}) == 8
assert all(type(row["identityAvailable"]) is bool and row["identityAvailable"] for row in single + shared)
assert all(row["event"] not in ("capture_call", "capture_result", "sck_stream_frame", "display_stream_frame") for row in single + shared)
summary = {"singleProcessThreadedRecords": len(single), "singleSequenceComplete": True,
           "sharedProcesses": 8, "sharedRecords": len(shared), "allLinesValidJSON": True,
           "sharedContentionReported": any(row["priorLogWriteFailures"] > 0 for row in shared),
           "sharedLossPossible": True, "sharedLogSuitableForSingleProcessEvidence": False,
           "capturePerformed": False, "uuModified": False, "passed": True}
(output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
