#!/usr/bin/env python3
"""Test v1.4 wrappers on synthetic content and NULL streams; never capture or run UU."""
import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    library, output = args.library.resolve(), args.output.resolve()
    if not library.is_file():
        parser.error("--library must exist")
    output.mkdir(parents=True, exist_ok=False)
    project = Path(__file__).resolve().parents[1]
    host = output / "DiagnosticProbe"
    subprocess.run(["xcrun", "clang", "-arch", "arm64", "-mmacosx-version-min=14.0", "-fobjc-arc", "-fblocks",
                    "-Wno-deprecated-declarations", "-framework", "Foundation", "-framework", "ScreenCaptureKit",
                    "-framework", "CoreGraphics", str(project / "tests/hook-invocations/DiagnosticProbe.m"),
                    "-o", str(host)], check=True)
    spec = importlib.util.spec_from_file_location("hook_analysis", project / "scripts/analyze-hook-invocations.py")
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    clock = ctypes.CDLL("/System/Library/Frameworks/QuartzCore.framework/QuartzCore").CACurrentMediaTime
    clock.restype = ctypes.c_double
    results = {}
    for mode in ("shareable", "display-control"):
        for audit in (False, True):
            name = mode + ("-audit" if audit else "-baseline")
            log = output / (name + ".jsonl")
            session = str(uuid.uuid4())
            env = {key: value for key, value in os.environ.items() if not key.startswith(("DYLD_", "HOOK_DEMO_"))}
            if audit:
                env.update(HOOK_DEMO_MODE="audit", HOOK_DEMO_LOG=str(log), HOOK_DEMO_SESSION_ID=session)
                if mode == "display-control":
                    env["DYLD_INSERT_LIBRARIES"] = str(library)
            start = clock()
            proc = subprocess.run([str(host), mode, str(library) if audit and mode == "shareable" else "-"],
                                  env=env, capture_output=True, text=True, timeout=15)
            end = clock()
            if proc.returncode:
                raise RuntimeError(f"{name}: fixture exit {proc.returncode}")
            receipt = json.loads(proc.stdout)
            (output / (name + "-receipt.json")).write_text(json.dumps(receipt, indent=2) + "\n")
            assert receipt["passed"] and not receipt["screenCapturePerformed"] and not receipt["realScreenEnumerationPerformed"]
            result = {"passed": True, "receipt": receipt}
            if audit:
                expect = {key: receipt[key] for key in ("pid", "uid", "processStartSeconds", "processStartMicroseconds", "executable")}
                expect.update(sessionID=session, startHostTime=start, endHostTime=end, hookVersion="1.4")
                (output / (name + "-expect.json")).write_text(json.dumps(expect, indent=2) + "\n")
                analysis = analyzer.analyze(log.read_bytes(), expect)
                (output / (name + "-analysis.json")).write_text(json.dumps(analysis, indent=2) + "\n")
                assert analysis["evidenceUsable"] and analysis["level"] == "loaded_only", analysis["issues"]
                assert not analysis["flags"]["captureEntryObserved"] and not analysis["flags"]["frameEvidenceObserved"]
                if mode == "shareable":
                    assert analysis["counts"]["shareableContentRequests"] == 4
                    assert analysis["counts"]["shareableContentResults"] == 3
                    assert analysis["counts"]["shareableContentSuccesses"] == 1
                    assert analysis["counts"]["shareableContentFailures"] == 2
                    assert analysis["coverage"]["pendingShareableContentResults"] == 1
                    # Only counts and errors survive; mock object contents never enter the log.
                    assert b"synthetic-window" not in log.read_bytes() and b"synthetic-app" not in log.read_bytes()
                else:
                    assert analysis["counts"]["displayStreamControlCalls"] == 2
                    assert analysis["counts"]["displayStreamControlFailures"] == 2
                    rows = [json.loads(line) for line in log.read_bytes().splitlines()]
                    returns = {row["api"]: row["returnCode"] for row in rows if row["event"] == "display_stream_control_result"}
                    assert returns == {"CGDisplayStreamStart": receipt["startReturnCode"], "CGDisplayStreamStop": receipt["stopReturnCode"]}
                result["analysisLevel"] = analysis["level"]
            results[name] = result
        baseline, audit_result = results[mode + "-baseline"]["receipt"], results[mode + "-audit"]["receipt"]
        keys = ("requests", "callbacks", "argumentPassThrough", "objectIdentityPreserved", "errorIdentityPreserved", "nilCompletionPassedThrough") if mode == "shareable" else ("startReturnCode", "stopReturnCode")
        assert all(baseline[key] == audit_result[key] for key in keys)
    summary = {"passed": True, "caseCount": len(results), "cases": results,
               "scope": "Synthetic SCShareableContent method and NULL CGDisplayStream arguments only",
               "capturePerformed": False, "realScreenEnumerationPerformed": False, "uuOperationPerformed": False,
               "validStreamLifecycleVerified": False, "realUUInvocationVerified": False}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"passed": True, "caseCount": len(results), "capturePerformed": False, "summary": str(output / "summary.json")}))


if __name__ == "__main__":
    main()
