"""Loopback-only reference receipt server. Not a deployed exam authority."""

import hashlib
import hmac
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import math
import re
import socketserver
import threading
import urllib.parse
from datetime import datetime

from .outbox import OutboxError, canonical, open_database, private_directory, utc_now, validate_evidence


class ReceiptStore:
    def __init__(self, directory, session_id, *, max_events=10000):
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", session_id):
            raise ValueError("invalidSessionID")
        self.directory = private_directory(directory)
        self.session_id = session_id
        self.max_events = max_events
        self.lock = threading.RLock()
        self.db = open_database(self.directory / "receipts.sqlite3")
        self.db.execute("""CREATE TABLE IF NOT EXISTS receipts (
            session_id TEXT NOT NULL, sequence INTEGER NOT NULL, event_id TEXT NOT NULL,
            payload_hash TEXT NOT NULL, payload BLOB NOT NULL, receipt TEXT NOT NULL,
            PRIMARY KEY(session_id, event_id), UNIQUE(session_id, sequence))""")

    def accept(self, payload, event_id, digest):
        if len(payload) > 65536 or hashlib.sha256(payload).hexdigest() != digest:
            raise OutboxError("payloadHashMismatch")
        event = json.loads(payload)
        expected = {"schemaVersion", "sessionId", "deviceId", "bootSessionID", "policyVersion",
                    "sequence", "eventId", "event", "observedAtUTC", "monotonicSeconds",
                    "previousHash", "evidence"}
        if not isinstance(event, dict) or set(event) != expected:
            raise OutboxError("invalidEventSchema")
        if (event["schemaVersion"] != 1 or type(event["sequence"]) is not int or event["sequence"] < 1
                or event["sessionId"] != self.session_id or event["eventId"] != event_id
                or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", event_id)
                or not isinstance(event["event"], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", event["event"])
                or not isinstance(event["previousHash"], str) or not re.fullmatch(r"[a-f0-9]{64}", event["previousHash"])):
            raise OutboxError("invalidEventIdentity")
        validate_evidence(event["evidence"])
        if not isinstance(event["evidence"], dict):
            raise OutboxError("invalidEvidence")
        for name in ("deviceId", "bootSessionID", "policyVersion"):
            if not isinstance(event[name], str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", event[name]):
                raise OutboxError("invalidEventMetadata")
        if type(event["monotonicSeconds"]) not in (int, float) or not math.isfinite(event["monotonicSeconds"]):
            raise OutboxError("invalidObservationTime")
        if not isinstance(event["observedAtUTC"], str) or len(event["observedAtUTC"]) > 64:
            raise OutboxError("invalidObservationTime")
        if datetime.fromisoformat(event["observedAtUTC"].replace("Z", "+00:00")).tzinfo is None:
            raise OutboxError("invalidObservationTime")
        with self.lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                old = self.db.execute("SELECT payload_hash,receipt FROM receipts WHERE session_id=? AND event_id=?",
                                      (self.session_id, event_id)).fetchone()
                if old:
                    if old[0] != digest:
                        raise OutboxError("idempotencyConflict")
                    self.db.execute("COMMIT")
                    return json.loads(old[1]), False
                previous = self.db.execute("SELECT sequence,payload_hash FROM receipts WHERE session_id=? ORDER BY sequence DESC LIMIT 1",
                                           (self.session_id,)).fetchone()
                if (event["sequence"] != (previous[0] + 1 if previous else 1)
                        or event["previousHash"] != (previous[1] if previous else "0" * 64)):
                    raise OutboxError("sequenceOrChainConflict")
                if self.db.execute("SELECT count(*) FROM receipts").fetchone()[0] >= self.max_events:
                    raise OutboxError("receiverCapacityExceeded")
                receipt = {"accepted": True, "sessionId": self.session_id, "eventId": event_id,
                           "sequence": event["sequence"], "payloadSHA256": digest,
                           "receivedAtUTC": utc_now(), "referenceServer": True,
                           "attestsClientTruth": False}
                self.db.execute("INSERT INTO receipts VALUES(?,?,?,?,?,?)",
                                (self.session_id, event["sequence"], event_id, digest, payload, canonical(receipt).decode()))
                self.db.execute("COMMIT")
                return receipt, True
            except Exception:
                if self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                raise

    def count(self):
        with self.lock:
            return self.db.execute("SELECT count(*) FROM receipts").fetchone()[0]

    def close(self):
        self.db.close()


class ReferenceReceiver(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, address, store, token):
        if address[0] != "127.0.0.1":
            raise ValueError("referenceReceiverMustBindIPv4Loopback")
        if not isinstance(token, str) or len(token) < 32 or any(c in token for c in "\r\n"):
            raise ValueError("invalidReferenceToken")
        self.store, self.token = store, token
        self._slots = threading.BoundedSemaphore(8)
        super().__init__(address, ReceiverHandler)

    @property
    def endpoint(self):
        return f"http://127.0.0.1:{self.server_port}/v1/exam-sessions/{urllib.parse.quote(self.store.session_id, safe='')}/security-events"

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class ReceiverHandler(BaseHTTPRequestHandler):
    server_version = "ExamGuardReferenceReceiver/1"

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def log_message(self, format, *args):
        # Never print request paths, authorization headers, or arbitrary bodies.
        pass

    def _respond(self, status, value):
        body = canonical(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        authorizations = self.headers.get_all("Authorization") or []
        if len(authorizations) != 1 or not hmac.compare_digest(authorizations[0], "Bearer " + self.server.token):
            self._respond(401, {"accepted": False, "error": "unauthorized", "referenceServer": True})
            return
        expected = f"/v1/exam-sessions/{urllib.parse.quote(self.server.store.session_id, safe='')}/security-events"
        if self.path != expected:
            self._respond(404, {"accepted": False, "error": "unknownSessionEndpoint"})
            return
        lengths = self.headers.get_all("Content-Length") or []
        try:
            if (len(lengths) != 1 or self.headers.get("Transfer-Encoding")
                    or self.headers.get("Content-Type") != "application/json"):
                raise ValueError()
            length = int(lengths[0])
            if not 0 < length <= 65536:
                raise ValueError()
        except ValueError:
            self._respond(400, {"accepted": False, "error": "invalidBodySizeOrType"})
            return
        try:
            payload = self.rfile.read(length)
            if len(payload) != length:
                raise ValueError()
            receipt, created = self.server.store.accept(payload, self.headers.get("Idempotency-Key", ""),
                                                        self.headers.get("X-Payload-SHA256", ""))
            self._respond(201 if created else 200, receipt)
        except (OutboxError, ValueError, TypeError, UnicodeError) as exc:
            code = str(exc) if isinstance(exc, OutboxError) else "invalidPayload"
            status = 409 if code in ("idempotencyConflict", "sequenceOrChainConflict") else 400
            self._respond(status, {"accepted": False, "error": code})
        except Exception:
            self._respond(503, {"accepted": False, "error": "storageOrReceiverFailure"})
