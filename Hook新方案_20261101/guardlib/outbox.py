"""Bounded SQLite evidence outbox with explicit, content-bound server receipts.

This protects against accidental loss/corruption and avoids blind acknowledgments.
It is not hardware attestation and cannot make a compromised host truthful.
"""

import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import queue
import re
import sqlite3
import ssl
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

from .clock import ContinuousClock


class OutboxError(RuntimeError):
    pass


EVIDENCE_KEYS = frozenset({
    "pid", "uid", "role", "vendor", "componentID", "teamID", "signingID", "cdhash",
    "reason", "result", "source", "mode", "policyVersion", "epoch", "identityStrength",
    "process", "processes", "checks", "clean", "coverageComplete", "guardHealthy",
    "evidenceHealthy", "observationId", "scanId", "birthTime", "startTimeSeconds",
    "startTimeMicroseconds", "pidversion", "bootSessionID", "executionIdentity",
    "signatureStatus", "dynamicValidationStatus", "staticValidationStatus", "errorCode",
    "errno", "signal", "actionId", "relatedEventId", "attempt", "durationSeconds",
    "targetCount", "unknownCount", "verifiedCount", "policyDigest", "restored",
    "restoreStatus", "coverage", "enumerationComplete", "identityCoverage",
    "pathUnavailableCount", "timedOutCount", "unresolvedCount", "monotonicSeconds",
    "observerGeneration", "state", "serverReported", "referenceServer", "actor",
    "remoteSessionVerified", "runningMemoryAttested", "examGateActuallyEnforced",
    "leaseRemainingSeconds", "authorizationID", "machineBootId", "product",
})


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def validate_evidence(value, depth=0):
    if depth > 6:
        raise OutboxError("evidenceTooDeep")
    if isinstance(value, dict):
        if len(value) > 64 or any(key not in EVIDENCE_KEYS for key in value):
            raise OutboxError("unsupportedEvidenceField")
        for child in value.values():
            validate_evidence(child, depth + 1)
    elif isinstance(value, list):
        if len(value) > 64:
            raise OutboxError("evidenceListTooLong")
        for child in value:
            validate_evidence(child, depth + 1)
    elif isinstance(value, str):
        if len(value) > 1024:
            raise OutboxError("evidenceStringTooLong")
    elif value is None or type(value) is bool:
        pass
    elif type(value) in (int, float):
        if not math.isfinite(value) or abs(value) > 2 ** 63:
            raise OutboxError("invalidEvidenceNumber")
    else:
        raise OutboxError("unsupportedEvidenceValue")


def private_directory(directory):
    path = Path(directory).absolute()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
        raise OutboxError("stateDirectoryMustBeRealDirectory")
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise OutboxError("stateDirectoryMustBePrivateAndOwned")
    return path


def open_database(path, max_bytes=32 * 1024 * 1024):
    if path.is_symlink():
        raise OutboxError("databaseSymlinkRejected")
    # Precreate with private permissions before SQLite sees it.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    info = os.fstat(fd)
    os.close(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise OutboxError("databaseMustBePrivateAndOwned")
    db = sqlite3.connect(path, timeout=1.0, isolation_level=None, check_same_thread=False)
    try:
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        if os.sys.platform == "darwin":
            db.execute("PRAGMA fullfsync=ON")
        page_size = db.execute("PRAGMA page_size").fetchone()[0]
        db.execute(f"PRAGMA max_page_count={max(32, max_bytes // page_size)}")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise OutboxError("databaseIntegrityCheckFailed")
        return db
    except Exception:
        db.close()
        raise


def validate_endpoint(endpoint, session_id, allow_loopback_http=False):
    parsed = urllib.parse.urlsplit(endpoint)
    try:
        port = parsed.port
    except ValueError as exc:
        raise OutboxError("invalidEndpoint") from exc
    if (not parsed.hostname or parsed.username or parsed.password or parsed.fragment
            or parsed.query or port == 0):
        raise OutboxError("invalidEndpoint")
    expected_path = "/v1/exam-sessions/" + urllib.parse.quote(session_id, safe="") + "/security-events"
    if parsed.path != expected_path:
        raise OutboxError("endpointSessionMismatch")
    loopback = False
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        pass
    # Literal loopback only: no DNS resolution that could redirect the test token.
    if parsed.scheme == "http":
        if not allow_loopback_http or not loopback:
            raise OutboxError("httpsRequiredExceptExplicitLoopbackTest")
    elif parsed.scheme != "https":
        raise OutboxError("httpsRequired")
    return parsed.scheme == "http"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        fp.close()
        raise OutboxError("redirectRejected")

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


def receipt_matches(receipt, session_id, event_id, sequence, digest, *, require_reference=False):
    if (not isinstance(receipt, dict) or receipt.get("accepted") is not True
            or receipt.get("sessionId") != session_id or receipt.get("eventId") != event_id
            or type(receipt.get("sequence")) is not int or receipt["sequence"] != sequence
            or receipt.get("payloadSHA256") != digest
            or not isinstance(receipt.get("receivedAtUTC"), str)
            or len(receipt["receivedAtUTC"]) > 64
            or (require_reference and receipt.get("referenceServer") is not True)):
        return False
    try:
        return datetime.fromisoformat(receipt["receivedAtUTC"].replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


class DurableOutbox:
    def __init__(self, directory, session_id, *, device_id="local-test-device",
                 boot_id="unattested-local-boot", policy_version="guard-v1",
                 max_events=10000, max_payload_bytes=16 * 1024 * 1024,
                 clock=None, wall_clock=utc_now):
        for text in (session_id, device_id, boot_id, policy_version):
            if not isinstance(text, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", text):
                raise ValueError("invalidIdentityMetadata")
        if type(max_events) is not int or max_events < 1 or type(max_payload_bytes) is not int or max_payload_bytes < 1024:
            raise ValueError("invalidOutboxCapacity")
        self.directory = private_directory(directory)
        self.session_id = session_id
        self.clock = clock or ContinuousClock()
        self.wall_clock = wall_clock
        self.max_events, self.max_payload_bytes = max_events, max_payload_bytes
        self._lock, self._delivery_lock = threading.RLock(), threading.Lock()
        self._last_error = None
        self._next_attempt = 0.0
        self._failure_count = 0
        self._integrity_fault = None
        self._network_worker = None
        try:
            self.db = open_database(self.directory / "outbox.sqlite3", max_payload_bytes + 8 * 1024 * 1024)
            self.db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self.db.execute("""CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL,
                payload BLOB NOT NULL, payload_hash TEXT NOT NULL,
                receipt TEXT, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT)""")
            metadata = {"sessionId": session_id, "deviceId": device_id,
                        "bootSessionID": boot_id, "policyVersion": policy_version}
            self.db.execute("BEGIN IMMEDIATE")
            for key, value in metadata.items():
                old = self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
                if old and old[0] != value:
                    raise OutboxError("outboxIdentityMismatch")
                self.db.execute("INSERT OR IGNORE INTO metadata VALUES (?, ?)", (key, value))
            self.db.execute("COMMIT")
            self.metadata = metadata
            self._verify_chain()
        except (sqlite3.Error, OSError) as exc:
            if hasattr(self, "db"):
                self.db.close()
            raise OutboxError("outboxStorageUnavailable") from exc
        except Exception:
            if hasattr(self, "db"):
                if self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                self.db.close()
            raise

    def _verify_chain(self):
        previous, expected = "0" * 64, 1
        for sequence, event_id, payload, digest, raw_receipt in self.db.execute(
                "SELECT sequence,event_id,payload,payload_hash,receipt FROM events ORDER BY sequence"):
            if sequence != expected or hashlib.sha256(payload).hexdigest() != digest:
                raise OutboxError("outboxChainCorrupt")
            if raw_receipt is not None:
                try:
                    receipt = json.loads(raw_receipt)
                except (ValueError, UnicodeError) as exc:
                    raise OutboxError("outboxReceiptCorrupt") from exc
                if not receipt_matches(receipt, self.session_id, event_id, sequence, digest):
                    raise OutboxError("outboxReceiptCorrupt")
            try:
                event = json.loads(payload)
            except (ValueError, UnicodeError) as exc:
                raise OutboxError("outboxPayloadCorrupt") from exc
            if (event.get("previousHash") != previous or event.get("sequence") != sequence
                    or event.get("eventId") != event_id or event.get("sessionId") != self.session_id):
                raise OutboxError("outboxChainCorrupt")
            previous, expected = digest, expected + 1

    def append(self, event_type, evidence, *, event_id=None):
        if not isinstance(event_type, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", event_type):
            raise OutboxError("invalidEventType")
        if not isinstance(evidence, dict):
            raise OutboxError("evidenceMustBeObject")
        validate_evidence(evidence)
        identifier = event_id or str(uuid.uuid4())
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", identifier):
            raise OutboxError("invalidEventID")
        with self._lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                count, size = self.db.execute("SELECT count(*),coalesce(sum(length(payload)),0) FROM events").fetchone()
                last = self.db.execute("SELECT sequence,payload_hash FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
                sequence = last[0] + 1 if last else 1
                event = {"schemaVersion": 1, **self.metadata, "sequence": sequence,
                         "eventId": identifier, "event": event_type,
                         "observedAtUTC": self.wall_clock(), "monotonicSeconds": self.clock(),
                         "previousHash": last[1] if last else "0" * 64, "evidence": evidence}
                payload = canonical(event)
                if len(payload) > 64 * 1024 or count >= self.max_events or size + len(payload) > self.max_payload_bytes:
                    raise OutboxError("outboxCapacityExceeded")
                digest = hashlib.sha256(payload).hexdigest()
                self.db.execute("INSERT INTO events(sequence,event_id,payload,payload_hash) VALUES(?,?,?,?)",
                                (sequence, identifier, payload, digest))
                self.db.execute("COMMIT")
                return {"eventId": identifier, "sequence": sequence, "payloadSHA256": digest,
                        "serverReported": False, "delivery": "pending"}
            except Exception as exc:
                if self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                self._last_error = type(exc).__name__ + ":appendFailed"
                self._integrity_fault = self._last_error
                if isinstance(exc, OutboxError):
                    raise
                raise OutboxError("outboxAppendFailed") from exc

    def deliver_once(self, endpoint, token, *, allow_loopback_http=False, timeout=3.0,
                     ssl_context=None, ignore_backoff=False):
        test_http = validate_endpoint(endpoint, self.session_id, allow_loopback_http)
        if not isinstance(token, str) or len(token) < 32 or any(c in token for c in "\r\n"):
            raise OutboxError("invalidBearerToken")
        if not math.isfinite(timeout) or not 0 < timeout <= 30:
            raise ValueError("invalidRequestTimeout")
        if ssl_context is not None and (ssl_context.verify_mode != ssl.CERT_REQUIRED or not ssl_context.check_hostname):
            raise OutboxError("insecureTLSContextRejected")
        if not self._delivery_lock.acquire(blocking=False):
            return {"delivery": "busy", "serverReported": False}
        try:
            if not ignore_backoff and self.clock() < self._next_attempt:
                return {"delivery": "backoff", "serverReported": False}
            with self._lock:
                row = self.db.execute("SELECT sequence,event_id,payload,payload_hash FROM events WHERE receipt IS NULL ORDER BY sequence LIMIT 1").fetchone()
            if row is None:
                return {"delivery": "empty", "serverReported": False}
            sequence, identifier, payload, digest = row
            try:
                if hashlib.sha256(payload).hexdigest() != digest:
                    raise OutboxError("outboxPayloadCorrupt")
                context = ssl_context or ssl.create_default_context()
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                                    urllib.request.HTTPSHandler(context=context))
                request = urllib.request.Request(endpoint, data=payload, method="POST", headers={
                    "Authorization": "Bearer " + token, "Content-Type": "application/json",
                    "Idempotency-Key": identifier, "X-Payload-SHA256": digest})
                if self._network_worker is not None and self._network_worker.is_alive():
                    return {"delivery": "busy", "serverReported": False}
                result_queue = queue.Queue(maxsize=1)
                deadline = time.monotonic() + timeout
                def exchange():
                    try:
                        with opener.open(request, timeout=timeout) as response:
                            if response.status not in (200, 201):
                                raise OutboxError("unexpectedReceiptStatus")
                            chunks, size = [], 0
                            while True:
                                if time.monotonic() >= deadline:
                                    raise OutboxError("requestDeadlineExceeded")
                                chunk = response.read1(min(4096, 16385 - size))
                                if not chunk:
                                    break
                                chunks.append(chunk)
                                size += len(chunk)
                                if size > 16384:
                                    raise OutboxError("receiptTooLarge")
                            result_queue.put((True, json.loads(b"".join(chunks))))
                    except Exception as error:
                        if isinstance(error, urllib.error.HTTPError):
                            error.close()
                        result_queue.put((False, error))
                self._network_worker = threading.Thread(target=exchange, daemon=True,
                                                        name="guard-evidence-delivery")
                self._network_worker.start()
                try:
                    success, received_value = result_queue.get(timeout=timeout)
                except queue.Empty as exc:
                    raise OutboxError("requestDeadlineExceeded") from exc
                if not success:
                    raise received_value
                receipt = received_value
                if not receipt_matches(receipt, self.session_id, identifier, sequence, digest,
                                       require_reference=test_http):
                    raise OutboxError("receiptMismatch")
                with self._lock:
                    self.db.execute("BEGIN IMMEDIATE")
                    self.db.execute("UPDATE events SET receipt=?,attempts=attempts+1,last_error=NULL WHERE sequence=? AND payload_hash=?",
                                    (canonical(receipt).decode(), sequence, digest))
                    self.db.execute("COMMIT")
                self._failure_count, self._next_attempt = 0, 0.0
                self._last_error = None
                return {"delivery": "acknowledged", "serverReported": True,
                        "referenceServer": receipt.get("referenceServer") is True, "receipt": receipt}
            except Exception as exc:
                # Keep credentials, endpoint query strings and arbitrary response text out of logs.
                self._last_error = str(exc) if isinstance(exc, OutboxError) else type(exc).__name__
                self._failure_count += 1
                self._next_attempt = self.clock() + min(60.0, 2 ** min(self._failure_count - 1, 6))
                with self._lock:
                    if self.db.in_transaction:
                        self.db.execute("ROLLBACK")
                    try:
                        self.db.execute("UPDATE events SET attempts=attempts+1,last_error=? WHERE sequence=?",
                                        (self._last_error[:128], sequence))
                    except sqlite3.Error:
                        self._last_error = "outboxFailureRecordUnavailable"
                return {"delivery": "pending", "serverReported": False,
                        "eventId": identifier, "error": self._last_error}
        finally:
            self._delivery_lock.release()

    def status(self):
        with self._lock:
            try:
                total, acknowledged, size = self.db.execute(
                    "SELECT count(*),coalesce(sum(receipt IS NOT NULL),0),coalesce(sum(length(payload)),0) FROM events").fetchone()
                return {"sessionId": self.session_id, "total": total, "pending": total - acknowledged,
                        "acknowledged": acknowledged, "payloadBytes": size, "lastError": self._last_error,
                        "healthy": self._last_error is None and self._integrity_fault is None and total < self.max_events and size < self.max_payload_bytes,
                        "integrityFault": self._integrity_fault,
                        "referenceReceiverProvesHostTruth": False}
            except sqlite3.Error as exc:
                raise OutboxError("outboxStatusUnavailable") from exc

    def records(self):
        with self._lock:
            return [{"event": json.loads(payload), "payloadSHA256": digest,
                     "receipt": json.loads(receipt) if receipt else None, "attempts": attempts}
                    for payload, digest, receipt, attempts in self.db.execute(
                        "SELECT payload,payload_hash,receipt,attempts FROM events ORDER BY sequence")]

    def close(self):
        with self._lock:
            self.db.close()
