#!/usr/bin/env python3
"""Build and run an own-window-only CaptureHook 1.3 integration host.

No UU processes, permissions or configuration are modified. Captured pixels are
never saved. A false permission preflight skips actual capture without a prompt.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    path.chmod(0o600)


def host_time():
    # Same public monotonic timebase as the hook, sampled in this independent
    # controller before launch and after exit, so constructor events are included.
    return CLOCK()


def run_case(directory, executable, dylib, mode, injected):
    directory.mkdir(mode=0o700)
    session = str(uuid.uuid4())
    log_template = directory / "hook-%p.jsonl"
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("DYLD_", "HOOK_DEMO_"))}
    if injected:
        env.update(DYLD_INSERT_LIBRARIES=str(dylib), HOOK_DEMO_MODE="audit",
                   HOOK_DEMO_SESSION_ID=session, HOOK_DEMO_LOG=str(log_template))
    start = host_time()
    process = subprocess.Popen([str(executable), mode, str(directory / "ready.json"),
                                str(directory / "host-result.json")], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        timed_out = True
        # Only this runner's own child is stopped; never discover or signal UU.
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=2)
    end = host_time()
    summary = {"mode": mode, "injected": injected, "sessionID": session,
               "pid": process.pid, "exitCode": process.returncode,
               "timedOut": timed_out, "stderrBytes": len(stderr), "stdoutBytes": len(stdout)}
    # Raw framework stderr is deliberately not persisted.
    if timed_out or process.returncode != 0:
        summary.update(passed=False, reason="hostFailedOrTimedOut")
        save(directory / "case-summary.json", summary)
        return summary
    ready = json.loads((directory / "ready.json").read_text())
    receipt = json.loads((directory / "host-result.json").read_text())
    if ready["pid"] != process.pid or receipt["pid"] != process.pid:
        raise RuntimeError("own-host PID receipt mismatch")
    expect = {key: ready[key] for key in ("pid", "uid", "processStartSeconds", "processStartMicroseconds", "executable")}
    expect.update(sessionID=session, startHostTime=start, endHostTime=end)
    save(directory / "expect.json", expect)
    summary["host"] = receipt
    summary["passed"] = True
    if mode.startswith("capture") and receipt.get("screenCapturePreflightGranted") and not receipt.get("screenshotRequested"):
        summary.update(passed=False, reason="authorizedCaptureScopeUnavailable")
    if mode == "capture-remove-audio" and receipt.get("screenCapturePreflightGranted"):
        audio_regression_passed = (receipt.get("audioOutputAttached") is True
                                  and receipt.get("audioOutputRemovedBeforeStart") is True
                                  and receipt.get("screenOutputRemoved") is True
                                  and receipt.get("completeScreenFrames", 0) > 0)
        summary["audioRemovalPreservedScreenOutput"] = audio_regression_passed
        if not audio_regression_passed:
            summary.update(passed=False, reason="audioRemovalScreenOutputRegression")
    if injected:
        log = Path(str(log_template).replace("%p", str(process.pid)))
        analysis_path = directory / "analysis.json"
        completed = subprocess.run([sys.executable, str(ROOT / "scripts/analyze-hook-invocations.py"),
                                    "--log", str(log), "--expect", str(directory / "expect.json"),
                                    "--output", str(analysis_path)], capture_output=True, text=True, timeout=15)
        analysis = json.loads(analysis_path.read_text())
        if mode == "load-only" or not receipt.get("screenshotRequested"):
            expected_level = "loaded_only"
        elif receipt["screenshotSucceeded"] or receipt["completeScreenFrames"] > 0:
            expected_level = "frame_callback_observed"
        else:
            expected_level = "capture_entry_observed"
        summary.update(expectedLevel=expected_level, observedLevel=analysis["level"],
                       analyzerExitCode=completed.returncode,
                       passed=summary["passed"] and completed.returncode == 0 and analysis["evidenceUsable"] and analysis["level"] == expected_level)
        # Positive evidence is also checked against independent host callbacks;
        # neither the log nor a module's presence alone supplies that assertion.
        flags = analysis.get("flags", {})
        if receipt.get("screenshotSucceeded") and not flags.get("successfulSnapshotObserved"):
            summary.update(passed=False, reason="successfulOriginalScreenshotCallbackNotLogged")
        if receipt.get("completeScreenFrames", 0) and not flags.get("validScreenFrameObserved"):
            summary.update(passed=False, reason="completeOriginalScreenCallbackNotLogged")
        if receipt.get("completeScreenFrames", 0) and not flags.get("originalCallbackReturnObserved"):
            summary.update(passed=False, reason="originalScreenCallbackReturnNotLogged")
        summary["captureSkipped"] = bool(receipt.get("captureSkipped"))
    save(directory / "case-summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dylib", type=Path, default=ROOT / "build/libCaptureHook-v1.3.dylib")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    output = args.output or ROOT / "artifacts" / ("hook-invocations-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    executable = output / "InvocationProbe"
    subprocess.run(["xcrun", "clang", "-arch", "arm64", "-mmacosx-version-min=14.0", "-fobjc-arc", "-fblocks", "-O1", "-g",
                    str(ROOT / "tests/hook-invocations/InvocationProbe.m"),
                    "-framework", "AppKit", "-framework", "ScreenCaptureKit", "-framework", "CoreGraphics",
                    "-framework", "CoreMedia", "-framework", "CoreVideo", "-framework", "QuartzCore", "-o", str(executable)], check=True)
    subprocess.run(["codesign", "--force", "--sign", "-", str(executable)], check=True, capture_output=True)
    if args.build_only:
        print(json.dumps({"built": str(executable)}))
        return 0
    dylib = args.dylib.resolve(strict=True)
    cases = [run_case(output / "baseline-load-only", executable, dylib, "load-only", False),
             run_case(output / "audit-load-only", executable, dylib, "load-only", True),
             run_case(output / "baseline-capture", executable, dylib, "capture", False),
             run_case(output / "audit-capture", executable, dylib, "capture", True),
             run_case(output / "baseline-remove-audio", executable, dylib, "capture-remove-audio", False),
             run_case(output / "audit-remove-audio", executable, dylib, "capture-remove-audio", True)]
    baseline, audit = cases[2].get("host", {}), cases[3].get("host", {})
    comparable = baseline.get("screenCapturePreflightGranted") is True and audit.get("screenCapturePreflightGranted") is True
    # Compare observable API functionality, not image contents or pixel masking.
    preserved = None
    if comparable:
        preserved = (not baseline.get("screenshotSucceeded") or bool(audit.get("screenshotSucceeded"))) and (
            not baseline.get("completeScreenFrames", 0) or audit.get("completeScreenFrames", 0) > 0)
    summary = {"schemaVersion": 1, "passed": all(case["passed"] for case in cases) and preserved is not False,
               "cases": cases, "baselineAuditCaptureComparable": comparable,
               "baselineSuccessfulCallbacksPreserved": preserved,
               "imagesSaved": False, "permissionRequestsAttempted": False,
               "uuProcessesOrConfigurationChanged": False, "remoteSessionVerified": False,
               "captureBlockingVerified": False,
               "limitations": ["This is an own-window synthetic host integration test in audit mode.",
                               "False preflight skips capture without requesting permission.",
                               "Callback delivery verifies host API behavior, not output pixels, UU integration or blocking.",
                               "Expected process identity comes from native host libproc queries, not hook logs."]}
    save(output / "summary.json", summary)
    print(json.dumps({"passed": summary["passed"], "output": str(output),
                      "captureComparable": comparable, "callbackFunctionalityPreserved": preserved}))
    return 0 if summary["passed"] else 1


QUARTZ = ctypes.CDLL("/System/Library/Frameworks/QuartzCore.framework/QuartzCore")
CLOCK = QUARTZ.CACurrentMediaTime
CLOCK.restype = ctypes.c_double
CLOCK.argtypes = []
if __name__ == "__main__":
    raise SystemExit(main())
