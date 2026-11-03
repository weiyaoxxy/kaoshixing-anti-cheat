#!/usr/bin/env python3
"""Analyze an existing macOS sample call tree; never samples or changes a process.

Only allowlisted symbols on a single ancestry path are capture-path evidence.
Binary Images and flat symbol summaries never contribute executable evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys

MAX_BYTES = 16 * 1024 * 1024
MAX_LINE = 16 * 1024
MAX_NODES = 100_000
MAX_EVIDENCE = 64
TREE = re.compile(r"(?P<prefix>[ +!:|]*)(?P<count>[0-9]+) (?P<body>.+)")
THREAD = re.compile(r"Thread_(?:[0-9]+|<multiple>)(?:\s|:|$)")
FRAME = re.compile(r"(?P<symbol>.+?)\s{2,}\(in (?P<image>[^()]+)\)(?:\s+.*)?")
SCK = re.compile(r"__\d+-\[SCStream\(SCContentSharing\) startRemoteVideoReceiveQueue:\]_block_invoke(?:_\d+)?")
RECEIVE = re.compile(r"streamer::capture::ScreenCapturerSck::OnReceiveVideoSampleBuffer\(.*\)")
ENCODER = re.compile(r"streamer::encoder::VideoToolboxEncoderT<.+>::Encode\(.*\)")
FINAL_IMAGE = re.compile(r"\s*0x[0-9a-fA-F]+\s+-\s+0x[0-9a-fA-F]+\s+.+\s+<[0-9a-fA-F-]{36}>\s+/[^\r\n]+")
KNOWN_STREAMER = {
    "streamer::capture::DesktopScreenCapturer::OnFrameCallback": "desktop_frame_callback",
    "streamer::VideoPreprocessSource::OnFrame": "video_preprocess",
    "streamer::IOSurfaceFrame::CopyFrom": "iosurface_copy_from",
    "streamer::IOSurfaceFrame::CopyTo": "iosurface_copy_to",
    "streamer::IOSurfaceFrame::Texture": "iosurface_texture",
}


class SampleError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise SampleError(code)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicateExpectationKey")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(SampleError("nonfiniteExpectationNumber")))
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        raise SampleError("invalidExpectationJSON") from None


def validate_expect(expect):
    require(isinstance(expect, dict), "expectationNotObject")
    require(type(expect.get("pid")) is int and expect["pid"] > 0, "invalidExpectedPID")
    path = expect.get("executable")
    require(isinstance(path, str) and path.startswith("/") and len(path) <= 4096
            and not any(ord(c) < 32 or ord(c) == 127 for c in path), "invalidExpectedExecutable")
    for key in ("identityMatchedBeforeAfter", "sampleTimedOut", "sampleOutputTruncated", "sampleOutputComplete"):
        if key in expect:
            require(type(expect[key]) is bool, "invalidExternalBoolean_" + key)
    if "sampleExitCode" in expect:
        require(type(expect["sampleExitCode"]) is int, "invalidSampleExitCode")
    if "expectedSampleSHA256" in expect:
        require(isinstance(expect["expectedSampleSHA256"], str)
                and re.fullmatch(r"[0-9a-fA-F]{64}", expect["expectedSampleSHA256"]), "invalidExpectedSampleSHA256")
    return expect


def symbol_info(body):
    match = FRAME.fullmatch(body)
    if not match:
        return None
    symbol, image = match["symbol"], match["image"]
    category = canonical = None
    if image == "ScreenCaptureKit" and SCK.fullmatch(symbol):
        category, canonical = "sck_video_receive_callback", "[SCStream(SCContentSharing) startRemoteVideoReceiveQueue:] block callback"
    elif image == "libstreamer.dylib":
        if RECEIVE.fullmatch(symbol):
            category, canonical = "libstreamer_sck_receive", "streamer::capture::ScreenCapturerSck::OnReceiveVideoSampleBuffer"
        elif ENCODER.fullmatch(symbol):
            category, canonical = "libstreamer_encoder", "streamer::encoder::VideoToolboxEncoderT<...>::Encode"
        else:
            for name, kind in KNOWN_STREAMER.items():
                if re.fullmatch(re.escape(name) + r"\(.*\)", symbol):
                    category, canonical = kind, name
                    break
    elif image == "VideoToolbox" and symbol in ("VTCompressionSessionEncodeFrame", "VTEncoderSessionEmitEncodedFrame"):
        category = "videotoolbox_encode" if symbol == "VTCompressionSessionEncodeFrame" else "videotoolbox_emit"
        canonical = symbol
    if category is None:
        return None
    # Only canonical names enter output; raw symbols, parameters and addresses do not.
    return {"category": category, "symbol": canonical, "image": image,
            "excerpt": canonical + " (in " + image + ")"}


def base_report():
    return {"schemaVersion": 1, "status": "invalid_or_incomplete", "evidenceUsable": False,
            "pathObserved": False, "headerIdentityMatched": False,
            "identityContinuityVerified": False, "outputCompletenessVerified": False,
            "captureHookHitVerified": False, "validFrameVerified": False,
            "remoteSessionVerified": False, "captureBlockingVerified": False,
            "logAuthenticityVerified": False, "sampleCountsAreFrameCounts": False,
            "encodingObserved": False, "iosurfaceObserved": False,
            "iosurfaceOnCapturePathObserved": False, "encoderToVideoToolboxChainObserved": False,
            "capturePathEvidence": [], "encodingEvidence": [], "iosurfaceEvidence": [],
            "issues": [], "limitations": [
                "Statistical stack sampling is not complete call tracing; sample counts are not call counts, frame counts or frame rate.",
                "Only a same-ancestry ScreenCaptureKit video callback and libstreamer SCK receiver establishes pathObserved.",
                "Independent encoding/IOSurface stacks are supporting observations, not a same-frame capture-to-encoding or remote-delivery trace.",
                "No matching path in a short sample does not exclude capture, other processes, modes or fallback backends.",
                "This does not verify SCStream.startCapture arguments, valid sample buffers, Hook execution, pixel masking or remote success.",
                "Headers, external identity/collector declarations and local files can be forged; this is not authenticated attestation.",
                "A graph terminator, Binary Images section and final newline cannot detect removal of whole trailing records. External collector declarations govern outputCompletenessVerified.",
                "Unknown intervening frames are retained as anonymous nodes, never asserted to be direct adjacent calls between the named symbols.",
            ]}


def analyze(sample_text, expect):
    """Return bounded, sanitized evidence from existing text and an external manifest."""
    report = base_report()
    try:
        expect = validate_expect(expect)
        report["expectedIdentity"] = {"pid": expect["pid"], "executable": expect["executable"]}
        report["externalIdentityMatchedBeforeAfter"] = expect.get("identityMatchedBeforeAfter")
        report["externalMetadataSource"] = "callerSuppliedExpectation"
        if isinstance(sample_text, bytes):
            raw = sample_text
            try:
                sample_text = raw.decode("utf-8")
            except UnicodeError:
                raise SampleError("invalidSampleUTF8") from None
        else:
            require(isinstance(sample_text, str), "sampleNotText")
            raw = sample_text.encode("utf-8")
        require(0 < len(raw) <= MAX_BYTES, "sampleSizeInvalidOrExceeded")
        report["sampleSHA256"] = hashlib.sha256(raw).hexdigest()
        if "expectedSampleSHA256" in expect:
            require(report["sampleSHA256"] == expect["expectedSampleSHA256"].lower(), "sampleHashMismatch")
        lines = sample_text.splitlines()
        require(all(len(line) <= MAX_LINE for line in lines), "sampleLineLimitExceeded")
        graph_starts = [i for i, line in enumerate(lines) if line == "Call graph:"]
        require(len(graph_starts) == 1, "missingOrDuplicateCallGraph")
        start = graph_starts[0]
        header = lines[:start]
        process_rows = [line for line in header if line.startswith("Process:")]
        path_rows = [line for line in header if line.startswith("Path:")]
        require(len(process_rows) == 1 and len(path_rows) == 1, "missingOrDuplicateIdentityHeader")
        pid_match = re.fullmatch(r"Process:\s+.+?\s+\[([0-9]+)\]\s*", process_rows[0])
        path_match = re.fullmatch(r"Path:\s+(.+?)\s*", path_rows[0])
        require(pid_match is not None and int(pid_match[1]) == expect["pid"], "headerPIDMismatch")
        require(path_match is not None and path_match[1] == expect["executable"], "headerExecutableMismatch")
        report["headerIdentityMatched"] = True
        require(expect.get("identityMatchedBeforeAfter") is not False, "externalProcessIdentityChanged")
        require(expect.get("sampleExitCode", 0) == 0, "sampleToolFailed")
        require(expect.get("sampleTimedOut") is not True, "sampleToolTimedOut")
        require(expect.get("sampleOutputTruncated") is not True, "sampleOutputTruncated")
        require(expect.get("sampleOutputComplete") is not False, "sampleOutputIncomplete")
        report["identityContinuityVerified"] = expect.get("identityMatchedBeforeAfter") is True
        require(sample_text.endswith("\n"), "missingFinalNewline")
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].startswith("Total number in stack (")
                    or lines[i].startswith("Sort by top of stack,") or lines[i] == "Binary Images:"), None)
        require(end is not None, "unterminatedCallGraph")
        binaries = [i for i, line in enumerate(lines) if line == "Binary Images:"]
        require(len(binaries) == 1 and binaries[0] >= end, "missingOrInvalidBinaryImagesFooter")
        trailing = [line for line in lines[binaries[0] + 1:] if line.strip()]
        require(bool(trailing) and FINAL_IMAGE.fullmatch(trailing[-1]) is not None, "missingOrMalformedFinalImageRow")
        report["coverage"] = {"callGraphStartLine": start + 1, "callGraphEndExclusiveLine": end + 1,
                              "graphTerminatorObserved": True, "binaryImagesFooterObserved": True,
                              "finalNewlineObserved": True, "symbolsOutsideCallGraphIgnored": True}
        output_declared_complete = (expect.get("sampleExitCode") == 0 and "sampleExitCode" in expect
                                    and expect.get("sampleTimedOut") is False
                                    and expect.get("sampleOutputTruncated") is False
                                    and expect.get("sampleOutputComplete") is True)
        report["outputCompletenessVerified"] = output_declared_complete
        stack = []
        thread = None
        thread_count = node_count = 0
        matches = Counter()
        capture_paths, encodings, surfaces = [], [], []
        surface_on_path = encoder_chain = False
        for index in range(start + 1, end):
            line = lines[index]
            if not line.strip():
                continue
            match = TREE.fullmatch(line)
            require(match is not None, "unrecognizedCallGraphRow")
            prefix, body = match["prefix"], match["body"]
            depth = len(prefix)
            if THREAD.match(body):
                require(prefix == "    ", "invalidThreadRootIndentation")
                thread_count += 1
                thread = {"ordinal": thread_count, "headerLine": index + 1}
                stack = [{"depth": depth, "line": index + 1, "info": None}]
                continue
            require(thread is not None, "frameWithoutThreadRoot")
            while stack and stack[-1]["depth"] >= depth:
                stack.pop()
            require(bool(stack) and depth == stack[-1]["depth"] + 2, "invalidOrMissingTreeAncestry")
            info = symbol_info(body)
            node = {"depth": depth, "line": index + 1, "info": info}
            stack.append(node)
            node_count += 1
            require(node_count <= MAX_NODES, "callGraphNodeLimitExceeded")
            if info is None:
                continue
            category = info["category"]
            matches[category] += 1
            ancestry = [node["info"]["category"] if node["info"] else None for node in stack]
            sck_index = next((i for i, kind in enumerate(ancestry) if kind == "sck_video_receive_callback"), None)
            receiver_index = next((i for i, kind in enumerate(ancestry) if kind == "libstreamer_sck_receive"), None)
            on_path = sck_index is not None and receiver_index is not None and sck_index < receiver_index
            if category == "libstreamer_sck_receive" and on_path:
                nodes = []
                for ancestor in stack[sck_index:]:
                    entry = {"sourceLine": ancestor["line"], "treeColumn": ancestor["depth"]}
                    entry.update(ancestor["info"] or {"category": "unreported_intermediate_frame"})
                    nodes.append(entry)
                capture_paths.append({"threadOrdinal": thread["ordinal"], "threadHeaderLine": thread["headerLine"],
                                      "sameAncestorChain": True, "namedCallsClaimedDirectlyAdjacent": False,
                                      "nodes": nodes})
            evidence = {"sourceLine": index + 1, "threadOrdinal": thread["ordinal"],
                        "threadHeaderLine": thread["headerLine"], **info}
            if category.startswith("iosurface_"):
                evidence["onObservedCaptureAncestorChain"] = on_path
                surfaces.append(evidence)
                surface_on_path = surface_on_path or on_path
            if category in ("libstreamer_encoder", "videotoolbox_encode", "videotoolbox_emit"):
                encodings.append(evidence)
                if category == "videotoolbox_encode" and "libstreamer_encoder" in ancestry[:-1]:
                    encoder_chain = True
        require(thread_count > 0 and node_count > 0, "emptyCallGraph")
        report.update(status="path_observed" if capture_paths else "path_not_observed", evidenceUsable=True,
                      pathObserved=bool(capture_paths), encodingObserved=matches["videotoolbox_encode"] > 0,
                      iosurfaceObserved=bool(surfaces), iosurfaceOnCapturePathObserved=surface_on_path,
                      encoderToVideoToolboxChainObserved=encoder_chain,
                      capturePathEvidence=capture_paths[:MAX_EVIDENCE], encodingEvidence=encodings[:MAX_EVIDENCE],
                      iosurfaceEvidence=surfaces[:MAX_EVIDENCE],
                      evidenceExcerptLimitApplied=any(len(items) > MAX_EVIDENCE for items in (capture_paths, encodings, surfaces)),
                      counts={"threadGroupsParsed": thread_count, "callGraphRowsParsed": node_count,
                              "captureAncestorPaths": len(capture_paths), "allowlistedSymbolRows": dict(matches)})
    except (SampleError, UnicodeError, RecursionError) as error:
        report["issues"].append({"code": str(error) if isinstance(error, SampleError) else "invalidSampleEncodingOrNesting"})
        report.update(status="invalid_or_incomplete", evidenceUsable=False, pathObserved=False,
                      encodingObserved=False, iosurfaceObserved=False, iosurfaceOnCapturePathObserved=False,
                      encoderToVideoToolboxChainObserved=False, capturePathEvidence=[], encodingEvidence=[], iosurfaceEvidence=[])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--expect", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New JSON file; never overwrite existing evidence")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("--output already exists; select a new path")
    try:
        require(args.expect.stat().st_size <= 65536, "expectationSizeLimitExceeded")
        expect = strict_json(args.expect.read_bytes())
        with args.sample.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        result = analyze(raw, expect)
    except (OSError, SampleError) as error:
        result = base_report()
        result["issues"] = [{"code": str(error) if isinstance(error, SampleError) else "inputReadFailed"}]
    try:
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    except OSError:
        print("Could not create new output JSON file.", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "pathObserved": result["pathObserved"],
                      "evidenceUsable": result["evidenceUsable"], "captureHookHitVerified": False}))
    return 2 if result["status"] == "invalid_or_incomplete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
