import math
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from guardlib.clock import ContinuousClock
from guardlib.session import ExamSessionCoordinator, SessionError


class TestClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class ExamSessionTests(unittest.TestCase):
    def setUp(self):
        self.clock = TestClock()
        self.session = ExamSessionCoordinator("test-session", clock=self.clock)

    def healthy(self, serial=0, **changes):
        checks = dict(clean=True, coverage_complete=True, guard_healthy=True, evidence_healthy=True)
        checks.update(changes)
        return self.session.update_checks(serial, **checks)

    def ready(self):
        self.healthy()
        self.session.authorize(30, "authorization-1", server_authorized=True)

    def active(self):
        self.ready()
        self.session.start()

    def test_new_and_recreated_objects_never_show_questions(self):
        self.assertFalse(self.session.snapshot()["mayDisplayQuestions"])
        with self.assertRaises(SessionError):
            self.session.start()
        self.active()
        replacement = ExamSessionCoordinator("test-session", clock=self.clock)
        self.assertEqual(replacement.snapshot()["state"], "preparing")

    def test_checks_alone_never_allow_start(self):
        self.healthy()
        self.assertFalse(self.session.snapshot()["mayStart"])

    def test_authorization_requires_server_fact_and_fresh_checks(self):
        with self.assertRaisesRegex(SessionError, "serverAuthorizationRequired"):
            self.session.authorize(30, "one")
        with self.assertRaisesRegex(SessionError, "freshHealthyChecksRequired"):
            self.session.authorize(30, "one", server_authorized=True)

    def test_ready_requires_checks_and_lease_then_explicit_start(self):
        self.ready()
        snapshot = self.session.snapshot()
        self.assertEqual(snapshot["state"], "ready")
        self.assertTrue(snapshot["mayStart"])
        self.assertFalse(snapshot["mayDisplayQuestions"])
        self.assertEqual(snapshot["esStatus"], "notApplicable")
        self.assertTrue(self.session.start()["mayDisplayQuestions"])

    def test_all_bad_checks_pause_and_clear_authorization(self):
        for key in ("clean", "coverage_complete", "guard_healthy", "evidence_healthy"):
            with self.subTest(key=key):
                self.setUp()
                self.active()
                epoch = self.session.snapshot()["epoch"]
                self.healthy(1, **{key: False})
                snapshot = self.session.snapshot()
                self.assertEqual(snapshot["state"], "paused")
                self.assertFalse(snapshot["mayDisplayQuestions"])
                self.assertEqual(snapshot["leaseRemainingSeconds"], 0)
                self.assertGreater(snapshot["epoch"], epoch)

    def test_clean_scan_does_not_resume_and_old_authorization_is_rejected(self):
        self.active()
        self.healthy(1, clean=False)
        self.healthy(2)
        with self.assertRaises(SessionError):
            self.session.resume()
        with self.assertRaisesRegex(SessionError, "authorizationAlreadyUsed"):
            self.session.authorize(30, "authorization-1", server_authorized=True)
        self.session.authorize(30, "authorization-2", server_authorized=True)
        self.assertEqual(self.session.snapshot()["state"], "paused")
        self.assertTrue(self.session.resume()["mayDisplayQuestions"])

    def test_out_of_order_observation_cannot_undo_failure(self):
        self.active()
        self.healthy(5, clean=False)
        self.assertFalse(self.healthy(4))
        self.assertFalse(self.healthy(5))
        self.assertFalse(self.session.snapshot()["checks"]["clean"])

    def test_check_staleness_pauses_even_with_valid_lease(self):
        self.active()
        self.clock.now += 10.01
        snapshot = self.session.tick()
        self.assertEqual(snapshot["state"], "paused")
        self.assertEqual(snapshot["reason"], "observationStale")

    def test_sleep_elapsed_counts_and_exact_lease_expiry_requires_recovery(self):
        self.healthy()
        self.session.authorize(5, "one", server_authorized=True)
        self.session.start()
        self.clock.now += 5
        snapshot = self.session.tick()
        self.assertEqual(snapshot["reason"], "leaseExpired")
        self.assertTrue(snapshot["requiresRecovery"])
        self.assertFalse(snapshot["mayDisplayQuestions"])

    def test_ready_lease_expiry_returns_preparing(self):
        self.ready()
        self.clock.now += 31
        self.assertEqual(self.session.snapshot()["state"], "preparing")
        with self.assertRaises(SessionError):
            self.session.start()

    def test_expired_lease_cannot_be_extended_after_the_fact(self):
        self.active()
        self.clock.now += 31
        self.session.tick()
        self.healthy(5)
        with self.assertRaisesRegex(SessionError, "recoveryRequired"):
            self.session.authorize(30, "after-expiry", server_authorized=True)
        self.assertTrue(self.session.snapshot()["requiresRecovery"])

    def test_manual_pause_requires_new_observation_before_resume_authorization(self):
        self.active()
        self.session.pause()
        with self.assertRaisesRegex(SessionError, "postPauseObservationRequired"):
            self.session.authorize(30, "after-pause", server_authorized=True)
        self.healthy(1)
        self.session.authorize(30, "after-pause", server_authorized=True)
        self.assertTrue(self.session.resume()["mayDisplayQuestions"])

    def test_end_invalidates_epoch_and_cannot_be_revived_by_late_work(self):
        self.active()
        before = self.session.snapshot()["epoch"]
        ended = self.session.begin_finish()
        self.assertGreater(ended["epoch"], before)
        self.assertFalse(ended["mayDisplayQuestions"])
        self.assertFalse(self.healthy(10))
        with self.assertRaises(SessionError):
            self.session.authorize(30, "late", server_authorized=True)
        self.assertEqual(self.session.begin_finish()["epoch"], ended["epoch"])

    def test_restore_failure_explicit_and_retry_can_finish(self):
        self.session.begin_finish("cancelled")
        failed = self.session.complete_restore(False, "job changed externally")
        self.assertEqual(failed["state"], "recoveryPending")
        self.assertTrue(failed["requiresRecovery"])
        self.assertEqual(self.session.complete_restore(True)["state"], "finished")
        with self.assertRaises(SessionError):
            self.session.complete_restore(True)

    def test_restore_cannot_be_claimed_before_starting_recovery(self):
        with self.assertRaises(SessionError):
            self.session.complete_restore(True)

    def test_concurrent_finish_and_observations_never_reactivate(self):
        self.active()
        barrier = threading.Barrier(3)
        def observe():
            barrier.wait()
            for number in range(1, 100):
                self.healthy(number)
        def finish():
            barrier.wait()
            for _ in range(20):
                self.session.begin_finish()
        threads = [threading.Thread(target=observe), threading.Thread(target=finish)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        snapshot = self.session.snapshot()
        self.assertEqual(snapshot["state"], "restoring")
        self.assertFalse(snapshot["mayDisplayQuestions"])

    def test_invalid_ttl_and_boolean_checks_rejected(self):
        for duration in (0, -1, 121, math.inf, math.nan, True):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                self.session.authorize(duration, "one", server_authorized=True)
        with self.assertRaises(ValueError):
            self.healthy(clean=1)
        with self.assertRaises(ValueError):
            self.healthy(-1)

    def test_clock_reversal_removes_display_permission(self):
        self.active()
        self.clock.now -= 1
        with self.assertRaises(SessionError):
            self.session.snapshot()
        self.clock.now += 2
        self.assertFalse(self.session.snapshot()["mayDisplayQuestions"])

    def test_internal_event_overflow_fails_closed_without_silent_resume(self):
        self.session = ExamSessionCoordinator("test-session", clock=self.clock, event_capacity=4)
        self.active()
        for number in range(5):
            try:
                self.session.authorize(30, f"renew-{number}", server_authorized=True)
            except SessionError:
                break
        snapshot = self.session.snapshot()
        self.assertGreater(snapshot["droppedStateEvents"], 0)
        self.assertFalse(snapshot["mayDisplayQuestions"])
        self.session.drain_events()
        self.healthy(20)
        with self.assertRaises(SessionError):
            self.session.authorize(30, "new", server_authorized=True)

    def test_continuous_clock_real_api_is_monotonic(self):
        clock = ContinuousClock()
        a, b = clock(), clock()
        self.assertGreaterEqual(b, a)
        self.assertEqual(clock.source, "mach_continuous_time" if sys.platform == "darwin" else "CLOCK_BOOTTIME")


if __name__ == "__main__":
    unittest.main()
