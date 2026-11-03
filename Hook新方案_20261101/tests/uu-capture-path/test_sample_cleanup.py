#!/usr/bin/env python3
"""Exercise sample SIGINT cleanup only against a child heartbeat fixture we create.

Accepts no target PID, sends no SIGCONT, and never inspects or controls UU.
Raw sample output exists only in a private temporary directory and is discarded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE.parents[2] / "artifacts"
ENVIRONMENT = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"}


def heartbeat_rows(path):
    if not path.exists():
        return []
    values = []
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) == 2 and all(field.isdigit() for field in fields):
            values.append(tuple(map(int, fields)))
    return values


def count(path):
    rows = heartbeat_rows(path)
    return rows[-1][0] if rows else 0


def stop_owned(child):
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if os.getuid() != os.geteuid() or os.geteuid() == 0:
        parser.error("Run as the ordinary logged-in user without sudo.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output or ARTIFACTS / ("sample-cleanup-fixture-" + stamp)).resolve()
    if not output.is_relative_to(ARTIFACTS.resolve()) or output == ARTIFACTS.resolve():
        parser.error("Output must be a new child of the workspace artifacts directory.")
    os.umask(0o077)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    binary = output / "SampleCleanupHeartbeat"
    heartbeat = output / "heartbeat.txt"
    result = {
        "schemaVersion": 1,
        "startedAtUTC": datetime.now(timezone.utc).isoformat(),
        "status": "incomplete",
        "scope": "self_created_child_fixture_only",
        "darwinRelease": os.uname().release,
        "machineArchitecture": os.uname().machine,
        "sampleExecutableSHA256": hashlib.sha256(Path('/usr/bin/sample').read_bytes()).hexdigest(),
        "requestedSampleSeconds": 20,
        "sampleIntervalMilliseconds": 5,
        "interruptWaitBudgetSeconds": 8,
        "sigcontSent": False,
        "uuInspectedOrModified": False,
        "rawSampleRetained": None,
        "limitations": [
            "Tests only this sample version, OS and fixture interruption path.",
            "A continuing heartbeat does not prove every target thread always resumes.",
            "Does not establish safety for UU, other software, SIGKILL or collector crashes.",
        ],
    }
    fixture = sampler = None
    temporary_path = None
    try:
        build = subprocess.run(
            ["/usr/bin/xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-O2",
             str(HERE / "SampleCleanupHeartbeat.c"), "-o", str(binary)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENVIRONMENT, timeout=30,
        )
        result["fixtureBuildExitCode"] = build.returncode
        if build.returncode:
            raise RuntimeError("fixtureBuildFailed")
        fixture = subprocess.Popen([str(binary), str(heartbeat)], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, env=ENVIRONMENT, start_new_session=True)
        result["fixturePID"] = fixture.pid
        deadline = time.monotonic() + 3
        while count(heartbeat) < 10 and time.monotonic() < deadline and fixture.poll() is None:
            time.sleep(0.02)
        result["heartbeatBeforeSample"] = count(heartbeat)
        if result["heartbeatBeforeSample"] < 10:
            raise RuntimeError("fixtureNotHealthy")
        with tempfile.TemporaryDirectory(prefix="sample-cleanup-self-fixture-") as temporary:
            temporary_path = Path(temporary)
            raw = temporary_path / "sample.txt"
            diagnostics = temporary_path / "diagnostics.txt"
            raw.touch(mode=0o600)
            with diagnostics.open("xb") as diagnostic_stream:
                sample_started = time.monotonic()
                sampler = subprocess.Popen(
                    ["/usr/bin/sample", str(fixture.pid), "20", "5", "-file", str(raw)],
                    stdout=diagnostic_stream, stderr=diagnostic_stream,
                    env=ENVIRONMENT, start_new_session=True,
                )
                result["samplePID"] = sampler.pid
                banner_deadline = time.monotonic() + 5
                banner = False
                while time.monotonic() < banner_deadline and sampler.poll() is None:
                    data = diagnostics.read_bytes()[:65536]
                    if b"Sampling process" in data:
                        banner = True
                        break
                    time.sleep(0.02)
                result["samplingStartBannerObserved"] = banner
                if not banner:
                    raise RuntimeError("samplingStartNotObserved")
                # Give the bounded sampling loop time to run before interruption.
                time.sleep(0.6)
                if sampler.poll() is not None:
                    raise RuntimeError("samplerExitedBeforeInterrupt")
                result["heartbeatImmediatelyBeforeSIGINT"] = count(heartbeat)
                sent = time.monotonic()
                sampler.send_signal(signal.SIGINT)
                result["sampleSIGINTSent"] = True
                try:
                    sampler.wait(timeout=8)
                    result["sampleExitedWithinInterruptBudget"] = True
                except subprocess.TimeoutExpired:
                    result["sampleExitedWithinInterruptBudget"] = False
                    # This is only our own fixture: allow its natural bounded run
                    # to finish before the final owned-child cleanup below.
                    sampler.wait(timeout=max(1, 30 - (time.monotonic() - sample_started)))
                result["sampleExitCode"] = sampler.returncode
                result["sampleInterruptToExitSeconds"] = round(time.monotonic() - sent, 6)
                result["sampleTotalElapsedSeconds"] = round(time.monotonic() - sample_started, 6)
                sample_text = raw.read_text(encoding="utf-8")
                process_header = re.search(r"^Process:\s+.+?\s+\[([0-9]+)\]\s*$", sample_text, re.M)
                path_header = re.search(r"^Path:\s+(.+?)\s*$", sample_text, re.M)
                result["sampleHeaderPIDMatchesFixture"] = bool(
                    process_header and int(process_header[1]) == fixture.pid)
                result["sampleHeaderPathMatchesExactly"] = bool(
                    path_header and path_header[1] == str(binary))
                # sample may anonymize paths inside the user's home directory.
                # The fixture is our own child, not an arbitrary caller-supplied
                # PID; keep the weaker path check explicit rather than claiming
                # an exact original-executable identity match.
                result["sampleHeaderBasenameMatchesFixture"] = bool(
                    path_header and Path(path_header[1]).name == binary.name)
                result["sampleHeaderPathContainsRedaction"] = bool(
                    path_header and ("/USER/" in path_header[1] or "*" in path_header[1]))
                result["sampleCallGraphObserved"] = "\nCall graph:\n" in sample_text
                result["rawSampleBytes"] = raw.stat().st_size
                after_exit = count(heartbeat)
                observe_deadline = time.monotonic() + 1.5
                while time.monotonic() < observe_deadline and fixture.poll() is None:
                    time.sleep(0.05)
                end_count = count(heartbeat)
                result["heartbeatAtSampleExit"] = after_exit
                result["heartbeatAfterObservation"] = end_count
                result["postExitHeartbeatProgress"] = end_count - after_exit
                result["fixtureAliveBeforeCleanup"] = fixture.poll() is None
                rows = heartbeat_rows(heartbeat)
                result["maximumObservedHeartbeatGapMilliseconds"] = round(
                    max((b[1] - a[1] for a, b in zip(rows, rows[1:])), default=0) / 1_000_000, 3)
                passed = (result["sampleExitedWithinInterruptBudget"] and
                          result["sampleTotalElapsedSeconds"] < result["requestedSampleSeconds"] and
                          result["sampleHeaderPIDMatchesFixture"] and
                          result["sampleHeaderBasenameMatchesFixture"] and
                          result["sampleCallGraphObserved"] and
                          result["fixtureAliveBeforeCleanup"] and
                          result["postExitHeartbeatProgress"] >= 10)
                result["status"] = "passed" if passed else "failed"
        result["rawSampleRetained"] = temporary_path.exists()
    except BaseException as error:
        result["status"] = "failed"
        result["failureType"] = type(error).__name__
        if isinstance(error, RuntimeError):
            result["failureCode"] = str(error)
    finally:
        cleanup_errors = []
        for name, child in (("sampler", sampler), ("fixture", fixture)):
            try:
                stop_owned(child)
                result[name + "Stopped"] = child is None or child.poll() is not None
            except BaseException as error:
                cleanup_errors.append(name + ":" + type(error).__name__)
        if temporary_path is not None:
            result["rawSampleRetained"] = temporary_path.exists()
        if cleanup_errors or result.get("rawSampleRetained") is True:
            result["status"] = "failed"
        result["cleanupErrors"] = cleanup_errors
        result["endedAtUTC"] = datetime.now(timezone.utc).isoformat()
        with (output / "summary.json").open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    print(json.dumps({"status": result["status"], "output": str(output),
                      "sampleExitCode": result.get("sampleExitCode"),
                      "postExitHeartbeatProgress": result.get("postExitHeartbeatProgress"),
                      "rawSampleRetained": result["rawSampleRetained"]}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
