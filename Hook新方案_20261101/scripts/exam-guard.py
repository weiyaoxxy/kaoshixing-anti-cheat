#!/usr/bin/env python3
"""Local-development reactive guard. stdout is exclusively the UI JSON protocol.

Requires explicit administrator authorization to mutate real remote applications.
Reference-server receipts are real local HTTP receipts, not production authorization.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import secrets
import signal
import subprocess
import sys
import threading
import time
import uuid

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from guardlib.clock import ContinuousClock
from guardlib.session import ExamSessionCoordinator, SessionError
from guardlib.outbox import DurableOutbox, OutboxError
from guardlib.receiver import ReceiptStore, ReferenceReceiver
from runtime.enforcement import DevelopmentWorker, WorkerError


def atomic_json(path, payload):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", closefd=False) as output:
            json.dump(payload, output, ensure_ascii=False, sort_keys=True)
            output.flush()
            os.fsync(fd)
        os.replace(temporary, path)
    finally:
        os.close(fd)
        temporary.unlink(missing_ok=True)


def evaluate_inventory(snapshot, vendors):
    if (not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != 2 or snapshot.get("testPolicy") is not False
            or not isinstance(snapshot.get("processes"), list) or not isinstance(snapshot.get("coverage"), dict)
            or any(not isinstance(p, dict) or not isinstance(p.get("codeIdentity", {}), dict) for p in snapshot.get("processes", []))
            or type(snapshot.get("enumerationComplete")) is not bool or type(snapshot.get("policyFileUnchanged")) is not bool):
        return {"clean": False, "coverage": False, "targets": [], "reason": "nativeEvidenceUnavailableOrTestPolicy"}
    targets = [p for p in snapshot.get("processes", []) if p.get("verifiedVendor") in vendors
               or p.get("codeIdentity", {}).get("verifiedVendor") in vendors]
    coverage = (snapshot.get("enumerationComplete") is True
                and snapshot.get("policyFileUnchanged") is True
                and not snapshot.get("coverage", {}).get("scanDeadlineExceeded", True))
    return {"clean": not targets, "coverage": coverage, "targets": targets,
            "reason": "forbiddenComponentObserved" if targets else "checksPassed" if coverage else "inspectionIncomplete"}


class Runner:
    def __init__(self, args):
        self.args = args
        self.session = args.ui_session_id or str(uuid.uuid4()).upper()
        uuid.UUID(self.session)
        self.directory = Path(args.session_dir).absolute()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        if self.directory.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("sessionDirectoryMustBePrivateAndOwned")
        self.clock = ContinuousClock()
        self.coordinator = ExamSessionCoordinator(self.session, max_lease_seconds=60, max_observation_age=25)
        self.commands, self.results = queue.Queue(maxsize=64), queue.Queue(maxsize=64)
        self.seen_commands = set()
        self.stopping = False
        self.restore_wait_started = None
        self.authorization_pending = False
        self.inspection_pending = False
        self.worker = None
        self.worker_status = None
        self.worker_event_count = 0
        self.root_inventory_id = None
        self.sequence, self.observation = 0, 0
        self.last_scan, self.last_delivery, self.last_authorization = 0, 0, 0
        self.last_evidence_at = None
        self.last_inventory = None
        self.evidence_healthy = True
        self.ack_healthy = False
        self.message = "本机开发验证：请先检查；管理员处置需要系统认证。"
        self.reasons = ["checksRequired"]
        self.outbox = DurableOutbox(self.directory / "outbox", self.session,
                                   device_id="local-development", boot_id="reference-" + uuid.uuid4().hex,
                                   policy_version="reactive-guard-development-v1")
        self.token = secrets.token_urlsafe(32)
        self.store = ReceiptStore(self.directory / "receiver", self.session)
        self.receiver = ReferenceReceiver(("127.0.0.1", 0), self.store, self.token)
        threading.Thread(target=self.receiver.serve_forever, daemon=True).start()
        self.emit("guardInitialized", {"mode": "reactiveTerminate", "referenceServer": True})

    def emit(self, name, evidence):
        try:
            self.outbox.append(name, evidence)
        except Exception as error:
            self.evidence_healthy = False
            self.reasons = ["evidenceWriteFailed"]
            print("evidence:", type(error).__name__, str(error), file=sys.stderr)
            self.coordinator.pause("evidenceWriteFailed")

    def start_scan(self):
        if self.inspection_pending or self.stopping:
            return
        self.inspection_pending = True
        def work():
            try:
                result = subprocess.run([self.args.inventory, "--policy", self.args.policy,
                                         "--budget", "15"], capture_output=True, text=True, timeout=22)
                if result.returncode not in (0, 2):
                    raise RuntimeError("inventoryExit:" + str(result.returncode))
                data = json.loads(result.stdout)
                self.results.put(("inventory", data), timeout=1)
            except Exception as error:
                self.results.put(("inventoryError", type(error).__name__ + ":" + str(error)), timeout=1)
        threading.Thread(target=work, daemon=True).start()

    def start_authorization(self):
        if self.authorization_pending or self.worker is not None or self.stopping:
            self.message = "管理员会话已请求；请等待检查或结束后重新建立会话。"
            return
        if not self.args.worker:
            self.message = "未配置已构建的管理员开发组件；当前仅可只读检查。"
            self.reasons = ["workerExecutableRequired"]
            return
        try:
            self.worker = DevelopmentWorker(self.args.worker, self.args.vendors, lease=self.args.worker_lease)
        except Exception as error:
            self.worker = None
            self.message = "管理员组件不可用：" + str(error)[:200]
            self.reasons = ["workerExecutableUnavailable"]
            self.coordinator.pause("workerExecutableUnavailable")
            return
        self.authorization_pending = True
        self.message = "请在系统弹窗中认证。获批后将临时清理所选远控；结束或到期恢复。"
        def work():
            try:
                self.worker.start()
                self.results.put(("authorization", True), timeout=1)
            except Exception as error:
                self.results.put(("authorizationError", str(error)), timeout=1)
        threading.Thread(target=work, daemon=True).start()

    def accept_inventory(self, data):
        self.last_inventory = data
        self.last_evidence_at = self.clock()
        result = evaluate_inventory(data, self.args.vendors)
        self.observation += 1
        atomic_json(self.directory / "latest-inventory.json", data)
        self.last_scan = self.clock()
        self.reasons = [result["reason"]]
        worker_healthy = self.worker_health()
        self.coordinator.update_checks(self.observation, clean=result["clean"], coverage_complete=result["coverage"],
                                       guard_healthy=worker_healthy,
                                       evidence_healthy=self.evidence_healthy and self.ack_healthy)
        self.emit("inventoryObserved", {"clean": result["clean"], "coverageComplete": result["coverage"],
                                        "targetCount": len(result["targets"]), "source": "nativeInventory",
                                        "referenceServer": True})
        if not result["coverage"]:
            self.message = "检查存在身份或覆盖缺口；保持准备/暂停，不会显示试题。"
        elif not result["clean"]:
            self.message = "发现禁止远控组件；需管理员清理并复查。"
        elif not worker_healthy:
            self.message = "本轮未发现已验证目标，管理员监测尚未就绪。"
        else:
            self.message = "本轮检查通过，等待本机参考回执和准入。"

    def worker_health(self):
        data = self.worker_status
        return bool(data and data.get("state") == "monitoring" and not data.get("failures")
                    and 0 <= self.clock() - data.get("updatedContinuousTime", 0) < 25
                    and self.clock() < data.get("expiresContinuousTime", 0))

    def poll_worker(self):
        if self.worker is None:
            return
        try:
            status = self.worker.read_status()
            if status is None:
                self.worker_status = None
                self.coordinator.pause("workerStatusUnavailable")
                return
            self.worker_status = status
            if self.stopping:
                self.worker.request_end()
            events = status.get("events", [])
            if len(events) < self.worker_event_count:
                raise WorkerError("workerEventHistoryShrank")
            for event in events[self.worker_event_count:]:
                details = event.get("details", {})
                evidence = {"source": "developmentRootWorker", "referenceServer": True,
                            "reason": event.get("event", "unknown"), "actor": "unknown"}
                for key in ("pid", "uid", "vendor", "signingID", "cdhash", "signal", "errno"):
                    if key in details:
                        evidence[key] = details[key]
                if "returnCode" in details:
                    evidence["result"] = str(details["returnCode"])
                self.emit("workerObservation", evidence)
            self.worker_event_count = len(events)
            inventory = status.get("inventoryEvidence")
            if isinstance(inventory, dict) and inventory.get("schemaVersion") == 2:
                identity = (inventory.get("scanStartedAtUTC"), inventory.get("policySHA256"))
                if identity != self.root_inventory_id:
                    self.root_inventory_id = identity
                    self.accept_inventory(inventory)
            if status.get("targets") and self.coordinator.snapshot()["state"] == "exam":
                self.coordinator.pause("forbiddenComponentObserved")
            if status.get("state") in ("finished", "recoveryPending"):
                if not self.stopping:
                    self.finish("workerSessionEnded")
                if self.coordinator.snapshot()["state"] in ("restoring", "recoveryPending"):
                    self.coordinator.complete_restore(status["state"] == "finished", "root worker: " + status["state"])
            elif not self.worker_health() and self.coordinator.snapshot()["state"] == "exam":
                self.coordinator.pause("workerUnavailable")
        except Exception as error:
            self.worker_status = None
            self.coordinator.pause("workerStatusUnavailable")
            self.reasons = [str(error)[:200]]

    def finish(self, reason):
        if not self.stopping:
            self.stopping = True
            self.restore_wait_started = self.clock()
            self.coordinator.begin_finish(reason)
            self.message = "已停止开考和新处置，正在核验恢复。"
        if self.worker:
            if getattr(self.worker, "authorization_outcome", None) == "cancelledBeforeLaunch":
                self.worker = None
                self.coordinator.complete_restore(True, "system authorization cancelled before launch")
                return
            try:
                self.worker.request_end()
            except Exception as error:
                self.reasons = ["restoreRequestPending:" + str(error)[:150]]
        elif not self.authorization_pending and self.coordinator.snapshot()["state"] in ("restoring", "recoveryPending"):
            self.coordinator.complete_restore(True, "no privileged changes requested")

    def handle(self, request):
        if not isinstance(request, dict) or request.get("protocolVersion") != 1:
            self.coordinator.pause("invalidUICommand"); return
        request_id = request.get("requestID")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            self.coordinator.pause("invalidRequestID"); return
        if request_id in self.seen_commands:
            return
        if len(self.seen_commands) >= 10000:
            self.finish("commandBudgetExceeded"); return
        self.seen_commands.add(request_id)
        command = request.get("command")
        if command == "end":
            self.finish("uiEnded")
        elif self.stopping:
            return
        elif command == "pause":
            self.coordinator.pause(str(request.get("reason", "uiPause"))[:128])
        elif command == "inspect":
            self.start_scan()
        elif command == "requestAuthorization":
            self.start_authorization()
        elif command in ("start", "resume"):
            try:
                if command == "resume" and self.coordinator.snapshot()["state"] == "exam":
                    self.coordinator.pause("uiReconfirmation")
                self.authorize_reference()
                self.coordinator.start() if command == "start" else self.coordinator.resume()
            except Exception as error:
                self.message = "无法开始/继续：" + str(error)
        else:
            self.coordinator.pause("unsupportedUICommand")

    def authorize_reference(self):
        if not self.ack_healthy or not self.worker_health() or self.last_inventory is None:
            raise SessionError("referenceReceiptAndWorkerRequired")
        if self.last_evidence_at is None or self.clock() - self.last_evidence_at > 20:
            raise SessionError("freshInventoryRequired")
        # Only accept_inventory may create an observation; authorization cannot
        # relabel an old measurement as a fresh sample after an error.
        # Explicit local demo authorization, not a signed production exam permit.
        self.coordinator.authorize(30, "local-reference-" + uuid.uuid4().hex, server_authorized=True)
        self.last_authorization = self.clock()

    def deliver(self):
        try:
            result = self.outbox.deliver_once(self.receiver.endpoint, self.token, allow_loopback_http=True)
            self.results.put(("delivery", result), timeout=1)
        except Exception as error:
            self.results.put(("deliveryError", str(error)), timeout=1)

    def status(self):
        snapshot = self.coordinator.snapshot()
        healthy = (all(snapshot["checks"].values()) and snapshot["observationAgeSeconds"] is not None
                   and snapshot["observationAgeSeconds"] <= self.coordinator.max_observation_age
                   and self.worker_health() and self.ack_healthy and self.evidence_healthy
                   and snapshot["leaseRemainingSeconds"] > 0)
        self.sequence += 1
        status = {"protocolVersion": 1, "type": "status", "sessionID": self.session,
                  "sequence": self.sequence, "state": snapshot["state"], "canStart": snapshot["mayStart"],
                  "examAllowed": snapshot["mayDisplayQuestions"],
                  "health": "healthy" if healthy else "degraded",
                  "message": self.message, "reasons": self.reasons, "mode": "reactiveTerminate",
                  "backend": "development-root-worker" if self.worker else "unprivileged",
                  "serverMode": "loopback-reference", "productionReady": False,
                  "esStatus": "notApplicable", "serverReported": self.ack_healthy,
                  "formalServerAuthorized": False, "coordinator": snapshot}
        atomic_json(self.directory / "guard-status.json", status)
        print(json.dumps(status, ensure_ascii=False), flush=True)

    def run(self):
        def reader():
            try:
                while True:
                    raw = sys.stdin.buffer.readline(16385)
                    if not raw:
                        self.commands.put({"protocolVersion": 1, "command": "end", "requestID": "stdin-eof"}, timeout=1)
                        return
                    if len(raw) > 16384:
                        raise ValueError("commandTooLarge")
                    self.commands.put(json.loads(raw), timeout=1)
            except Exception:
                self.commands.put({"protocolVersion": 1, "command": "end", "requestID": "stdin-error"}, timeout=1)
        threading.Thread(target=reader, daemon=True).start()
        delivery_pending = False
        self.status()  # Before any inspection or mutation.
        try:
            while True:
                started = self.clock()
                for _ in range(16):
                    try:
                        self.handle(self.commands.get_nowait())
                    except queue.Empty:
                        break
                for _ in range(32):
                    try:
                        kind, value = self.results.get_nowait()
                    except queue.Empty:
                        break
                    if kind == "inventory":
                        self.inspection_pending = False; self.accept_inventory(value)
                    elif kind == "inventoryError":
                        self.inspection_pending = False
                        self.last_inventory = None; self.last_evidence_at = None
                        self.coordinator.pause("inventoryFailed"); self.reasons = [value[:200]]
                    elif kind == "authorization":
                        self.authorization_pending = False; self.message = "管理员开发会话已请求，等待受保护状态与清理结果。"
                    elif kind == "authorizationError":
                        self.authorization_pending = False; self.reasons = [value[:300]]; self.message = "系统认证未完成或组件启动失败。"
                        if self.stopping:
                            self.finish("authorizationClosedAfterEnd")
                    elif kind in ("delivery", "deliveryError"):
                        delivery_pending = False
                        # No pending events is not itself a new receipt.
                        if kind == "delivery":
                            if value.get("acknowledged") is True or value.get("serverReported") is True:
                                self.ack_healthy = True
                                self.last_delivery = self.clock()
                            elif value.get("delivery") == "pending" or value.get("error"):
                                self.ack_healthy = False; self.coordinator.pause("referenceDeliveryFailed")
                        else:
                            self.ack_healthy = False; self.coordinator.pause("referenceDeliveryFailed")
                self.poll_worker()
                for event in self.coordinator.drain_events():
                    self.emit(event["event"], {"epoch": event["epoch"], "state": event["state"], "referenceServer": True})
                if not delivery_pending:
                    delivery_pending = True
                    threading.Thread(target=self.deliver, daemon=True).start()
                if self.last_delivery and self.clock() - self.last_delivery > 20:
                    self.ack_healthy = False; self.coordinator.pause("referenceReceiptStale")
                if self.worker is None and not self.stopping and self.last_inventory is not None and self.clock() - self.last_scan > 5:
                    self.start_scan()
                if not self.stopping and self.worker_health() and self.clock() - self.last_authorization > 10:
                    try:
                        self.authorize_reference()
                    except SessionError:
                        pass
                snapshot = self.coordinator.snapshot()
                if (self.stopping and snapshot["state"] == "restoring" and self.restore_wait_started is not None
                        and self.clock() - self.restore_wait_started > 20):
                    self.coordinator.complete_restore(False, "恢复尚未确认；独立管理员组件继续按有限租约处理，请保留会话记录。")
                if snapshot["requiresRecovery"] and snapshot["reason"] == "leaseExpired":
                    self.finish("examLeaseExpired")
                self.status()
                if snapshot["state"] == "finished":
                    # A final receipt attempt is bounded; local restore does not wait on delivery.
                    break
                time.sleep(max(0.02, 0.5 - (self.clock() - started)))
        except (BrokenPipeError, KeyboardInterrupt):
            self.finish("uiDisconnected")
        finally:
            if self.worker and self.coordinator.snapshot()["state"] != "finished":
                self.worker.request_end()  # Independent native guardian remains until restore/TTL.
            self.receiver.shutdown()
            self.receiver.server_close()
            self.store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui-protocol", action="store_true", required=True)
    parser.add_argument("--ui-session-id")
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--worker")
    parser.add_argument("--worker-lease", type=int, default=180)
    parser.add_argument("--vendors", default="uu,todesk,sunlogin", type=lambda v: v.split(","))
    args = parser.parse_args()
    Runner(args).run()


if __name__ == "__main__":
    main()
