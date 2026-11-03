#!/usr/bin/env python3
"""Read-only validation of externally scoped CaptureHook 1.3/1.4 schema-2 evidence.

This never discovers a current process or derives its expectation from the log.
Local log evidence does not authenticate a remote session or prove blocking.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import uuid

MAX_LOG_BYTES = 32 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_RECORDS = 100_000
HOOK_VERSIONS = ("1.3", "1.4")
SHAREABLE_CONTENT_API = "SCShareableContent.getShareableContentExcludingDesktopWindows:onScreenWindowsOnly:completionHandler:"
DISPLAY_CONTROL_APIS = ("CGDisplayStreamStart", "CGDisplayStreamStop")
V14_DIAGNOSTIC_EVENTS = {
    "shareable_content_request", "shareable_content_result",
    "display_stream_control_call", "display_stream_control_result",
}
API_OPERATIONS = {
    "CGWindowListCreateImage": "snapshot_request",
    "CGDisplayCreateImage": "snapshot_request",
    "SCScreenshotManager.captureImage": "snapshot_request",
    "SCScreenshotManager.captureImageInRect": "snapshot_request",
    "SCScreenshotManager.captureSampleBuffer": "snapshot_request",
    "CGDisplayStreamCreate": "stream_create",
    "CGDisplayStreamCreateWithDispatchQueue": "stream_create",
    "SCStream.init": "stream_create",
    "SCStream.addStreamOutput": "stream_setup",
    "SCStream.removeStreamOutput": "stream_setup",
    "SCStream.startCapture": "stream_start",
    "SCStream.stopCapture": "stream_stop",
    "SCStream.updateContentFilter": "stream_update",
    "SCStream.updateConfiguration": "stream_update",
}
DIAGNOSTIC_EVENTS = {
    "hook_unavailable", "original_symbol_missing", "display_stream_geometry",
    "display_stream_passthrough", "display_stream_redacted", "redaction_failed",
    "image_result", "sample_result", "sck_stream_result", "redacted", "passthrough",
    "log_self_test", "capture_setup_result", "capture_stop_result", "capture_update_result",
}


class EvidenceError(ValueError):
    """Contains an allowlisted error code, never raw input text."""


def require(condition, code):
    if not condition:
        raise EvidenceError(code)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def number(value, minimum=0):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= minimum
    except OverflowError:
        return False


def identifier(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and all(ord(c) >= 32 for c in value)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise EvidenceError("duplicateJSONKey")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(EvidenceError("nonfiniteJSONNumber")))
    except EvidenceError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise EvidenceError("invalidJSON") from None


def validate_expectation(expect):
    require(isinstance(expect, dict), "expectationNotObject")
    require(identifier(expect.get("sessionID")), "invalidExpectedSessionID")
    require(integer(expect.get("pid"), 1), "invalidExpectedPID")
    require(integer(expect.get("processStartSeconds"), 1), "invalidExpectedProcessStart")
    require(integer(expect.get("processStartMicroseconds")) and expect["processStartMicroseconds"] < 1_000_000,
            "invalidExpectedProcessStart")
    path = expect.get("executable")
    require(isinstance(path, str) and path.startswith("/") and len(path) <= 4096
            and "\n" not in path and "\x00" not in path, "invalidExpectedExecutable")
    require(number(expect.get("startHostTime")) and number(expect.get("endHostTime"))
            and expect["endHostTime"] >= expect["startHostTime"], "invalidExpectedHostTimeWindow")
    if "expectedFinalSequence" in expect:
        require(integer(expect["expectedFinalSequence"]), "invalidExpectedFinalSequence")
    if "uid" in expect:
        require(integer(expect["uid"]), "invalidExpectedUID")
    if "hookInstanceID" in expect:
        require(identifier(expect["hookInstanceID"]), "invalidExpectedHookInstanceID")
    if "hookVersion" in expect:
        require(isinstance(expect["hookVersion"], str) and expect["hookVersion"] in HOOK_VERSIONS,
                "invalidExpectedHookVersion")
    return expect


class Analyzer:
    def __init__(self, expect):
        self.expect = validate_expectation(expect)
        self.instance = None
        self.uid = None
        self.mode = None
        self.version = None
        self.sequence = 0
        self.host_time = None
        self.first_host_time = None
        self.calls = {}
        self.results = set()
        self.streams = {}
        self.frames = {}
        self.forwarded_frames = set()
        self.flags = {
            "imageLoadedObserved": False,
            "hookInstallationObserved": False,
            "streamInitializationObserved": False,
            "streamSetupObserved": False,
            "captureEntryObserved": False,
            "successfulSnapshotObserved": False,
            "validScreenFrameObserved": False,
            "frameEvidenceObserved": False,
            "originalCallbackReturnObserved": False,
        }
        self.counts = Counter()

    def common(self, row):
        require(isinstance(row, dict), "recordNotObject")
        require(type(row.get("schemaVersion")) is int and row["schemaVersion"] == 2, "unsupportedSchema")
        version = row.get("hookVersion")
        require(isinstance(version, str) and version in HOOK_VERSIONS, "unsupportedHookVersion")
        require(self.version is None or version == self.version, "mixedHookVersions")
        if "hookVersion" in self.expect:
            require(version == self.expect["hookVersion"], "identityMismatch_hookVersion")
        require(type(row.get("priorLogWriteFailures")) is int and row["priorLogWriteFailures"] == 0, "priorLogWriteFailureOrMissingCounter")
        require(row.get("identityAvailable") is True, "processIdentityUnavailable")
        for field in ("sessionID", "pid", "processStartSeconds", "processStartMicroseconds", "executable"):
            expected = self.expect[field]
            require(type(row.get(field)) is type(expected) and row[field] == expected, "identityMismatch_" + field)
        require(integer(row.get("uid")), "invalidUID")
        if "uid" in self.expect:
            require(row["uid"] == self.expect["uid"], "identityMismatch_uid")
        instance = row.get("hookInstanceID")
        require(identifier(instance), "invalidHookInstanceID")
        try:
            uuid.UUID(instance)
        except ValueError:
            raise EvidenceError("invalidHookInstanceID") from None
        if "hookInstanceID" in self.expect:
            require(instance == self.expect["hookInstanceID"], "identityMismatch_hookInstanceID")
        require(self.instance is None or instance == self.instance, "mixedHookInstances")
        require(self.uid is None or self.uid == row["uid"], "changedUID")
        require(row.get("mode") in ("audit", "block"), "invalidHookMode")
        require(self.mode is None or self.mode == row["mode"], "changedHookMode")
        seq = row.get("sequence")
        require(integer(seq, 1), "invalidSequence")
        require(seq == self.sequence + 1, "sequenceGapDuplicateOrOutOfOrder")
        host = row.get("hostTime")
        require(number(host), "invalidHostTime")
        require(self.expect["startHostTime"] <= host <= self.expect["endHostTime"], "outsideExpectedHostTimeWindow")
        require(self.host_time is None or host >= self.host_time, "hostTimeOutOfOrder")
        require(identifier(row.get("event")), "invalidEventName")
        require(self.sequence > 0 or row["event"] == "image_loaded", "missingInitialImageLoaded")
        require(row["event"] != "image_loaded" or self.sequence == 0, "duplicateImageLoaded")
        self.instance, self.uid, self.mode = instance, row["uid"], row["mode"]
        self.version = version
        self.sequence, self.host_time = seq, host
        if self.first_host_time is None:
            self.first_host_time = host

    def stream_for(self, row):
        sid = row.get("streamID")
        require(identifier(sid) and sid in self.streams, "unknownStreamID")
        stream = self.streams[sid]
        require(row.get("creationCallID") == stream["creationCallID"], "streamCreationCallMismatch")
        return stream

    def consume(self, row):
        self.common(row)
        event = row["event"]
        if event == "image_loaded":
            self.flags["imageLoadedObserved"] = True
        elif event == "hook_installed":
            self.flags["hookInstallationObserved"] = True
        elif event == "capture_call":
            self.capture_call(row)
        elif event == "capture_result":
            self.snapshot_result(row)
        elif event == "stream_create_result":
            self.stream_create_result(row)
        elif event == "stream_setup_result":
            call = self.result_call(row, "stream_setup", event)
            require(row.get("streamID") == call["streamID"] and row.get("outputID") == call.get("outputID"), "setupResultIdentityMismatch")
            require(type(row.get("success")) is bool, "invalidSetupResultSuccess")
            if call["api"] == "SCStream.addStreamOutput" and row["success"]:
                stream = self.streams[call["streamID"]]
                require(call["outputID"] not in stream["outputs"], "duplicateOutputRegistration")
                stream["outputs"][call["outputID"]] = {"type": call.get("type"), "frames": {}}
        elif event == "capture_start_result":
            call = self.result_call(row, "stream_start", event)
            require(row.get("streamID") == call["streamID"], "startResultStreamMismatch")
            require(type(row.get("success")) is bool, "invalidStartResultSuccess")
        elif event in ("display_stream_frame", "sck_stream_frame"):
            self.frame(row)
        elif event == "frame_forwarded":
            fid = row.get("frameID")
            require(identifier(fid) and fid in self.frames, "orphanForwardedFrame")
            require(fid not in self.forwarded_frames, "duplicateForwardedFrame")
            frame = self.frames[fid]
            require(row.get("streamID") == frame["streamID"] and row.get("outputID") == frame["outputID"]
                    and type(row.get("validScreenFrame")) is bool and row["validScreenFrame"] == frame["valid"], "forwardedFrameIdentityMismatch")
            require(row.get("originalCallbackReturned") is True, "callbackReturnNotConfirmed")
            self.forwarded_frames.add(fid)
            self.counts["forwardedFrameRecords"] += 1
            if frame["valid"]:
                self.flags["originalCallbackReturnObserved"] = True
        elif event in V14_DIAGNOSTIC_EVENTS:
            self.diagnostic(row)
        elif event in DIAGNOSTIC_EVENTS:
            self.counts["diagnosticEvents"] += 1
            if event == "hook_unavailable":
                self.counts["unavailableHooks"] += 1
        else:
            # A new event schema must be reviewed, not silently interpreted as capture evidence.
            self.counts["uninterpretedEvents"] += 1
        self.counts["acceptedRecords"] += 1

    def diagnostic(self, row):
        """Validate diagnostic pairs without setting any capture or frame flags."""
        require(self.version == "1.4", "diagnosticRequiresHookVersion14")
        event, api = row["event"], row.get("api")
        shareable = event.startswith("shareable_content_")
        require(isinstance(api, str) and (api == SHAREABLE_CONTENT_API if shareable else api in DISPLAY_CONTROL_APIS),
                "unsupportedDiagnosticAPI")
        operation = "shareable_content" if shareable else "display_stream_control"
        if event in ("shareable_content_request", "display_stream_control_call"):
            cid = row.get("callID")
            require(identifier(cid) and cid not in self.calls, "missingOrDuplicateCallID")
            call = {"api": api, "operation": operation}
            if not shareable:
                require(type(row.get("streamProvided")) is bool, "invalidDiagnosticStreamProvided")
                call["streamProvided"] = row["streamProvided"]
            self.calls[cid] = call
            self.counts["shareableContentRequests" if shareable else "displayStreamControlCalls"] += 1
        else:
            call = self.result_call(row, operation, event)
            require(type(row.get("success")) is bool, "invalidDiagnosticSuccess")
            if shareable:
                domain, code = row.get("errorDomain"), row.get("errorCode")
                require(isinstance(domain, str) and len(domain) <= 256 and all(ord(c) >= 32 for c in domain),
                        "invalidDiagnosticErrorDomain")
                require(type(code) is int and -(2 ** 63) <= code < 2 ** 63, "invalidDiagnosticErrorCode")
                for field in ("displayCount", "windowCount", "applicationCount"):
                    require(integer(row.get(field)), "invalidShareableContentCount")
                require(not row["success"] or (domain == "" and code == 0), "inconsistentDiagnosticSuccess")
                self.counts["shareableContentResults"] += 1
                self.counts["shareableContentSuccesses" if row["success"] else "shareableContentFailures"] += 1
            else:
                require(type(row.get("streamProvided")) is bool and row["streamProvided"] == call["streamProvided"],
                        "diagnosticArgumentMismatch")
                code = row.get("returnCode")
                require(type(code) is int and -(2 ** 31) <= code < 2 ** 31, "invalidDisplayControlReturnCode")
                require(row["success"] == (code == 0), "inconsistentDiagnosticSuccess")
                self.counts["displayStreamControlResults"] += 1
                self.counts["displayStreamControlSuccesses" if row["success"] else "displayStreamControlFailures"] += 1
        self.counts["diagnosticEvents"] += 1

    def capture_call(self, row):
        cid, api, operation = row.get("callID"), row.get("api"), row.get("operation")
        require(identifier(cid) and cid not in self.calls, "missingOrDuplicateCallID")
        require(isinstance(api, str) and api in API_OPERATIONS and API_OPERATIONS[api] == operation, "unsupportedAPIOrOperationMismatch")
        call = {"api": api, "operation": operation}
        if operation.startswith("stream_"):
            sid = row.get("streamID")
            require(identifier(sid), "invalidStreamID")
            call["streamID"] = sid
            if operation == "stream_create":
                require(sid not in self.streams, "duplicateStreamID")
                self.streams[sid] = {"creationCallID": cid, "api": api, "created": False,
                                     "started": False, "outputs": {}}
                self.flags["streamInitializationObserved"] = True
            else:
                stream = self.stream_for(row)
                require(stream["created"], "streamOperationBeforeSuccessfulCreation")
                if operation == "stream_setup":
                    self.flags["streamSetupObserved"] = True
                    if api == "SCStream.addStreamOutput":
                        require(identifier(row.get("outputID")), "invalidOutputID")
                        require(integer(row.get("type")), "invalidOutputType")
                        call["outputID"], call["type"] = row["outputID"], row["type"]
                    elif "outputID" in row:
                        call["outputID"] = row["outputID"]
                elif operation == "stream_start":
                    stream["started"] = True
        self.calls[cid] = call
        self.counts["captureCalls"] += 1
        if operation == "snapshot_request":
            self.counts["snapshotRequests"] += 1
        if operation == "snapshot_request" or operation == "stream_start" or api.startswith("CGDisplayStreamCreate"):
            self.flags["captureEntryObserved"] = True
            self.counts["captureEntryCalls"] += 1
        else:
            self.counts["initializationSetupOrLifecycleCalls"] += 1

    def result_call(self, row, operation, event):
        cid = row.get("callID")
        require(identifier(cid) and cid in self.calls, "orphanCallResult")
        call = self.calls[cid]
        require(call["operation"] == operation and row.get("api") == call["api"], "callResultAPIMismatch")
        key = (event, cid)
        require(key not in self.results, "duplicateCallResult")
        self.results.add(key)
        return call

    def snapshot_result(self, row):
        self.result_call(row, "snapshot_request", "capture_result")
        for field in ("success", "validImageOrSample", "hasImage", "hasSample"):
            require(type(row.get(field)) is bool, "invalidSnapshotResultBoolean")
        for field in ("width", "height"):
            require(integer(row.get(field)), "invalidSnapshotDimensions")
        valid = row["success"] and row["validImageOrSample"]
        require(not row["success"] or row["validImageOrSample"], "inconsistentSnapshotSuccess")
        if row["validImageOrSample"]:
            require((row["hasImage"] or row["hasSample"]) and row["width"] > 0 and row["height"] > 0,
                    "inconsistentValidSnapshot")
        if valid:
            self.flags["successfulSnapshotObserved"] = True
            self.flags["frameEvidenceObserved"] = True
            self.counts["successfulSnapshots"] += 1
        self.counts["snapshotResults"] += 1

    def stream_create_result(self, row):
        call = self.result_call(row, "stream_create", "stream_create_result")
        require(row.get("streamID") == call["streamID"], "createResultStreamMismatch")
        require(type(row.get("success")) is bool, "invalidCreateResultSuccess")
        self.streams[call["streamID"]]["created"] = row["success"]

    def frame(self, row):
        sid = row.get("streamID")
        require(identifier(sid) and sid in self.streams, "orphanStreamFrame")
        stream = self.streams[sid]
        require(stream["created"], "frameWithoutSuccessfulStreamCreation")
        sck = row["event"] == "sck_stream_frame"
        require((stream["api"] == "SCStream.init") == sck, "streamFrameAPIFamilyMismatch")
        output_id, frame_id = row.get("outputID"), row.get("frameID")
        require(identifier(output_id), "invalidFrameOutputID")
        require(identifier(frame_id) and frame_id not in self.frames, "missingOrDuplicateFrameID")
        if sck:
            require(output_id in stream["outputs"] and stream["outputs"][output_id]["type"] == 0 and stream["started"], "sckFrameWithoutSuccessfulScreenSetupAndStart")
        else:
            require(not stream["outputs"] or output_id in stream["outputs"], "displayStreamOutputIDChanged")
            stream["outputs"].setdefault(output_id, {"frames": {}})
        output = stream["outputs"][output_id]
        require(type(row.get("validScreenFrame")) is bool, "invalidScreenFrameFlag")
        require(integer(row.get("frameCount"), 1) and integer(row.get("screenFrameCount")), "invalidFrameCounters")
        require(row["frameCount"] not in output["frames"], "duplicateFrameCounter")
        require(row["screenFrameCount"] <= row["frameCount"], "inconsistentScreenFrameCounter")
        for field in ("width", "height"):
            require(integer(row.get(field)), "invalidFrameDimensions")
        if row["validScreenFrame"]:
            require(row["width"] > 0 and row["height"] > 0 and row["screenFrameCount"] > 0,
                    "inconsistentValidScreenFrame")
            # When the hook includes underlying attributes, reject contradictory claims.
            if sck:
                require(type(row.get("type")) is int and row["type"] == 0, "nonScreenFrameMarkedValid")
                require(row.get("sampleValid") is True and row.get("dataReady") is True, "invalidDataMarkedValid")
            status_field = "frameStatus" if sck else "status"
            require(type(row.get(status_field)) is int and row[status_field] == 0, "incompleteFrameMarkedValid")
            for field in ("sampleValid", "dataReady", "hasImage", "hasSurface"):
                if field in row:
                    require(row[field] is True, "invalidDataMarkedValid")
            self.flags["validScreenFrameObserved"] = True
            self.flags["frameEvidenceObserved"] = True
            self.counts["validScreenFrameRecords"] += 1
        output["frames"][row["frameCount"]] = {"screenCount": row["screenFrameCount"], "valid": row["validScreenFrame"]}
        self.frames[frame_id] = {"streamID": sid, "outputID": output_id, "valid": row["validScreenFrame"]}
        self.counts["streamFrameRecords"] += 1

    def validate_frame_counters(self):
        # Concurrent callbacks may acquire the logging lock in a different order from
        # the output counter lock. Check counter consistency in callback-count order.
        for stream in self.streams.values():
            for output in stream["outputs"].values():
                previous_count = previous_screen = 0
                for count, frame in sorted(output["frames"].items()):
                    delta = frame["screenCount"] - previous_screen
                    require(0 <= delta <= count - previous_count, "inconsistentScreenFrameCounter")
                    require(not frame["valid"] or delta > 0, "inconsistentValidScreenFrameCounter")
                    if count == previous_count + 1 and not frame["valid"]:
                        require(delta == 0, "invalidFrameIncrementedScreenCounter")
                    previous_count, previous_screen = count, frame["screenCount"]


def analyze(log_bytes, expect):
    """Pure analysis entry point. No process access, file writes, or baseline discovery."""
    report = {
        "schemaVersion": 1, "level": "invalid_or_incomplete", "evidenceUsable": False,
        "localEvidenceOnly": True, "captureBlockingVerified": False,
        "remoteSessionVerified": False, "logAuthenticityVerified": False,
        "issues": [], "flags": {}, "coverage": {},
    }
    try:
        engine = Analyzer(expect)
    except EvidenceError as error:
        report["issues"] = [{"code": str(error), "source": "expectation"}]
        return report
    report["expectation"] = {key: expect[key] for key in ("sessionID", "pid", "processStartSeconds", "processStartMicroseconds", "executable", "startHostTime", "endHostTime")}
    if "hookVersion" in expect:
        report["expectation"]["hookVersion"] = expect["hookVersion"]
    report["inputSHA256"] = hashlib.sha256(log_bytes).hexdigest()
    issues = report["issues"]
    if len(log_bytes) > MAX_LOG_BYTES:
        issues.append({"code": "logSizeLimitExceeded"})
        lines = []
    else:
        lines = log_bytes.splitlines(keepends=True)
    if len(lines) > MAX_RECORDS:
        issues.append({"code": "recordCountLimitExceeded"})
    for index, line in enumerate(lines[:MAX_RECORDS], 1):
        previous = (engine.sequence, engine.host_time, engine.first_host_time, engine.instance, engine.uid, engine.mode, engine.version,
                    engine.flags.copy(), engine.counts.copy())
        try:
            require(len(line) <= MAX_LINE_BYTES, "lineSizeLimitExceeded")
            require(line.endswith(b"\n"), "truncatedFinalLine")
            require(bool(line.strip()), "blankRecord")
            row = strict_json(line)
            engine.consume(row)
        except EvidenceError as error:
            (engine.sequence, engine.host_time, engine.first_host_time, engine.instance, engine.uid, engine.mode, engine.version,
             engine.flags, engine.counts) = previous
            issues.append({"line": index, "code": str(error)})
            break  # Preserve only the validated prefix; do not stitch across corrupt records.
    if not issues:
        try:
            engine.validate_frame_counters()
        except EvidenceError as error:
            issues.append({"code": str(error)})
    expected_final = expect.get("expectedFinalSequence")
    tail_verified = expected_final is not None and expected_final == engine.sequence and not issues
    if expected_final is not None and expected_final != engine.sequence:
        issues.append({"code": "expectedFinalSequenceMismatch"})
    flags = engine.flags
    if not issues:
        report["evidenceUsable"] = True
        if flags["frameEvidenceObserved"]:
            report["level"] = "frame_callback_observed"
        elif flags["captureEntryObserved"]:
            report["level"] = "capture_entry_observed"
        elif flags["imageLoadedObserved"]:
            report["level"] = "loaded_only"
        else:
            report["level"] = "no_evidence"
    report["flags"] = flags
    report["hookVersion"] = engine.version
    report["flagsDescribeValidatedPrefixOnly"] = bool(issues)
    report["counts"] = {"inputLines": len(lines), **dict(engine.counts)}
    report["coverage"] = {
        "allInputRecordsValidated": not issues,
        "allEventPayloadsInterpreted": not issues and engine.counts["uninterpretedEvents"] == 0,
        "sequenceContiguousFromImageLoaded": not issues and bool(lines),
        "identityAndMonotonicWindowMatched": not issues and bool(lines),
        "logTailCompletenessVerified": tail_verified,
        "expectedFinalSequenceProvided": expected_final is not None,
        "lastValidatedSequence": engine.sequence,
        "firstValidatedHostTime": engine.first_host_time,
        "lastValidatedHostTime": engine.host_time,
        "framesAreSampled": True,
        "allCaptureAPIsCovered": False,
        "fullExpectedTimeWindowContinuouslyObserved": False,
        "pendingSnapshotResults": engine.counts["snapshotRequests"] - engine.counts["snapshotResults"],
        "pendingShareableContentResults": engine.counts["shareableContentRequests"] - engine.counts["shareableContentResults"],
        "pendingDisplayStreamControlResults": engine.counts["displayStreamControlCalls"] - engine.counts["displayStreamControlResults"],
    }
    report["limitations"] = [
        "The expectation must come from an independent controller or test-host receipt; this analyzer cannot authenticate its provenance.",
        "Local logs and manifests can be forged or altered. Correlation is not cryptographic attestation.",
        "Without an independently obtained expectedFinalSequence, deletion of whole trailing JSONL records is undetectable; observed positive evidence does not prove complete collection.",
        "Stream initialization, setup, update and stop do not by themselves establish capture entry. Capture entry alone does not establish any valid frame.",
        "Only reported valid captured input or screen callbacks are counted. No output pixel redaction, complete stream, UU remote session, or end-to-end protection is verified.",
        "Unfinished async requests can remain at the end of the observation window. Snapshot requests may supply entry evidence; diagnostic requests do not.",
        "Shareable-content enumeration and CGDisplayStream start/stop diagnostics never establish capture or frame evidence. Their call IDs do not identify a native stream or a remote session.",
    ]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--expect", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New JSON file; existing files are never overwritten")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("--output already exists; choose a new file")
    try:
        require(args.expect.stat().st_size <= MAX_LINE_BYTES, "expectationSizeLimitExceeded")
        expect = strict_json(args.expect.read_bytes())
        with args.log.open("rb") as stream:
            raw = stream.read(MAX_LOG_BYTES + 1)
        result = analyze(raw, expect)
    except (OSError, EvidenceError) as error:
        result = {"schemaVersion": 1, "level": "invalid_or_incomplete", "evidenceUsable": False,
                  "localEvidenceOnly": True, "captureBlockingVerified": False,
                  "remoteSessionVerified": False, "logAuthenticityVerified": False,
                  "issues": [{"code": str(error) if isinstance(error, EvidenceError) else "inputReadFailed"}]}
    try:
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    except OSError:
        print("Cannot create the new output JSON file.", file=sys.stderr)
        return 2
    print(json.dumps({"level": result["level"], "evidenceUsable": result["evidenceUsable"],
                      "captureBlockingVerified": False, "localEvidenceOnly": True}))
    return 2 if result["level"] == "invalid_or_incomplete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
