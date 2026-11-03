#!/usr/bin/env python3
"""Synthetic trees plus existing historical files; never touches live UU."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/analyze-uu-capture-sample.py"
spec = importlib.util.spec_from_file_location("uu_capture_sample", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
EXPECT = {"pid": 123, "executable": "/test/UURemoteServer"}
SCK = "__59-[SCStream(SCContentSharing) startRemoteVideoReceiveQueue:]_block_invoke  (in ScreenCaptureKit) + 12  [0x1234]"
RECEIVE = "streamer::capture::ScreenCapturerSck::OnReceiveVideoSampleBuffer(opaqueCMSampleBuffer*, streamer::capture::DesktopConfig const&)  (in libstreamer.dylib) + 4  [0x2345]"
SURFACE = "streamer::IOSurfaceFrame::CopyFrom(streamer::capture::RawVideoFrame const&)  (in libstreamer.dylib) + 2  [0x3456]"
ENCODER = "streamer::encoder::VideoToolboxEncoderT<streamer::encoder::SystemVideoToolboxEncoderPolicy>::Encode(streamer::encoder::VideoEncodeFrameInfo const&)  (in libstreamer.dylib) + 1  [0x4567]"
VT = "VTCompressionSessionEncodeFrame  (in VideoToolbox) + 1  [0x5678]"
THREAD = "    20 Thread_9   DispatchQueue_8: PRIVATE_THREAD_BUSINESS_VALUE  (serial)"
IMAGE = "       0x1000 - 0x1fff +Dummy (1) <12345678-1234-1234-1234-123456789ABC> /test/UURemoteServer"


def frame(depth, symbol, count=1):
    return " " * depth + str(count) + " " + symbol


def sample(rows=None, footer=True):
    if rows is None:
        rows = [THREAD, frame(6, SCK, 12), frame(8, "PRIVATE_OTHER_SYMBOL(value)  (in PrivateLibrary)"), frame(10, RECEIVE, 7)]
    text = "Process: UURemoteServer [123]\nPath: /test/UURemoteServer\n\nCall graph:\n" + "\n".join(rows) + "\n"
    if footer:
        text += "\nTotal number in stack (recursive counted multiple, when >=5):\n\nBinary Images:\n" + IMAGE + "\n"
    return text


class CaptureSampleTests(unittest.TestCase):
    def check_invalid(self, text, expect=None, code=None):
        result = module.analyze(text, EXPECT if expect is None else expect)
        self.assertEqual(result["status"], "invalid_or_incomplete")
        self.assertFalse(result["pathObserved"])
        self.assertFalse(result["evidenceUsable"])
        if code:
            self.assertIn(code, [row["code"] for row in result["issues"]])
        return result

    def test_same_ancestor_path_with_anonymous_bridge(self):
        result = module.analyze(sample(), EXPECT)
        self.assertEqual(result["status"], "path_observed")
        self.assertTrue(result["pathObserved"])
        self.assertTrue(result["headerIdentityMatched"])
        self.assertEqual([n["category"] for n in result["capturePathEvidence"][0]["nodes"]],
                         ["sck_video_receive_callback", "unreported_intermediate_frame", "libstreamer_sck_receive"])

    def test_direct_child_also_matches(self):
        self.assertTrue(module.analyze(sample([THREAD, frame(6, SCK), frame(8, RECEIVE)]), EXPECT)["pathObserved"])

    def test_branch_prefix_characters_are_columns(self):
        text = sample([THREAD, "    + 4 " + SCK, "    +   3 " + RECEIVE])
        self.assertTrue(module.analyze(text, EXPECT)["pathObserved"])

    def test_siblings_do_not_form_chain(self):
        result = module.analyze(sample([THREAD, frame(6, SCK), frame(6, RECEIVE)]), EXPECT)
        self.assertEqual(result["status"], "path_not_observed")

    def test_distinct_descendant_branches_do_not_form_chain(self):
        rows = [THREAD, frame(6, "root  (in libdispatch.dylib)"), frame(8, SCK),
                frame(10, "leaf  (in libdispatch.dylib)"), frame(8, "other  (in libdispatch.dylib)"), frame(10, RECEIVE)]
        self.assertFalse(module.analyze(sample(rows), EXPECT)["pathObserved"])

    def test_threads_do_not_form_chain(self):
        result = module.analyze(sample([THREAD, frame(6, SCK), THREAD.replace("Thread_9", "Thread_10"), frame(6, RECEIVE)]), EXPECT)
        self.assertFalse(result["pathObserved"])

    def test_same_thread_id_new_group_still_resets_ancestry(self):
        self.assertFalse(module.analyze(sample([THREAD, frame(6, SCK), THREAD, frame(6, RECEIVE)]), EXPECT)["pathObserved"])

    def test_reverse_order_is_not_capture_path(self):
        self.assertFalse(module.analyze(sample([THREAD, frame(6, RECEIVE), frame(8, SCK)]), EXPECT)["pathObserved"])

    def test_binary_images_symbols_ignored(self):
        text = sample([THREAD, frame(6, "idle  (in libsystem_kernel.dylib)")])
        text = text.replace(IMAGE, SCK + "\n" + RECEIVE + "\n" + IMAGE)
        self.assertFalse(module.analyze(text, EXPECT)["pathObserved"])

    def test_flat_summary_symbols_ignored(self):
        text = sample([THREAD, frame(6, "idle  (in libsystem_kernel.dylib)")])
        text = text.replace("\nBinary Images:", "\n" + frame(6, SCK) + "\n" + frame(8, RECEIVE) + "\nBinary Images:")
        self.assertFalse(module.analyze(text, EXPECT)["pathObserved"])

    def test_generic_sck_callback_is_insufficient(self):
        text = sample([THREAD, frame(6, "-[SCStream startCaptureWithCompletionHandler:]  (in ScreenCaptureKit)"), frame(8, RECEIVE)])
        self.assertFalse(module.analyze(text, EXPECT)["pathObserved"])

    def test_wrong_image_is_insufficient(self):
        for before, after in [("(in ScreenCaptureKit)", "(in Impostor)"), ("(in libstreamer.dylib)", "(in OtherLibrary)")]:
            with self.subTest(before=before):
                self.assertFalse(module.analyze(sample().replace(before, after), EXPECT)["pathObserved"])

    def test_substring_symbol_is_insufficient(self):
        self.assertFalse(module.analyze(sample().replace("streamer::capture::ScreenCapturerSck::", "FakePrefixstreamer::capture::ScreenCapturerSck::"), EXPECT)["pathObserved"])

    def test_encoding_is_separate_supporting_evidence(self):
        rows = [THREAD, frame(6, SCK), frame(8, RECEIVE), THREAD, frame(6, ENCODER), frame(8, VT)]
        result = module.analyze(sample(rows), EXPECT)
        self.assertTrue(result["encodingObserved"])
        self.assertTrue(result["encoderToVideoToolboxChainObserved"])
        self.assertEqual(result["encodingEvidence"][0]["threadOrdinal"], 2)

    def test_encoder_siblings_not_linked(self):
        result = module.analyze(sample([THREAD, frame(6, ENCODER), frame(6, VT)]), EXPECT)
        self.assertTrue(result["encodingObserved"])
        self.assertFalse(result["encoderToVideoToolboxChainObserved"])

    def test_surface_on_capture_chain_and_independent_surface(self):
        result = module.analyze(sample([THREAD, frame(6, SCK), frame(8, RECEIVE), frame(10, SURFACE)]), EXPECT)
        self.assertTrue(result["iosurfaceOnCapturePathObserved"])
        other = module.analyze(sample([THREAD, frame(6, SCK), frame(8, RECEIVE), frame(6, SURFACE)]), EXPECT)
        self.assertTrue(other["iosurfaceObserved"])
        self.assertFalse(other["iosurfaceOnCapturePathObserved"])

    def test_pid_and_path_mismatch_fail_closed(self):
        for key, value, code in [("pid", 124, "headerPIDMismatch"), ("executable", "/other/UURemoteServer", "headerExecutableMismatch")]:
            self.check_invalid(sample(), {**EXPECT, key: value}, code)

    def test_duplicate_identity_header_rejected(self):
        self.check_invalid("Process: UURemoteServer [123]\n" + sample(), code="missingOrDuplicateIdentityHeader")

    def test_false_identity_continuity_fails_closed(self):
        result = self.check_invalid(sample(), {**EXPECT, "identityMatchedBeforeAfter": False}, "externalProcessIdentityChanged")
        self.assertTrue(result["headerIdentityMatched"])

    def test_missing_identity_continuity_is_not_verified(self):
        result = module.analyze(sample(), EXPECT)
        self.assertTrue(result["pathObserved"])
        self.assertFalse(result["identityContinuityVerified"])
        self.assertFalse(result["outputCompletenessVerified"])

    def test_external_completion_declarations(self):
        expect = {**EXPECT, "identityMatchedBeforeAfter": True, "sampleExitCode": 0, "sampleTimedOut": False,
                  "sampleOutputTruncated": False, "sampleOutputComplete": True}
        result = module.analyze(sample(), expect)
        self.assertTrue(result["identityContinuityVerified"])
        self.assertTrue(result["outputCompletenessVerified"])
        for key, value in [("sampleExitCode", 1), ("sampleTimedOut", True), ("sampleOutputTruncated", True), ("sampleOutputComplete", False)]:
            self.check_invalid(sample(), {**expect, key: value})

    def test_strict_external_types(self):
        for key, value in [("pid", True), ("identityMatchedBeforeAfter", 1), ("sampleExitCode", False), ("sampleOutputComplete", "true")]:
            self.check_invalid(sample(), {**EXPECT, key: value})

    def test_hash_check(self):
        text = sample()
        result = module.analyze(text, {**EXPECT, "expectedSampleSHA256": hashlib.sha256(text.encode()).hexdigest()})
        self.assertTrue(result["pathObserved"])
        self.check_invalid(text, {**EXPECT, "expectedSampleSHA256": "0" * 64}, "sampleHashMismatch")

    def test_missing_footer_or_final_newline_rejected(self):
        self.check_invalid(sample(footer=False), code="unterminatedCallGraph")
        self.check_invalid(sample().rstrip("\n"), code="missingFinalNewline")
        self.check_invalid(sample().replace(IMAGE, "partial image"), code="missingOrMalformedFinalImageRow")

    def test_malformed_tree_never_preserves_positive(self):
        text = sample().replace("\n\nTotal number", "\nUNSUPPORTED GRAPH ROW\n\nTotal number")
        result = self.check_invalid(text, code="unrecognizedCallGraphRow")
        self.assertEqual(result["capturePathEvidence"], [])

    def test_missing_parent_and_bad_thread_root_rejected(self):
        self.check_invalid(sample([THREAD, frame(6, SCK), frame(10, RECEIVE)]), code="invalidOrMissingTreeAncestry")
        self.check_invalid(sample([THREAD.lstrip(), frame(6, SCK)]), code="invalidThreadRootIndentation")
        self.check_invalid(sample([frame(6, SCK), frame(8, RECEIVE)]), code="frameWithoutThreadRoot")

    def test_empty_or_bad_utf8_input_rejected(self):
        self.check_invalid("")
        self.check_invalid(b"\xff\xfe")

    def test_output_omits_raw_thread_names_parameters_and_addresses(self):
        result = module.analyze(sample(), {**EXPECT, "privateExtra": "UNRELATED_EXTERNAL_SECRET"})
        output = json.dumps(result)
        for text in ["PRIVATE_THREAD_BUSINESS_VALUE", "PRIVATE_OTHER_SYMBOL", "0x1234", "opaqueCMSampleBuffer", "UNRELATED_EXTERNAL_SECRET"]:
            self.assertNotIn(text, output)
        for key in ["captureHookHitVerified", "validFrameVerified", "remoteSessionVerified", "captureBlockingVerified", "sampleCountsAreFrameCounts"]:
            self.assertIs(result[key], False)

    def test_counts_are_rows_not_sample_weights(self):
        result = module.analyze(sample([THREAD, frame(6, SCK, 999999), frame(8, RECEIVE, 999999)]), EXPECT)
        self.assertEqual(result["counts"]["captureAncestorPaths"], 1)
        self.assertEqual(result["counts"]["callGraphRowsParsed"], 2)

    def test_historical_server_and_gui_regression(self):
        base = ROOT / "artifacts/uu-live-connected-20261101T144107Z"
        expected_hash = "81d6dddaf064631892ebc7244a66d563d492f87a33c56b14d3dbc304ef01534b"
        raw = (base / "server-sample.txt").read_bytes()
        result = module.analyze(raw, {"pid": 84053, "executable": "/Applications/UURemote.app/Contents/Helpers/UURemoteServer", "expectedSampleSHA256": expected_hash})
        self.assertEqual(result["issues"], [])
        self.assertTrue(result["pathObserved"])
        self.assertTrue(result["encodingObserved"])
        self.assertTrue(result["iosurfaceOnCapturePathObserved"])
        self.assertTrue(result["encoderToVideoToolboxChainObserved"])
        self.assertEqual(result["capturePathEvidence"][0]["nodes"][0]["sourceLine"], 1429)
        self.assertEqual(result["capturePathEvidence"][0]["nodes"][-1]["sourceLine"], 1431)
        self.assertFalse(result["identityContinuityVerified"])
        for name, pid, path in [("gui", 84593, "/Applications/UURemote.app/Contents/MacOS/UURemote"),
                                ("service", 84016, "/Applications/UURemote.app/Contents/MacOS/UURemoteService")]:
            result = module.analyze((base / (name + "-sample.txt")).read_bytes(), {"pid": pid, "executable": path})
            self.assertEqual(result["status"], "path_not_observed")

    def test_cli_new_output_only_and_invalid_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, expect, output = base / "sample.txt", base / "expect.json", base / "output.json"
            source.write_text(sample())
            expect.write_text(json.dumps(EXPECT))
            cmd = [sys.executable, str(SCRIPT), "--sample", str(source), "--expect", str(expect), "--output", str(output)]
            result = subprocess.run(cmd, capture_output=True)
            self.assertEqual(result.returncode, 0)
            saved = output.read_bytes()
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            self.assertEqual(saved, output.read_bytes())
            output.unlink()
            source.write_text("truncated")
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            self.assertFalse(json.loads(output.read_text())["pathObserved"])


if __name__ == "__main__":
    unittest.main()
