import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
import ssl
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from guardlib.outbox import DurableOutbox, OutboxError, canonical, validate_endpoint
from guardlib.receiver import ReceiptStore, ReferenceReceiver


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.token = secrets.token_urlsafe(32)
        self.outbox = DurableOutbox(self.root / "outbox", "test-session")
        self.store = ReceiptStore(self.root / "server", "test-session")
        self.server = ReferenceReceiver(("127.0.0.1", 0), self.store, self.token)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        self.thread.start()
        self.endpoint = self.server.endpoint

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)
        self.store.close()
        try:
            self.outbox.close()
        except sqlite3.ProgrammingError:
            pass
        self.temp.cleanup()

    def append(self, **kwargs):
        return self.outbox.append("forbiddenComponentObserved", {"pid": 123, "vendor": "test-fixture", "actor": "unknown"}, **kwargs)

    def deliver(self, **kwargs):
        return self.outbox.deliver_once(self.endpoint, self.token, allow_loopback_http=True, **kwargs)

    def test_no_receipt_means_not_reported(self):
        result = self.append()
        self.assertFalse(result["serverReported"])
        self.assertEqual(self.outbox.status()["pending"], 1)
        self.assertEqual(self.store.count(), 0)

    def test_actual_http_receipt_matches_event_and_survives_restart(self):
        event = self.append()
        result = self.deliver()
        self.assertTrue(result["serverReported"])
        self.assertTrue(result["referenceServer"])
        self.assertFalse(result["receipt"]["attestsClientTruth"])
        self.assertEqual(result["receipt"]["payloadSHA256"], event["payloadSHA256"])
        self.outbox.close()
        self.outbox = DurableOutbox(self.root / "outbox", "test-session")
        self.assertEqual(self.outbox.status()["acknowledged"], 1)
        self.assertEqual(self.outbox.status()["pending"], 0)

    def test_missing_ack_after_server_commit_retries_idempotently(self):
        self.append()
        first = self.deliver()["receipt"]
        self.outbox.db.execute("UPDATE events SET receipt=NULL")
        result = self.deliver()
        self.assertEqual(result["receipt"], first)
        self.assertEqual(self.store.count(), 1)

    def test_wrong_token_keeps_pending_and_backoff_applies(self):
        self.append()
        result = self.outbox.deliver_once(self.endpoint, secrets.token_urlsafe(32), allow_loopback_http=True)
        self.assertFalse(result["serverReported"])
        self.assertEqual(self.outbox.status()["pending"], 1)
        self.assertEqual(self.deliver()["delivery"], "backoff")
        self.assertTrue(self.deliver(ignore_backoff=True)["serverReported"])

    def test_network_refusal_keeps_pending(self):
        self.append()
        endpoint = self.endpoint.replace(str(self.server.server_port), "1", 1)
        result = self.outbox.deliver_once(endpoint, self.token, allow_loopback_http=True, timeout=.2)
        self.assertFalse(result["serverReported"])
        self.assertEqual(self.outbox.status()["pending"], 1)

    def test_http_requires_explicit_literal_loopback(self):
        for url, opt in [(self.endpoint, False), (self.endpoint.replace("127.0.0.1", "localhost"), True),
                         (self.endpoint.replace("127.0.0.1", "192.0.2.1"), True),
                         ("file:///tmp/data", False), (self.endpoint + "?token=secret", True)]:
            with self.subTest(url=url), self.assertRaises(OutboxError):
                validate_endpoint(url, "test-session", opt)

    def test_endpoint_cannot_change_session_or_embed_credentials(self):
        for endpoint in (self.endpoint.replace("test-session", "another-session"),
                         self.endpoint.replace("127.0.0.1", "user:password@127.0.0.1")):
            with self.assertRaises(OutboxError):
                validate_endpoint(endpoint, "test-session", True)

    def test_insecure_tls_context_rejected_before_network(self):
        self.append()
        context = ssl._create_unverified_context()
        with self.assertRaises(OutboxError):
            self.outbox.deliver_once(self.endpoint, self.token, allow_loopback_http=True, ssl_context=context)

    def test_secrets_and_exam_content_fields_rejected(self):
        for evidence in ({"answer": "secret"}, {"process": {"password": "secret"}}, {"question": "x"}, {"commandLine": "x"}):
            with self.subTest(evidence=evidence), self.assertRaises(OutboxError):
                self.outbox.append("test", evidence)
        self.assertEqual(self.outbox.status()["total"], 0)

    def test_invalid_and_oversized_evidence_rejected(self):
        for evidence in ({"pid": float("nan")}, {"reason": "x" * 1025}, {"processes": [{}] * 65}):
            with self.assertRaises(OutboxError):
                self.outbox.append("test", evidence)

    def test_capacity_failure_is_not_silently_dropped_or_sequence_gap(self):
        self.outbox.close()
        self.outbox = DurableOutbox(self.root / "small", "test-session", max_events=1)
        self.append()
        with self.assertRaisesRegex(OutboxError, "outboxCapacityExceeded"):
            self.append()
        self.assertEqual(self.outbox.status()["total"], 1)
        self.assertFalse(self.outbox.status()["healthy"])

    def test_disk_write_failure_is_explicit_and_not_cleared_by_ack(self):
        self.append()
        self.outbox.db.execute("PRAGMA query_only=ON")
        with self.assertRaises(OutboxError):
            self.append()
        self.outbox.db.execute("PRAGMA query_only=OFF")
        self.assertTrue(self.deliver()["serverReported"])
        self.assertFalse(self.outbox.status()["healthy"])

    def test_reopening_with_different_identity_is_rejected(self):
        with self.assertRaisesRegex(OutboxError, "outboxIdentityMismatch"):
            DurableOutbox(self.root / "outbox", "another-session")

    def test_private_directory_and_symlink_enforced(self):
        public = self.root / "public"
        public.mkdir(mode=0o755)
        with self.assertRaises(OutboxError):
            DurableOutbox(public, "test-session")
        link = self.root / "linked"
        link.symlink_to(self.root / "outbox")
        with self.assertRaises(OutboxError):
            DurableOutbox(link, "test-session")

    def test_existing_corrupt_database_rejected(self):
        bad = self.root / "bad"
        bad.mkdir(mode=0o700)
        path = bad / "outbox.sqlite3"
        path.write_bytes(b"this is not SQLite")
        path.chmod(0o600)
        with self.assertRaises(OutboxError):
            DurableOutbox(bad, "test-session")

    def test_payload_corruption_detected_before_delivery_and_reopen(self):
        self.append()
        self.outbox.db.execute("UPDATE events SET payload=?", (b'{}',))
        self.assertEqual(self.deliver()["error"], "outboxPayloadCorrupt")
        self.outbox.close()
        with self.assertRaisesRegex(OutboxError, "outboxChainCorrupt"):
            DurableOutbox(self.root / "outbox", "test-session")

    def test_stored_receipt_corruption_is_not_trusted_after_restart(self):
        self.append()
        self.deliver()
        self.outbox.db.execute("UPDATE events SET receipt=?", ('{"accepted":true}',))
        self.outbox.close()
        with self.assertRaisesRegex(OutboxError, "outboxReceiptCorrupt"):
            DurableOutbox(self.root / "outbox", "test-session")

    def test_receiver_rejects_duplicate_id_with_different_content(self):
        self.append(event_id="fixed-event")
        self.deliver()
        event = self.outbox.records()[0]["event"]
        event["evidence"]["pid"] = 999
        payload = canonical(event)
        with self.assertRaisesRegex(OutboxError, "idempotencyConflict"):
            self.store.accept(payload, event["eventId"], hashlib.sha256(payload).hexdigest())

    def test_receiver_rejects_sequence_gap_and_wrong_chain(self):
        self.append()
        event = self.outbox.records()[0]["event"]
        for changes in ({"sequence": 2}, {"previousHash": "f" * 64}):
            changed = {**event, **changes}
            payload = canonical(changed)
            with self.assertRaisesRegex(OutboxError, "sequenceOrChainConflict"):
                self.store.accept(payload, changed["eventId"], hashlib.sha256(payload).hexdigest())

    def test_concurrent_append_sequences_are_unique_and_contiguous(self):
        failures = []
        def producer():
            try:
                for _ in range(10):
                    self.append()
            except Exception as exc:
                failures.append(exc)
        threads = [threading.Thread(target=producer) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(failures, [])
        self.assertEqual([r["event"]["sequence"] for r in self.outbox.records()], list(range(1, 41)))

    def test_server_cannot_bind_external_interface(self):
        with self.assertRaises(ValueError):
            ReferenceReceiver(("0.0.0.0", 0), self.store, self.token)

    def _bad_server(self, behavior):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(handler):
                payload = json.loads(handler.rfile.read(int(handler.headers["Content-Length"])))
                if behavior == "slow":
                    time.sleep(.35)
                if behavior == "redirect":
                    handler.send_response(307)
                    handler.send_header("Location", self.endpoint)
                    handler.end_headers()
                    return
                body = canonical({"accepted": True, "sessionId": "test-session", "eventId": payload["eventId"],
                                  "sequence": payload["sequence"], "payloadSHA256": "0" * 64,
                                  "receivedAtUTC": "2026-11-03T00:00:00Z", "referenceServer": True})
                handler.send_response(200)
                handler.send_header("Content-Length", str(len(body)))
                handler.end_headers()
                try:
                    handler.wfile.write(body)
                except BrokenPipeError:
                    pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/v1/exam-sessions/test-session/security-events"

    def test_mismatched_receipt_does_not_acknowledge(self):
        self.append()
        result = self.outbox.deliver_once(self._bad_server("mismatch"), self.token, allow_loopback_http=True)
        self.assertEqual(result["error"], "receiptMismatch")
        self.assertEqual(self.outbox.status()["pending"], 1)

    def test_redirect_is_rejected_without_forwarding_token(self):
        self.append()
        result = self.outbox.deliver_once(self._bad_server("redirect"), self.token, allow_loopback_http=True)
        self.assertEqual(result["error"], "redirectRejected")
        self.assertEqual(self.store.count(), 0)

    def test_slow_receiver_does_not_block_caller_beyond_budget(self):
        self.append()
        started = time.monotonic()
        result = self.outbox.deliver_once(self._bad_server("slow"), self.token, allow_loopback_http=True, timeout=.08)
        self.assertLess(time.monotonic() - started, .3)
        self.assertFalse(result["serverReported"])
        self.assertEqual(self.outbox.status()["pending"], 1)


if __name__ == "__main__":
    unittest.main()
