#!/usr/bin/env python3
"""Inspect every saved PNG, preserving missing files/errors as inconclusive.

Pillow is required. This script measures synthetic marker pixels in the known
Demo marker rectangle, not arbitrary magenta pixels elsewhere on the desktop.
It summarizes existing Vision OCR observations without treating OCR misses as
proof of protection. Output is local JSON/CSV beside the input artifacts.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops


def read_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def marker_roi(path: Path, size, state, report):
    """Coordinates derive from the synthetic Demo's fixed 88x64 point marker.

    ExamView draws at x=canvasWidth-126, y=canvasHeight-106 in AppKit
    coordinates. PNG coordinates are top-left. Window screenshots exclude
    shadows except screencapture's system-window.png, whose padding is retained.
    """
    backing = state["backingScale"]
    canvas_w, canvas_h = state["pixelWidth"] / backing, state["pixelHeight"] / backing
    x, y, w, h = canvas_w - 126, 42, 88, 64
    iw, ih = size
    if path.name == "source-reference.png" or path.name.endswith(".decoded.png"):
        sx, sy = iw / canvas_w, ih / canvas_h
        return [round(x * sx), round(y * sy), round((x + w) * sx), round((y + h) * sy)]
    window = next((q for q in report.get("cgWindows", []) if q["id"] == state["windowID"]), None)
    if not window:
        raise ValueError("Target window bounds missing; cannot infer marker ROI")
    bounds = window["bounds"]
    y += bounds["Height"] - canvas_h
    if "display" in str(path):
        display = report.get("scDisplays", [{}])[0].get("frame")
        if not display:
            raise ValueError("Display frame missing; cannot infer marker ROI")
        x += bounds["X"] - display["x"]
        y += bounds["Y"] - display["y"]
        sx, sy = iw / display["width"], ih / display["height"]
        ox = oy = 0
    elif path.name == "system-window.png":
        # The shadow padding is asymmetric. Calibrate it from the positive
        # baseline instead of assuming the visible window is centered in PNG.
        baseline_path = path.parent.parent / "baseline" / "system-window.png"
        with Image.open(baseline_path) as original:
            baseline = original.convert("RGBA")
        br, bg, bb, ba = baseline.split()
        marker = ImageChops.multiply(ImageChops.multiply(br.point(lambda v: 255 if v >= 190 else 0),
                                                         bg.point(lambda v: 255 if v <= 90 else 0)),
                                     bb.point(lambda v: 255 if v >= 190 else 0))
        marker = ImageChops.multiply(marker, ba.point(lambda v: 255 if v >= 200 else 0))
        bbox = marker.getbbox()
        if not bbox or (bbox[2] - bbox[0], bbox[3] - bbox[1]) != (round(w * backing), round(h * backing)):
            raise ValueError("Cannot calibrate shadow padding from baseline marker")
        return [round(bbox[0] * iw / baseline.width), round(bbox[1] * ih / baseline.height),
                round(bbox[2] * iw / baseline.width), round(bbox[3] * ih / baseline.height)]
    else:
        sx, sy = iw / bounds["Width"], ih / bounds["Height"]
        ox = oy = 0
    return [round(ox + x * sx), round(oy + y * sy), round(ox + (x + w) * sx), round(oy + (y + h) * sy)]


def inspect_image(path, case, state, report, ocr):
    result = {"path": str(path.relative_to(case)), "exists": path.exists()}
    observation = ocr.get(str(path.resolve()))
    if observation:
        result["ocr"] = {k: observation.get(k) for k in ["secretDetected", "nativeLeakDetected", "publicDetected", "error"]}
    else:
        result["ocr"] = None
    if not path.exists():
        result["error"] = "file missing; no protection conclusion"
        return result
    try:
        with Image.open(path) as original:
            im = original.convert("RGBA")
        result["width"], result["height"] = im.size
        r, g, b, a = im.split()
        mask = ImageChops.multiply(ImageChops.multiply(r.point(lambda v: 255 if v >= 190 else 0),
                                                       g.point(lambda v: 255 if v <= 90 else 0)),
                                   b.point(lambda v: 255 if v >= 190 else 0))
        mask = ImageChops.multiply(mask, a.point(lambda v: 255 if v >= 200 else 0))
        result["magentaPixelsWholeImage"] = mask.histogram()[255]
        roi = marker_roi(path, im.size, state, report)
        if not (0 <= roi[0] < roi[2] <= im.width and 0 <= roi[1] < roi[3] <= im.height):
            raise ValueError(f"Marker ROI outside image: {roi}")
        result["markerROI"] = roi
        result["markerROIArea"] = (roi[2] - roi[0]) * (roi[3] - roi[1])
        result["markerPixelsInROI"] = mask.crop(roi).histogram()[255]
        result["markerCoverage"] = result["markerPixelsInROI"] / result["markerROIArea"]
        result["markerObserved"] = result["markerCoverage"] >= 0.5
        alpha = a.histogram()
        result["nontransparentPixels"] = im.width * im.height - alpha[0]
        result["allTransparent"] = alpha[0] == im.width * im.height
        result["roiAlphaExtrema"] = a.crop(roi).getextrema()
        result["rgbaExtrema"] = im.getextrema()
    except Exception as exc:
        result["error"] = str(exc)
    return result


def analyze_case(case, state_path=None):
    state = read_json(state_path or case / "demo-state.json", {})
    capture_root = case if state_path else case / "capture"
    report = read_json(capture_root / "report.json", {})
    observations = []
    for name in ["media-inspection.jsonl", "stream-inspection.jsonl"]:
        path = case / name
        if path.exists():
            observations.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    ocr = {str(Path(row["path"]).resolve()): row for row in observations}
    screenshots = [case / name for name in ["system-window.png", "system-display.png", "source-reference.png"]]
    screenshots += [case / "capture" / name for name in ["cg-window.png", "cg-display.png", "sck-screenshot-window.png", "sck-screenshot-display.png"]]
    screenshots += sorted(case.glob("*.decoded.png"))
    images = [] if state_path else [inspect_image(p, case, state, report, ocr) for p in screenshots]
    streams = {}
    for kind in [key.removeprefix("stream_") for key in report if key.startswith("stream_")]:
        log = report.get("stream_" + kind, {})
        directory = capture_root / log.get("directory", "sck-stream-" + kind)
        files = {p.name: p for p in directory.glob("*.png")}
        expected = {frame["file"] for frame in log.get("frames", []) if frame.get("saved") and frame.get("file")}
        frames = [inspect_image(directory / name, case, state, report, ocr) for name in sorted(set(files) | expected)]
        frame_metadata = {f["file"]: f for f in log.get("frames", []) if f.get("file")}
        for frame in frames:
            frame["phase"] = frame_metadata.get(Path(frame["path"]).name, {}).get("phase", "initial")
        valid = [f for f in frames if "error" not in f]
        pts = [f["ptsSeconds"] for f in log.get("frames", []) if f.get("saved") and "ptsSeconds" in f]
        streams[kind] = {
            "status": log.get("status"), "errors": log.get("streamErrors", []),
            "framesReportedSaved": log.get("completeFramesSaved"),
            "filesPresent": len(files), "framesInspected": len(frames), "imagesReadable": len(valid),
            "allReportedFilesPresent": bool(expected) and expected.issubset(files),
            "noExtraFiles": set(files).issubset(expected),
            "allFramesValidComplete": bool(log.get("frames")) and all(f.get("sampleValid") and f.get("SCFrameStatusRaw") == 0 for f in log["frames"]),
            "ptsSpanSeconds": max(pts) - min(pts) if pts else None,
            "markerDetectedFrames": sum(f["markerObserved"] for f in valid),
            "roiPixelCountMin": min((f["markerPixelsInROI"] for f in valid), default=None),
            "roiPixelCountMax": max((f["markerPixelsInROI"] for f in valid), default=None),
            "allTransparentFrames": sum(f["allTransparent"] for f in valid),
            "ocrFramesInspected": sum(f.get("ocr") is not None for f in valid),
            "ocrSecretDetectedFrames": sum(f.get("ocr", {}).get("secretDetected") is True for f in valid if f.get("ocr")),
            "ocrNativeLeakDetectedFrames": sum(f.get("ocr", {}).get("nativeLeakDetected") is True for f in valid if f.get("ocr")),
            "phaseCounts": dict(Counter(f.get("phase", "initial") for f in log.get("frames", []) if f.get("saved"))),
            "phaseMarkerDetectedFrames": dict(Counter(f["phase"] for f in valid if f["markerObserved"])),
            "frames": frames,
        }
    return {
        "mode": case.name, "demoState": state,
        "probe": {k: report.get(k) for k in ["processID", "permissionBefore", "permissionAfter", "targetFoundInCGList", "targetFoundInSCList", "operatingSystem"]},
        "separateProcesses": bool(state.get("pid") and report.get("processID") and state["pid"] != report["processID"]),
        "screencapture": read_json(case / "screencapture.json"), "coreGraphics": report.get("coreGraphics"),
        "recordings": [row for row in observations if str(row["path"]).endswith(".mp4")],
        "images": images, "streams": streams,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--state", type=Path, help="Analyze a standalone probe directory using this Demo state JSON")
    args = parser.parse_args()
    matrix = args.matrix.resolve()
    cases = [analyze_case(matrix, args.state)] if args.state else [analyze_case(p) for p in sorted(matrix.iterdir()) if p.is_dir() and (p / "demo-state.json").exists()]
    result = {
        "matrix": str(matrix),
        "method": "Every saved stream PNG decoded with Pillow. RGBA thresholds R>=190,G<=90,B>=190,A>=200; marker ROI derives from Demo geometry; >=50% ROI means markerObserved. OCR fields are separate observations, not security verdicts.",
        "limitations": "This image analysis does not independently verify the physical display. No image or an unreadable image is inconclusive. No marker does not prove all exam content absent. Stream inspection covers saved samples, not every compositor frame. Desktop pixels outside marker ROI are not used as evidence.",
        "cases": cases,
    }
    (matrix / "analysis-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    fields = ["mode", "path", "exists", "width", "height", "markerPixelsInROI", "markerCoverage", "markerObserved", "magentaPixelsWholeImage", "allTransparent", "error"]
    with (matrix / "analysis-images.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for case in cases:
            for row in case["images"] + [frame for s in case["streams"].values() for frame in s["frames"]]:
                writer.writerow({"mode": case["mode"], **row})
    for case in cases:
        print(case["mode"], {kind: {k: v for k, v in stream.items() if k != "frames"} for kind, stream in case["streams"].items()})
    print(matrix / "analysis-summary.json")


if __name__ == "__main__":
    main()
