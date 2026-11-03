"""Runner integration tests. Never request real administrator authorization.

Remote applications and root worker processes are not started or stopped here.
Only private fixture executables and loopback reference receivers are used.
"""

import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
spec = importlib.util.spec_from_file_location("exam_guard_runner_under_test", PROJECT / "scripts/exam-guard.py")
runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner_module)
from guardlib.session import SessionError
from runtime.enforcement import WorkerError


def inventory(*, complete=True, processes=None, deadline=False, test_policy=False):
    return {"schemaVersion": 2, "testPolicy": test_policy, "processes": processes or [],
            "enumerationComplete": complete, "policyFileUnchanged": True,
            "coverage": {"scanDeadlineExceeded": deadline}}


class FakeWorker:
    """Only provides data and records end requests; no process/system operations."""
    def __init__(self, status=None, error=None):
        self.status, self.error, self.ends = status, error, 0

    def read_status(self):
        if self.error:
            raise self.error
        return self.status

    def request_end(self):
        self.ends += 1
        return True


class StopControlledLoop(Exception):
    pass


class BlockingInput:
    """Keep stdin open during one controlled runner iteration, then release."""
    def __init__(self):
        self.buffer = self
        self.released = threading.Event()

    def readline(self, limit):
        self.released.wait(2)
        return b""


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.args = argparse.Namespace(ui_session_id=str(uuid.uuid4()).upper(),
            session_dir=str(self.root / "session"), inventory="/nonexistent/test-inventory",
            policy=str(self.root / "policy.json"), worker=None, worker_lease=30,
            vendors=["uu", "todesk", "sunlogin"])
        self.forbid_authorization = patch.object(runner_module.DevelopmentWorker, "start",
                                                side_effect=AssertionError("REAL AUTHORIZATION FORBIDDEN IN TEST"))
        self.forbid_authorization.start()
        self.addCleanup(self.forbid_authorization.stop)
        self.runner = runner_module.Runner(self.args)

    def tearDown(self):
        self.runner.receiver.shutdown()
        self.runner.receiver.server_close()
        try:
            self.runner.store.close()
        except Exception:
            pass
        try:
            self.runner.outbox.close()
        except Exception:
            pass
        self.temp.cleanup()

    def command(self, name, identifier=None, **extra):
        self.runner.handle({"protocolVersion": 1, "command": name,
                            "requestID": identifier or uuid.uuid4().hex, **extra})

    def add_fake_healthy_worker(self):
        now = self.runner.clock()
        self.runner.worker_status = {"state": "monitoring", "failures": [], "targets": [],
            "updatedContinuousTime": now, "expiresContinuousTime": now + 60, "events": []}
        self.runner.worker = FakeWorker(self.runner.worker_status)

    def reference_ack(self):
        self.runner.deliver()
        kind, value = self.runner.results.get(timeout=2)
        self.assertEqual(kind, "delivery")
        self.assertTrue(value["serverReported"])
        self.assertTrue(value["referenceServer"])
        self.runner.ack_healthy = True
        self.runner.last_delivery = self.runner.clock()
        return value

    def active(self):
        self.reference_ack()
        self.add_fake_healthy_worker()
        self.runner.accept_inventory(inventory())
        self.command("start")
        self.assertTrue(self.runner.coordinator.snapshot()["mayDisplayQuestions"])

    def test_initial_status_never_displays_questions_or_claims_production(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.runner.status()
        status = json.loads(output.getvalue())
        self.assertEqual(status["state"], "preparing")
        self.assertFalse(status["examAllowed"])
        self.assertFalse(status["productionReady"])
        self.assertFalse(status["formalServerAuthorized"])
        self.assertEqual(status["serverMode"], "loopback-reference")
        self.assertEqual(status["esStatus"], "notApplicable")

    def test_no_helper_and_clean_inventory_cannot_start(self):
        self.reference_ack()
        self.runner.accept_inventory(inventory())
        self.command("start")
        self.assertFalse(self.runner.coordinator.snapshot()["mayDisplayQuestions"])
        self.assertIn("referenceReceiptAndWorkerRequired", self.runner.message)

    def test_unconfigured_authorization_is_explained_without_prompt(self):
        self.command("requestAuthorization")
        self.assertEqual(self.runner.reasons, ["workerExecutableRequired"])
        self.assertIsNone(self.runner.worker)
        self.assertFalse(self.runner.authorization_pending)

    def test_bad_worker_configuration_becomes_not_ready_without_crashing(self):
        self.args.worker = "/nonexistent/never-authorize"
        self.command("requestAuthorization")
        self.assertFalse(self.runner.authorization_pending)
        self.assertFalse(self.runner.coordinator.snapshot()["mayDisplayQuestions"])

    def test_explicit_authorization_cancel_has_no_changes_to_restore(self):
        worker = FakeWorker()
        worker.authorization_outcome = "cancelledBeforeLaunch"
        self.runner.worker = worker
        self.runner.finish("authorizationCancelled")
        snapshot = self.runner.coordinator.snapshot()
        self.assertEqual(snapshot["state"], "finished")
        self.assertIn("cancelled before launch", snapshot["restoreDetails"])
        self.assertEqual(worker.ends, 0)
        self.assertIsNone(self.runner.worker)

    def _run_until_terminal_restore_status(self):
        blocked_input = BlockingInput()
        original = self.runner.status
        observed = []
        def status_and_stop():
            original()
            state = self.runner.coordinator.snapshot()["state"]
            observed.append(state)
            if state in ("finished", "recoveryPending"):
                raise StopControlledLoop()
        def no_network_delivery():
            self.runner.results.put(("delivery", {"delivery": "empty", "serverReported": False}))
        output = io.StringIO()
        try:
            with patch.object(sys, "stdin", blocked_input), contextlib.redirect_stdout(output), \
                 patch.object(self.runner, "status", side_effect=status_and_stop), \
                 patch.object(self.runner, "deliver", side_effect=no_network_delivery), \
                 self.assertRaises(StopControlledLoop):
                self.runner.run()
        finally:
            blocked_input.released.set()
        return observed

    def test_unknown_launch_becomes_recovery_pending_after_bound(self):
        worker = FakeWorker()
        worker.authorization_outcome = "unknown"
        self.runner.worker = worker
        self.runner.finish("unknownAuthorizationResult")
        # Advance only the test observation of the recovery wait; no 20-second sleep.
        self.runner.restore_wait_started = self.runner.clock() - 21
        observed = self._run_until_terminal_restore_status()
        self.assertIn("recoveryPending", observed)
        self.assertFalse(self.runner.coordinator.snapshot()["mayDisplayQuestions"])
        self.assertGreater(worker.ends, 0)

    def test_cancel_result_arriving_after_end_finishes_without_unknown_restore(self):
        worker = FakeWorker()
        worker.authorization_outcome = "pending"
        self.runner.worker = worker
        self.runner.authorization_pending = True
        self.runner.finish("userEndedWhilePromptPending")
        worker.authorization_outcome = "cancelledBeforeLaunch"
        self.runner.results.put(("authorizationError", "administratorAuthorizationFailed: User canceled. (-128)"))
        observed = self._run_until_terminal_restore_status()
        self.assertIn("finished", observed)
        self.assertNotIn("recoveryPending", observed)

    def test_ended_session_cannot_start_resume_or_request_new_authorization(self):
        self.command("end")
        for operation in ("start", "resume", "inspect", "requestAuthorization"):
            self.command(operation)
        self.runner.accept_inventory(inventory())
        self.assertEqual(self.runner.coordinator.snapshot()["state"], "finished")
        self.assertFalse(self.runner.coordinator.snapshot()["mayDisplayQuestions"])
        self.assertFalse(self.runner.authorization_pending)
        self.assertFalse(self.runner.inspection_pending)

    def test_unknown_coverage_or_changed_policy_cannot_start(self):
        self.reference_ack()
        self.add_fake_healthy_worker()
        for bad in (inventory(complete=False), inventory(deadline=True), inventory(test_policy=True),
                    {**inventory(), "policyFileUnchanged": False}, {"schemaVersion": 1}):
            with self.subTest(bad=bad):
                self.runner.accept_inventory(bad)
                self.command("start")
                self.assertFalse(self.runner.coordinator.snapshot()["mayDisplayQuestions"])

    def test_forbidden_component_during_exam_immediately_pauses(self):
        self.active()
        self.runner.accept_inventory(inventory(processes=[{"pid": 123, "verifiedVendor": "uu"}]))
        self.assertEqual(self.runner.coordinator.snapshot()["state"], "paused")
        self.assertFalse(self.runner.coordinator.snapshot()["mayDisplayQuestions"])

    def test_same_request_is_idempotent_and_different_end_ids_also_safe(self):
        self.command("end", "end-first")
        self.command("end", "end-first")
        self.command("end", "end-second")
        self.command("end", "stdin-eof")
        self.assertEqual(self.runner.coordinator.snapshot()["state"], "finished")

    def test_unknown_command_pauses_without_root_operation(self):
        self.active()
        self.command("kill-arbitrary-pid", pid=1)
        self.assertFalse(self.runner.coordinator.snapshot()["mayDisplayQuestions"])
        self.assertEqual(self.runner.worker.ends, 0)

    def test_malformed_protocol_and_request_id_pause(self):
        for bad in (None, [], {"protocolVersion": 2}, {"protocolVersion": 1, "requestID": 42},
                    {"protocolVersion": 1, "requestID": "x" * 129}):
            with self.subTest(bad=bad):
                self.runner.handle(bad)
                self.assertFalse(self.runner.coordinator.snapshot()["mayDisplayQuestions"])

    def test_missing_worker_status_invalidates_cached_health(self):
        self.active()
        self.runner.worker.status = None
        self.runner.poll_worker()
        self.assertFalse(self.runner.worker_health())
        self.assertFalse(self.runner.coordinator.snapshot()["mayDisplayQuestions"])

    def test_untrusted_worker_status_invalidates_cached_health(self):
        self.active()
        self.runner.worker.error = WorkerError("untrustedWorkerStatus")
        self.runner.poll_worker()
        self.assertFalse(self.runner.worker_health())
        self.assertFalse(self.runner.coordinator.snapshot()["mayDisplayQuestions"])

    def test_finished_worker_can_be_polled_repeatedly(self):
        self.add_fake_healthy_worker()
        self.runner.worker.status = {**self.runner.worker_status, "state": "finished"}
        self.runner.poll_worker()
        self.runner.poll_worker()
        self.assertEqual(self.runner.coordinator.snapshot()["state"], "finished")
        self.assertNotIn("restoreNotStarted", " ".join(self.runner.reasons))

    def test_authorization_does_not_fabricate_post_pause_observation(self):
        self.active()
        self.runner.coordinator.pause("inspectionFailure")
        self.command("resume")
        self.assertFalse(self.runner.coordinator.snapshot()["mayDisplayQuestions"])
        self.runner.accept_inventory(inventory())
        self.command("resume")
        self.assertTrue(self.runner.coordinator.snapshot()["mayDisplayQuestions"])

    def test_failed_emission_sticks_evidence_health_false(self):
        self.active()
        self.runner.emit("badEvidence", {"answer": "must not be persisted"})
        self.assertFalse(self.runner.evidence_healthy)
        self.assertFalse(self.runner.coordinator.snapshot()["mayDisplayQuestions"])

    def test_real_reference_receipt_is_content_bound_and_not_host_attestation(self):
        receipt = self.reference_ack()["receipt"]
        self.assertEqual(receipt["sessionId"], self.runner.session)
        self.assertEqual(receipt["sequence"], 1)
        self.assertFalse(receipt["attestsClientTruth"])
        self.assertEqual(self.runner.outbox.status()["acknowledged"], 1)

    def test_inventory_subprocess_error_is_reported_as_error(self):
        self.runner.start_scan()
        kind, value = self.runner.results.get(timeout=3)
        self.assertEqual(kind, "inventoryError")
        self.assertIn("FileNotFoundError", value)

    def test_stale_checks_do_not_publish_healthy(self):
        self.active()
        self.runner.coordinator.max_observation_age = .001
        time.sleep(.005)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.runner.status()
        status = json.loads(output.getvalue())
        self.assertFalse(status["examAllowed"])
        self.assertEqual(status["health"], "degraded")

    def test_malformed_inventory_is_incomplete_not_a_crash_or_clean_result(self):
        invalid = [None, [], {**inventory(), "processes": ["bad-item"]},
                   {**inventory(), "processes": None}, {**inventory(), "coverage": "bad"}]
        missing = inventory()
        del missing["processes"]
        invalid.append(missing)
        for value in invalid:
            with self.subTest(value=value):
                verdict = runner_module.evaluate_inventory(value, ["uu"])
                self.assertFalse(verdict["coverage"])
                self.assertFalse(verdict["clean"])

    def test_test_policy_and_other_vendor_are_not_conflated(self):
        verdict = runner_module.evaluate_inventory(inventory(test_policy=True), ["uu"])
        self.assertFalse(verdict["coverage"])
        verdict = runner_module.evaluate_inventory(inventory(processes=[{"verifiedVendor": "todesk"}]), ["uu"])
        self.assertTrue(verdict["clean"])
        self.assertTrue(verdict["coverage"])


class RunnerCLITests(unittest.TestCase):
    def execute(self, data):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw) / "session"
            result = subprocess.run([sys.executable, "-B", str(PROJECT / "scripts/exam-guard.py"),
                "--ui-protocol", "--session-dir", str(directory), "--inventory", "/never-run-inventory",
                "--policy", "/never-read-policy"], input=data, capture_output=True, timeout=8)
            statuses = [json.loads(line) for line in result.stdout.decode().splitlines() if line]
            self.assertTrue(statuses, result.stderr.decode())
            self.assertTrue(all(s["examAllowed"] is False for s in statuses))
            self.assertEqual(statuses[-1]["state"], "finished", result.stderr.decode())
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_eof_finishes_without_privileged_work(self):
        self.execute(b"")

    def test_invalid_json_finishes_without_privileged_work(self):
        self.execute(b"{malformed\n")

    def test_oversized_command_finishes_without_privileged_work(self):
        self.execute(b"x" * 17000 + b"\n")

    def test_explicit_end_followed_by_eof_is_safe(self):
        self.execute(json.dumps({"protocolVersion": 1, "requestID": "user-end", "command": "end"}).encode() + b"\n")


if __name__ == "__main__":
    unittest.main()
