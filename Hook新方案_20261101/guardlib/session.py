"""Pure exam gate/state coordinator. It does not kill, restore, or verify a server.

The caller must authenticate server authorizations and provide fresh observation
facts. A new object always starts in preparing; persisted JSON cannot resume an
exam or extend a previous lease. A UI must hide questions unless snapshot says
mayDisplayQuestions=True and must enforce its own connection/freshness timeout.
"""

from collections import deque
import math
import threading

from .clock import ContinuousClock


class SessionError(RuntimeError):
    pass


class ExamSessionCoordinator:
    STATES = {"preparing", "ready", "exam", "paused", "restoring", "recoveryPending", "finished"}

    def __init__(self, session_id, *, clock=None, max_lease_seconds=120.0,
                 max_observation_age=10.0, event_capacity=512):
        if not isinstance(session_id, str) or not session_id or len(session_id) > 128:
            raise ValueError("invalidSessionID")
        for number in (max_lease_seconds, max_observation_age):
            if isinstance(number, bool) or not math.isfinite(number) or number <= 0:
                raise ValueError("invalidTimeLimit")
        if type(event_capacity) is not int or event_capacity < 4:
            raise ValueError("invalidEventCapacity")
        self.session_id = session_id
        self.clock = clock or ContinuousClock()
        self.max_lease_seconds = float(max_lease_seconds)
        self.max_observation_age = float(max_observation_age)
        self._lock = threading.RLock()
        self.state = "preparing"
        self.epoch = 1
        self.reason = "checksRequired"
        self._observation_id = -1
        self._observed_at = None
        self._checks = {"clean": False, "coverageComplete": False,
                        "guardHealthy": False, "evidenceHealthy": False}
        self._deadline = None
        self._authorization_id = None
        self._used_authorizations = set()
        self._last_clock = None
        self._events = deque()
        self._event_capacity = event_capacity
        self._event_sequence = 0
        self._dropped_events = 0
        self._restore_details = None
        self._recovery_required = False
        self._resume_after_observation_id = -1

    def _now(self):
        now = float(self.clock())
        if not math.isfinite(now) or (self._last_clock is not None and now < self._last_clock):
            self._deadline = None
            if self.state in ("exam", "ready"):
                self.state = "paused" if self.state == "exam" else "preparing"
            self.reason = "clockInvalid"
            self._recovery_required = True
            raise SessionError("clockInvalid")
        self._last_clock = now
        return now

    def _record(self, event, **data):
        self._event_sequence += 1
        if len(self._events) >= self._event_capacity:
            self._events.popleft()
            self._dropped_events += 1
            self._checks["evidenceHealthy"] = False
            self._deadline = None
            if self.state == "exam":
                self.state = "paused"
            elif self.state == "ready":
                self.state = "preparing"
            self.reason = "stateEventQueueOverflow"
        self._events.append({"sequence": self._event_sequence, "event": event,
                             "state": self.state, "epoch": self.epoch, **data})

    def _healthy(self, now):
        return (all(self._checks.values()) and self._observed_at is not None
                and 0 <= now - self._observed_at <= self.max_observation_age
                and self._dropped_events == 0)

    def _valid_lease(self, now):
        return self._deadline is not None and now < self._deadline

    def _pause(self, reason):
        if reason == "leaseExpired":
            self._recovery_required = True
        if self.state == "exam":
            self.state = "paused"
            self.epoch += 1
            self._resume_after_observation_id = self._observation_id
            self._record("examPaused", reason=reason)
        elif self.state == "ready":
            self.state = "preparing"
            self.epoch += 1
            self._record("examReadinessLost", reason=reason)
        self.reason = reason
        self._deadline = None
        self._authorization_id = None

    def _tick_locked(self, now):
        if self.state in ("exam", "ready"):
            if not self._valid_lease(now):
                self._pause("leaseExpired")
            elif not self._healthy(now):
                self._pause("observationStale" if self._observed_at is None or
                            now - self._observed_at > self.max_observation_age else "checksFailed")

    def update_checks(self, observation_id, *, clean, coverage_complete,
                      guard_healthy, evidence_healthy):
        if type(observation_id) is not int or observation_id < 0:
            raise ValueError("invalidObservationID")
        if any(type(x) is not bool for x in (clean, coverage_complete, guard_healthy, evidence_healthy)):
            raise ValueError("checksMustBeBooleans")
        with self._lock:
            now = self._now()
            self._tick_locked(now)
            if self.state in ("restoring", "recoveryPending", "finished"):
                return False
            if observation_id <= self._observation_id:
                return False
            self._observation_id, self._observed_at = observation_id, now
            self._checks = {"clean": clean, "coverageComplete": coverage_complete,
                            "guardHealthy": guard_healthy, "evidenceHealthy": evidence_healthy}
            if not self._healthy(now):
                self._pause("forbiddenComponentObserved" if not clean else "checksFailed")
            # A clean observation never resumes or obtains a server authorization.
            return True

    def authorize(self, ttl_seconds, authorization_id, *, server_authorized=False):
        if (isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float))
                or not math.isfinite(ttl_seconds) or not 0 < ttl_seconds <= self.max_lease_seconds):
            raise ValueError("invalidLeaseDuration")
        if not isinstance(authorization_id, str) or not authorization_id or len(authorization_id) > 128:
            raise ValueError("invalidAuthorizationID")
        with self._lock:
            now = self._now()
            self._tick_locked(now)
            if server_authorized is not True:
                raise SessionError("serverAuthorizationRequired")
            if self.state in ("restoring", "recoveryPending", "finished"):
                raise SessionError("sessionEnding")
            if self._recovery_required:
                raise SessionError("recoveryRequired")
            if authorization_id in self._used_authorizations:
                raise SessionError("authorizationAlreadyUsed")
            if len(self._used_authorizations) >= 10000:
                self._pause("authorizationBudgetExceeded")
                raise SessionError("authorizationBudgetExceeded")
            if not self._healthy(now):
                raise SessionError("freshHealthyChecksRequired")
            if self.state == "paused" and self._observation_id <= self._resume_after_observation_id:
                raise SessionError("postPauseObservationRequired")
            self._used_authorizations.add(authorization_id)
            self._authorization_id = authorization_id
            self._deadline = now + float(ttl_seconds)
            if self.state == "preparing":
                self.state, self.reason = "ready", "checksAndAuthorizationReady"
            self._record("leaseAuthorized", authorizationID=authorization_id)
            return self._snapshot_locked(now)

    def start(self):
        with self._lock:
            now = self._now()
            self._tick_locked(now)
            if self.state != "ready" or not self._healthy(now) or not self._valid_lease(now):
                raise SessionError("notReady")
            self.state, self.reason = "exam", "examStarted"
            self._record("examStarted")
            return self._snapshot_locked(now)

    def resume(self):
        with self._lock:
            now = self._now()
            if self.state != "paused" or not self._healthy(now) or not self._valid_lease(now):
                raise SessionError("freshChecksAndNewAuthorizationRequired")
            self.state, self.reason = "exam", "examResumed"
            self._record("examResumed")
            return self._snapshot_locked(now)

    def pause(self, reason="operatorPause"):
        with self._lock:
            self._now()
            if self.state in ("preparing", "ready", "exam", "paused"):
                self._pause(str(reason)[:128])
            return self.snapshot()

    def begin_finish(self, reason="examEnded"):
        with self._lock:
            now = self._now()
            if self.state not in ("restoring", "recoveryPending", "finished"):
                self.epoch += 1
                self.state, self.reason = "restoring", str(reason)[:128]
                self._deadline = None
                self._authorization_id = None
                self._record("restoreStarted", reason=self.reason)
            return self._snapshot_locked(now)

    def complete_restore(self, success, details=""):
        if type(success) is not bool:
            raise ValueError("restoreResultMustBeBoolean")
        with self._lock:
            now = self._now()
            if self.state not in ("restoring", "recoveryPending"):
                raise SessionError("restoreNotStarted")
            self.state = "finished" if success else "recoveryPending"
            self.reason = "restoreCompleted" if success else "restoreFailed"
            self._restore_details = str(details)[:1024]
            self._record(self.reason)
            return self._snapshot_locked(now)

    def tick(self):
        return self.snapshot()

    def _snapshot_locked(self, now):
        return {"schemaVersion": 1, "sessionId": self.session_id, "mode": "reactiveTerminate",
                "state": self.state, "epoch": self.epoch, "reason": self.reason,
                "checks": dict(self._checks), "observationId": self._observation_id,
                "observationAgeSeconds": None if self._observed_at is None else now - self._observed_at,
                "leaseRemainingSeconds": max(0, self._deadline - now) if self._deadline else 0,
                "mayDisplayQuestions": self.state == "exam" and self._healthy(now) and self._valid_lease(now),
                "mayStart": self.state == "ready" and self._healthy(now) and self._valid_lease(now),
                "requiresRecovery": self.state in ("restoring", "recoveryPending") or (self._recovery_required and self.state != "finished"),
                "esStatus": "notApplicable", "droppedStateEvents": self._dropped_events,
                "restoreDetails": self._restore_details,
                "clockSource": getattr(self.clock, "source", "injectedTestClock")}

    def snapshot(self):
        with self._lock:
            now = self._now()
            self._tick_locked(now)
            return self._snapshot_locked(now)

    def drain_events(self):
        with self._lock:
            result = list(self._events)
            self._events.clear()
            return result
