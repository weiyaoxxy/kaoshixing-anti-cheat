#!/usr/bin/env python3
"""Synthetic evidence tests only; never starts, inspects or changes UU."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/analyze-hook-invocations.py"
spec = importlib.util.spec_from_file_location("hook_invocations", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

EXPECT = {"sessionID": "test-session", "pid": 321, "processStartSeconds": 1800000000,
          "processStartMicroseconds": 123456, "executable": "/test/owned-capture-host",
          "startHostTime": 100.0, "endHostTime": 200.0}
INSTANCE = "12345678-1234-1234-1234-123456789abc"


class Trace:
    def __init__(self, version="1.3"):
        self.rows = []
        self.version = version
        self.add("image_loaded")

    def add(self, event, **fields):
        row = {key: EXPECT[key] for key in ("sessionID", "pid", "processStartSeconds", "processStartMicroseconds", "executable")}
        row.update(schemaVersion=2, hookVersion=self.version, identityAvailable=True,
                   priorLogWriteFailures=0,
                   hookInstanceID=INSTANCE, uid=501, sequence=len(self.rows) + 1,
                   hostTime=100.0 + len(self.rows) * 0.01, mode="audit", event=event)
        row.update(fields)
        self.rows.append(row)
        return self

    def raw(self):
        return b"".join(json.dumps(row).encode() + b"\n" for row in self.rows)

    def analyze(self, expect=None):
        return module.analyze(self.raw(), EXPECT if expect is None else expect)

    def snapshot(self, success=True):
        self.add("capture_call", callID="shot-1", api="SCScreenshotManager.captureImage", operation="snapshot_request")
        self.add("capture_result", callID="shot-1", api="SCScreenshotManager.captureImage",
                 success=success, validImageOrSample=success, hasImage=success, hasSample=False,
                 width=64 if success else 0, height=48 if success else 0)
        return self

    def stream(self, sck=True, success=True, setup=True, start=True):
        api = "SCStream.init" if sck else "CGDisplayStreamCreateWithDispatchQueue"
        self.add("capture_call", callID="create-1", api=api, operation="stream_create", streamID="stream-1")
        self.add("stream_create_result", callID="create-1", api=api, streamID="stream-1", success=success)
        if sck and setup:
            self.output("output-1")
        if sck and start:
            self.add("capture_call", callID="start-1", api="SCStream.startCapture", operation="stream_start",
                     streamID="stream-1", creationCallID="create-1")
        return self

    def output(self, output):
        self.add("capture_call", callID="setup-" + output, api="SCStream.addStreamOutput", operation="stream_setup",
                 streamID="stream-1", creationCallID="create-1", outputID=output, type=0)
        self.add("stream_setup_result", callID="setup-" + output, api="SCStream.addStreamOutput", streamID="stream-1", outputID=output, success=True)
        return self

    def frame(self, sck=True, valid=True, output="output-1", count=1, fid="frame-1"):
        self.add("sck_stream_frame" if sck else "display_stream_frame", streamID="stream-1", outputID=output,
                 frameID=fid, validScreenFrame=valid, frameCount=count, screenFrameCount=count if valid else 0,
                 width=64 if valid else 0, height=48 if valid else 0, **({"type": 0, "frameStatus": 0, "sampleValid": valid, "dataReady": valid} if sck else {"status": 0}))
        return self

    def shareable(self, success=True):
        fields = {"callID": "enumerate-1", "api": module.SHAREABLE_CONTENT_API}
        self.add("shareable_content_request", **fields)
        self.add("shareable_content_result", **fields, success=success,
                 errorDomain="" if success else "SyntheticDiagnostic", errorCode=0 if success else -37,
                 displayCount=1 if success else 0, windowCount=2 if success else 0, applicationCount=3 if success else 0)
        return self

    def control(self, start=True, success=True):
        fields = {"callID": "cg-start" if start else "cg-stop",
                  "api": "CGDisplayStreamStart" if start else "CGDisplayStreamStop", "streamProvided": True}
        self.add("display_stream_control_call", **fields)
        self.add("display_stream_control_result", **fields, success=success, returnCode=0 if success else 1001)
        return self


class EvidenceTests(unittest.TestCase):
    def invalid(self, trace, code=None):
        result = trace.analyze() if isinstance(trace, Trace) else module.analyze(trace, EXPECT)
        self.assertEqual(result["level"], "invalid_or_incomplete")
        self.assertFalse(result["evidenceUsable"])
        if code:
            self.assertIn(code, [issue["code"] for issue in result["issues"]])
        return result

    def test_empty_has_no_evidence(self):
        result = module.analyze(b"", EXPECT)
        self.assertEqual(result["level"], "no_evidence")
        self.assertFalse(result["coverage"]["logTailCompletenessVerified"])

    def test_loaded_and_installed_are_not_capture(self):
        result = Trace().add("hook_installed", selector="startCaptureWithCompletionHandler:").analyze()
        self.assertEqual(result["level"], "loaded_only")
        self.assertFalse(result["flags"]["captureEntryObserved"])

    def test_sck_init_setup_stop_update_are_not_capture(self):
        trace = Trace().stream(start=False)
        trace.add("capture_call", callID="stop-1", streamID="stream-1", creationCallID="create-1",
                  api="SCStream.stopCapture", operation="stream_stop")
        trace.add("capture_call", callID="update-1", streamID="stream-1", creationCallID="create-1",
                  api="SCStream.updateConfiguration", operation="stream_update")
        self.assertEqual(trace.analyze()["level"], "loaded_only")

    def test_request_without_result_is_entry_only(self):
        trace = Trace().add("capture_call", callID="shot", api="CGDisplayCreateImage", operation="snapshot_request")
        result = trace.analyze()
        self.assertEqual(result["level"], "capture_entry_observed")
        self.assertEqual(result["coverage"]["pendingSnapshotResults"], 1)

    def test_failed_snapshot_is_entry_only(self):
        self.assertEqual(Trace().snapshot(False).analyze()["level"], "capture_entry_observed")

    def test_valid_snapshot_is_frame_evidence(self):
        result = Trace().snapshot().analyze()
        self.assertEqual(result["level"], "frame_callback_observed")
        self.assertTrue(result["flags"]["successfulSnapshotObserved"])
        self.assertFalse(result["captureBlockingVerified"])
        self.assertTrue(result["localEvidenceOnly"])

    def test_cg_create_is_entry_even_if_creation_fails(self):
        self.assertEqual(Trace().stream(sck=False, success=False).analyze()["level"], "capture_entry_observed")

    def test_sck_start_without_frame_is_entry(self):
        self.assertEqual(Trace().stream().analyze()["level"], "capture_entry_observed")

    def test_valid_cg_frame(self):
        self.assertEqual(Trace().stream(sck=False).frame(sck=False).analyze()["level"], "frame_callback_observed")

    def test_valid_sck_frame(self):
        result = Trace().stream().frame().analyze()
        self.assertEqual(result["level"], "frame_callback_observed")
        self.assertFalse(result["flags"]["originalCallbackReturnObserved"])

    def test_invalid_callback_is_not_frame_evidence(self):
        self.assertEqual(Trace().stream().frame(valid=False).analyze()["level"], "capture_entry_observed")

    def test_forwarded_valid_frame_remains_local_only(self):
        trace = Trace().stream().frame().add("frame_forwarded", frameID="frame-1", streamID="stream-1", outputID="output-1", validScreenFrame=True, originalCallbackReturned=True)
        result = trace.analyze()
        self.assertTrue(result["flags"]["originalCallbackReturnObserved"])
        self.assertFalse(result["remoteSessionVerified"])
        self.assertFalse(result["captureBlockingVerified"])

    def test_sampled_frame_counters_can_skip(self):
        result = Trace().stream().frame().frame(count=60, fid="frame-60").analyze()
        self.assertEqual(result["level"], "frame_callback_observed")
        self.assertEqual(result["counts"]["validScreenFrameRecords"], 2)

    def test_multiple_outputs_have_independent_counters(self):
        trace = Trace().stream().output("output-2").frame(output="output-1").frame(output="output-2", fid="second-output-frame-1")
        self.assertEqual(trace.analyze()["level"], "frame_callback_observed")

    def test_failed_duplicate_add_preserves_successful_output(self):
        trace = Trace().stream().frame()
        trace.add("capture_call", callID="repeat-add", api="SCStream.addStreamOutput", operation="stream_setup",
                  streamID="stream-1", creationCallID="create-1", outputID="output-1", type=0)
        trace.add("stream_setup_result", callID="repeat-add", api="SCStream.addStreamOutput", streamID="stream-1", outputID="output-1", success=False)
        trace.frame(count=2, fid="frame-2")
        result = trace.analyze()
        self.assertEqual(result["level"], "frame_callback_observed")
        self.assertEqual(result["counts"]["validScreenFrameRecords"], 2)

    def test_manifest_identity_is_strict(self):
        for key, value in [("sessionID", "old-session"), ("pid", 322), ("processStartSeconds", 1800000001),
                           ("processStartMicroseconds", 123457), ("executable", "/other/host")]:
            with self.subTest(key=key):
                trace = Trace().snapshot()
                trace.rows[-1][key] = value
                self.invalid(trace, "identityMismatch_" + key)

    def test_missing_identity_and_old_schema(self):
        for field, value in [("identityAvailable", False), ("schemaVersion", 1), ("hookVersion", "1.2"), ("sessionID", "")]:
            with self.subTest(field=field):
                trace = Trace()
                trace.rows[0][field] = value
                self.invalid(trace)

    def test_sequence_duplicate_gap_and_reorder(self):
        for bad in (1, 3, 0, True):
            with self.subTest(sequence=bad):
                trace = Trace().snapshot()
                trace.rows[1]["sequence"] = bad
                self.invalid(trace)

    def test_initial_sequence_must_start_at_one_and_loaded(self):
        trace = Trace()
        trace.rows[0]["sequence"] = 3
        self.invalid(trace)
        trace = Trace()
        trace.rows[0]["event"] = "hook_installed"
        self.invalid(trace, "missingInitialImageLoaded")

    def test_mixed_hook_instances_rejected(self):
        trace = Trace().snapshot()
        trace.rows[-1]["hookInstanceID"] = "12345678-1234-1234-1234-123456789abd"
        self.invalid(trace, "mixedHookInstances")

    def test_time_window_and_monotonic_order(self):
        for value in (99.9, 200.1, -1, True, float("inf")):
            with self.subTest(host=value):
                trace = Trace().snapshot()
                trace.rows[-1]["hostTime"] = value
                self.invalid(trace)
        trace = Trace().snapshot()
        trace.rows[-1]["hostTime"] = 100.0
        self.invalid(trace, "hostTimeOutOfOrder")

    def test_truncated_final_line_and_invalid_json(self):
        raw = Trace().snapshot().raw()
        self.invalid(raw[:-1], "truncatedFinalLine")
        self.invalid(raw + b'{"broken":\n', "invalidJSON")

    def test_duplicate_json_keys_rejected(self):
        raw = Trace().raw().replace(b'"schemaVersion": 2', b'"schemaVersion": 2, "schemaVersion": 2')
        self.invalid(raw, "duplicateJSONKey")

    def test_wrong_snapshot_result_call_and_api(self):
        for field, value in [("callID", "different-call"), ("api", "CGDisplayCreateImage")]:
            trace = Trace().snapshot()
            trace.rows[-1][field] = value
            self.invalid(trace)

    def test_snapshot_requires_boolean_validity_and_dimensions(self):
        for field, value in [("validImageOrSample", False), ("width", 0), ("height", True), ("success", "true"), ("hasImage", False)]:
            with self.subTest(field=field):
                trace = Trace().snapshot()
                trace.rows[-1][field] = value
                self.invalid(trace)

    def test_duplicate_result_rejected(self):
        trace = Trace().snapshot()
        fields = {k: v for k, v in trace.rows[-1].items() if k in ("callID", "api", "success", "validImageOrSample", "hasImage", "hasSample", "width", "height")}
        trace.add("capture_result", **fields)
        self.invalid(trace, "duplicateCallResult")

    def test_operation_cannot_relabel_stop_as_capture(self):
        trace = Trace().add("capture_call", callID="forged", api="SCStream.stopCapture", operation="snapshot_request")
        self.invalid(trace, "unsupportedAPIOrOperationMismatch")

    def test_malformed_container_fields_return_invalid_instead_of_crashing(self):
        for field, value in [("api", []), ("api", {}), ("operation", {}), ("callID", [])]:
            trace = Trace().add("capture_call", callID="shot", api="CGDisplayCreateImage", operation="snapshot_request")
            trace.rows[-1][field] = value
            self.invalid(trace)

    def test_orphan_frames_and_failed_creation(self):
        self.invalid(Trace().frame(), "orphanStreamFrame")
        self.invalid(Trace().stream(sck=False, success=False).frame(sck=False), "frameWithoutSuccessfulStreamCreation")

    def test_sck_frames_require_setup_success_and_start(self):
        self.invalid(Trace().stream(setup=False).frame(), "sckFrameWithoutSuccessfulScreenSetupAndStart")
        self.invalid(Trace().stream(start=False).frame(), "sckFrameWithoutSuccessfulScreenSetupAndStart")
        trace = Trace().stream().frame()
        trace.rows[4]["success"] = False
        self.invalid(trace, "sckFrameWithoutSuccessfulScreenSetupAndStart")

    def test_creation_call_must_match(self):
        trace = Trace().stream()
        trace.rows[3]["creationCallID"] = "unrelated-create"
        self.invalid(trace, "streamCreationCallMismatch")

    def test_non_screen_incomplete_or_invalid_data_cannot_be_valid(self):
        for field, value in [("type", 1), ("frameStatus", 2), ("sampleValid", False), ("dataReady", False), ("width", 0), ("screenFrameCount", 0)]:
            with self.subTest(field=field):
                trace = Trace().stream().frame()
                trace.rows[-1][field] = value
                self.invalid(trace)

    def test_frame_id_counter_and_family_correlations(self):
        self.invalid(Trace().stream().frame().frame(fid="frame-2"), "duplicateFrameCounter")
        self.invalid(Trace().stream().frame().frame(count=2), "missingOrDuplicateFrameID")
        self.invalid(Trace().stream().frame(sck=False), "streamFrameAPIFamilyMismatch")

    def test_orphan_forwarding_does_not_prove_anything(self):
        self.invalid(Trace().add("frame_forwarded", frameID="missing", streamID="stream-1", outputID="output-1", validScreenFrame=True), "orphanForwardedFrame")

    def test_expected_final_sequence_detects_complete_line_tail_deletion(self):
        trace = Trace().snapshot()
        expect = {**EXPECT, "expectedFinalSequence": 3}
        self.assertTrue(trace.analyze(expect)["coverage"]["logTailCompletenessVerified"])
        trace.rows.pop()
        self.assertEqual(trace.analyze(expect)["level"], "invalid_or_incomplete")
        self.assertEqual(trace.analyze()["level"], "capture_entry_observed")
        self.assertFalse(trace.analyze()["coverage"]["logTailCompletenessVerified"])

    def test_invalid_tail_preserves_prefix_but_not_usable_grade(self):
        trace = Trace().snapshot()
        result = self.invalid(trace.raw() + b"broken", "truncatedFinalLine")
        self.assertTrue(result["flags"]["frameEvidenceObserved"])
        self.assertTrue(result["flagsDescribeValidatedPrefixOnly"])
        self.assertFalse(result["evidenceUsable"])
        self.assertEqual(result["coverage"]["lastValidatedSequence"], 3)

    def test_semantic_failure_not_counted_as_validated_prefix(self):
        trace = Trace().snapshot()
        trace.rows[-1]["width"] = 0
        result = self.invalid(trace)
        self.assertEqual(result["coverage"]["lastValidatedSequence"], 2)
        self.assertEqual(result["coverage"]["pendingSnapshotResults"], 1)
        self.assertFalse(result["flags"]["frameEvidenceObserved"])

    def test_unknown_diagnostics_are_not_capture(self):
        result = Trace().add("future_diagnostic", success=True).analyze()
        self.assertEqual(result["level"], "loaded_only")
        self.assertEqual(result["counts"]["uninterpretedEvents"], 1)

    def test_version14_retains_existing_frame_evidence_rules(self):
        for version in module.HOOK_VERSIONS:
            with self.subTest(version=version):
                result = Trace(version).stream().frame().analyze()
                self.assertEqual(result["level"], "frame_callback_observed")
                self.assertEqual(result["hookVersion"], version)

    def test_mixed_versions_rejected_in_both_directions(self):
        for first, second in (("1.3", "1.4"), ("1.4", "1.3")):
            with self.subTest(first=first):
                trace = Trace(first).snapshot()
                trace.rows[-1]["hookVersion"] = second
                result = self.invalid(trace, "mixedHookVersions")
                self.assertEqual(result["hookVersion"], first)
                self.assertFalse(result["flags"]["frameEvidenceObserved"])

    def test_unsupported_or_malformed_versions_rejected(self):
        for version in ("1.5", "1.2", None, [], {}, 1.4):
            with self.subTest(version=version):
                self.invalid(Trace(version), "unsupportedHookVersion")

    def test_external_version_binding(self):
        result = Trace("1.4").analyze({**EXPECT, "hookVersion": "1.4"})
        self.assertTrue(result["evidenceUsable"])
        result = Trace("1.4").analyze({**EXPECT, "hookVersion": "1.3"})
        self.assertEqual(result["issues"][0]["code"], "identityMismatch_hookVersion")
        for value in ("1.5", [], None):
            result = Trace().analyze({**EXPECT, "hookVersion": value})
            self.assertEqual(result["issues"][0]["code"], "invalidExpectedHookVersion")

    def test_diagnostics_never_upgrade_capture_or_frame_evidence(self):
        for success in (True, False):
            with self.subTest(success=success):
                result = Trace("1.4").shareable(success).control(success=success).control(start=False, success=success).analyze()
                self.assertEqual(result["level"], "loaded_only")
                self.assertEqual(result["counts"]["diagnosticEvents"], 6)
                self.assertFalse(result["flags"]["captureEntryObserved"])
                self.assertFalse(result["flags"]["frameEvidenceObserved"])
                self.assertFalse(result["captureBlockingVerified"])
                self.assertEqual(result["coverage"]["pendingShareableContentResults"], 0)
                self.assertEqual(result["coverage"]["pendingDisplayStreamControlResults"], 0)

    def test_diagnostics_cannot_establish_stream_for_frame(self):
        self.invalid(Trace("1.4").control().frame(sck=False), "orphanStreamFrame")

    def test_old_version_cannot_claim_new_diagnostic_contract(self):
        self.invalid(Trace("1.3").shareable(), "diagnosticRequiresHookVersion14")
        self.invalid(Trace("1.3").control(), "diagnosticRequiresHookVersion14")

    def test_diagnostic_results_require_matching_request(self):
        for family in ("shareable", "control"):
            with self.subTest(family=family):
                trace = getattr(Trace("1.4"), family)()
                trace.rows[-1]["callID"] = "unrelated"
                self.invalid(trace, "orphanCallResult")
        trace = Trace("1.4").control()
        trace.rows[-1]["api"] = "CGDisplayStreamStop"
        self.invalid(trace, "callResultAPIMismatch")

    def test_diagnostic_and_capture_call_ids_share_namespace(self):
        trace = Trace("1.4").control()
        trace.add("capture_call", api="CGDisplayCreateImage", callID="cg-start", operation="snapshot_request")
        self.invalid(trace, "missingOrDuplicateCallID")
        trace = Trace("1.4").snapshot()
        trace.add("shareable_content_request", api=module.SHAREABLE_CONTENT_API, callID="shot-1")
        self.invalid(trace, "missingOrDuplicateCallID")

    def test_duplicate_diagnostic_result_rejected(self):
        trace = Trace("1.4").shareable()
        result = {key: trace.rows[-1][key] for key in ("api", "callID", "success", "errorDomain", "errorCode", "displayCount", "windowCount", "applicationCount")}
        trace.add("shareable_content_result", **result)
        self.invalid(trace, "duplicateCallResult")

    def test_shareable_count_and_error_types_are_strict(self):
        for field, value in (("displayCount", -1), ("windowCount", True), ("applicationCount", "3"),
                             ("errorDomain", []), ("errorDomain", "bad\nvalue"), ("errorCode", True),
                             ("errorCode", 2 ** 63), ("success", 1)):
            with self.subTest(field=field, value=value):
                trace = Trace("1.4").shareable()
                trace.rows[-1][field] = value
                self.invalid(trace)

    def test_success_cannot_contradict_diagnostic_error(self):
        trace = Trace("1.4").shareable()
        trace.rows[-1]["errorDomain"] = "SyntheticDiagnostic"
        self.invalid(trace, "inconsistentDiagnosticSuccess")
        trace = Trace("1.4").control()
        trace.rows[-1]["returnCode"] = 1001
        self.invalid(trace, "inconsistentDiagnosticSuccess")

    def test_display_control_argument_and_return_types_are_strict(self):
        for field, value, code in (("streamProvided", False, "diagnosticArgumentMismatch"),
                                   ("streamProvided", 1, "diagnosticArgumentMismatch"),
                                   ("returnCode", True, "invalidDisplayControlReturnCode")):
            trace = Trace("1.4").control()
            trace.rows[-1][field] = value
            self.invalid(trace, code)
        trace = Trace("1.4").control()
        trace.rows[1]["streamProvided"] = None
        self.invalid(trace, "invalidDiagnosticStreamProvided")

    def test_diagnostic_api_cannot_be_relabelled(self):
        for value in ([], "SCStream.startCapture", "CGDisplayStreamCreate"):
            trace = Trace("1.4").control()
            trace.rows[1]["api"] = value
            self.invalid(trace, "unsupportedDiagnosticAPI")

    def test_unfinished_diagnostics_only_affect_coverage(self):
        trace = Trace("1.4").shareable()
        trace.rows.pop()
        trace.add("display_stream_control_call", api="CGDisplayStreamStart", callID="cg-start", streamProvided=True)
        result = trace.analyze()
        self.assertEqual(result["level"], "loaded_only")
        self.assertEqual(result["coverage"]["pendingShareableContentResults"], 1)
        self.assertEqual(result["coverage"]["pendingDisplayStreamControlResults"], 1)
        self.assertFalse(result["flags"]["captureEntryObserved"])

    def test_diagnostic_extra_flags_do_not_forge_frame_evidence(self):
        trace = Trace("1.4").shareable()
        trace.rows[-1].update(validScreenFrame=True, frameEvidenceObserved=True, windowTitle="synthetic-secret")
        result = trace.analyze()
        self.assertEqual(result["level"], "loaded_only")
        self.assertNotIn("synthetic-secret", json.dumps(result))

    def test_external_expectation_is_required(self):
        for field in EXPECT:
            with self.subTest(field=field):
                expect = dict(EXPECT)
                del expect[field]
                self.assertEqual(module.analyze(Trace().raw(), expect)["level"], "invalid_or_incomplete")

    def test_malformed_manifest_types(self):
        for field, value in [("pid", True), ("processStartMicroseconds", 1000000), ("startHostTime", float("nan")), ("endHostTime", 99), ("expectedFinalSequence", -1)]:
            expect = {**EXPECT, field: value}
            self.assertEqual(module.analyze(Trace().raw(), expect)["level"], "invalid_or_incomplete")

    def test_input_limits(self):
        old = module.MAX_LOG_BYTES
        try:
            module.MAX_LOG_BYTES = 10
            self.invalid(Trace().raw(), "logSizeLimitExceeded")
        finally:
            module.MAX_LOG_BYTES = old

    def test_prior_write_failures_are_always_incomplete(self):
        for value in (1, -1, True, None):
            trace = Trace().snapshot()
            trace.rows[-1]["priorLogWriteFailures"] = value
            self.invalid(trace, "priorLogWriteFailureOrMissingCounter")

    def test_parallel_callback_counter_order_is_not_log_sequence_order(self):
        trace = Trace().stream().frame(count=2, fid="frame-2").frame(count=1, fid="frame-1")
        self.assertEqual(trace.analyze()["level"], "frame_callback_observed")

    def test_impossible_counter_increase_is_rejected_after_sorting(self):
        trace = Trace().stream().frame(count=60, fid="frame-60").frame(count=61, fid="frame-61")
        trace.rows[-2]["screenFrameCount"] = 1
        trace.rows[-1]["screenFrameCount"] = 50
        self.invalid(trace, "inconsistentScreenFrameCounter")

    def test_callback_return_requires_explicit_return_flag(self):
        trace = Trace().stream().frame().add("frame_forwarded", frameID="frame-1", streamID="stream-1", outputID="output-1", validScreenFrame=True, originalCallbackReturned=False)
        self.invalid(trace, "callbackReturnNotConfirmed")

    def test_missing_underlying_frame_validity_is_rejected(self):
        for field in ("type", "frameStatus", "sampleValid", "dataReady"):
            trace = Trace().stream().frame()
            del trace.rows[-1][field]
            self.invalid(trace)

    def test_cli_output_is_new_and_invalid_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log, expect, output = root / "events.jsonl", root / "expect.json", root / "result.json"
            log.write_bytes(Trace().snapshot().raw())
            expect.write_text(json.dumps(EXPECT))
            command = [sys.executable, str(SCRIPT), "--log", str(log), "--expect", str(expect), "--output", str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = output.read_bytes()
            self.assertEqual(json.loads(original)["level"], "frame_callback_observed")
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), original)
            output.unlink()
            log.write_bytes(b"truncated")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            self.assertEqual(json.loads(output.read_text())["level"], "invalid_or_incomplete")


if __name__ == "__main__":
    unittest.main()
