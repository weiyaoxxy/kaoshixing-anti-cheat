"""Bounded root worker bridge. Only start a compiled policy or request END.

There is deliberately no API for an arbitrary PID/path/job/shell command.
System authorization is interactive; credentials are never collected here.
"""
import json
import hashlib
import os
from pathlib import Path
import shlex
import stat
import subprocess
import tempfile
import uuid


class WorkerError(RuntimeError):
    pass


class DevelopmentWorker:
    def __init__(self, executable, vendors, owner_pid=None, lease=180):
        if not set(vendors) or not set(vendors) <= {"uu", "todesk", "sunlogin"}:
            raise WorkerError("unsupportedVendor")
        if type(lease) is not int or not 10 <= lease <= 600:
            raise WorkerError("invalidLease")
        self.executable = Path(executable).resolve(strict=True)
        if not self.executable.is_file() or not os.access(self.executable, os.X_OK):
            raise WorkerError("workerExecutableUnavailable")
        self.session = str(uuid.uuid4()).upper()
        self.directory = Path("/private/var/tmp/exam-remote-guard-" + self.session)
        self.vendors = sorted(set(vendors))
        self.owner = owner_pid or os.getpid()
        self.uid = os.getuid()
        self.lease = lease
        self.started = False
        self.authorization_outcome = "notRequested"
        self.end_requested = False
        self.last_sequence = 0

    def start(self, read_only=False):
        if self.started:
            raise WorkerError("workerAlreadyRequested")
        self.started = True  # An ambiguous authorization result is not retried.
        identity = subprocess.run([str(self.executable), "--owner-identity", str(self.owner)], capture_output=True, text=True, timeout=5)
        if identity.returncode:
            raise WorkerError("ownerIdentityUnavailable")
        life = json.loads(identity.stdout)["birth"]
        if len(life) != 3 or life[0] != self.uid:
            raise WorkerError("ownerIdentityMismatch")
        deployment = Path("/private/var/tmp/exam-remote-helper-" + self.session)
        protected = deployment / "Worker"
        contents = self.executable.read_bytes()
        expected = hashlib.sha256(contents).hexdigest()
        # Read Desktop/project files as the consenting user; elevated AppleScript
        # may correctly lack TCC access to Desktop. Only these pinned build bytes
        # are staged in an owner-only temporary directory for installation.
        stage = Path(tempfile.mkdtemp(prefix="exam-remote-stage-", dir="/private/var/tmp"))
        staged_worker = stage / "Worker"
        fd = os.open(staged_worker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700)
        with os.fdopen(fd, "wb") as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        arguments = [str(protected), "--session", self.session, "--uid", str(self.uid),
                     "--owner", str(self.owner), "--owner-birth", str(life[1]) + ":" + str(life[2]), "--vendors", ",".join(self.vendors),
                     "--lease", str(self.lease)]
        if read_only:
            arguments.insert(1, "--root-inspect")
        # The executable has compiled vendor/job identities and a hard maximum TTL.
        # Copy and verify inside a fresh root-owned directory before any elevated
        # code is executed. The pinned bytes cannot be replaced by the GUI UID.
        checksum = 'test "$(/usr/bin/shasum -a 256 ' + shlex.quote(str(protected)) + ')" = ' + shlex.quote(expected + "  " + str(protected))
        shell_command = " && ".join([
            shlex.join(["/bin/mkdir", "-m", "700", str(deployment)]),
            shlex.join(["/usr/bin/install", "-m", "755", "-o", "root", "-g", "wheel", str(staged_worker), str(protected)]),
            checksum, "(" + shlex.join(arguments) + " > /dev/null 2>&1 &)"])
        self.authorization_outcome = "pending"
        try:
            result = subprocess.run(["/usr/bin/osascript", "-e", "on run argv", "-e",
                                 "do shell script (item 1 of argv) with administrator privileges",
                                 "-e", "end run", shell_command],
                                capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            self.authorization_outcome = "unknown"
            raise WorkerError("administratorAuthorizationTimedOut")
        if result.returncode:
            self.authorization_outcome = ("cancelledBeforeLaunch" if "(-128)" in result.stderr and not deployment.exists()
                                          and not self.directory.exists() else "unknown")
            raise WorkerError("administratorAuthorizationFailed:" + result.stderr.strip()[:400])
        self.authorization_outcome = "launchRequested"

    def read_status(self):
        path = self.directory / "status.json"
        try:
            directory = self.directory.lstat()
            if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != 0
                    or directory.st_mode & 0o022):
                raise WorkerError("untrustedWorkerDirectory")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
                    or info.st_size > 8 * 1024 * 1024):
                raise WorkerError("untrustedWorkerStatus")
            with os.fdopen(fd, "rb", closefd=False) as handle:
                state = json.load(handle)
        finally:
            os.close(fd)
        if (state.get("sessionID") != self.session or state.get("ownerPID") != self.owner
                or state.get("uid") != self.uid or state.get("vendors") != self.vendors
                or type(state.get("sequence")) is not int
                or state["sequence"] < self.last_sequence
                or state.get("backend") != "development-root-worker"):
            raise WorkerError("workerStatusIdentityMismatch")
        self.last_sequence = state["sequence"]
        return state

    def request_end(self):
        self.end_requested = True
        if not self.directory.exists():
            return False  # Retry after a slow authorization/start; the hard TTL also applies.
        self.read_status()  # Validate the root-owned parent before accessing IPC.
        fd = os.open(self.directory / "end.request", os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != self.uid or info.st_mode & 0o077:
                raise WorkerError("invalidEndRequestFile")
            os.ftruncate(fd, 0)
            os.write(fd, b"end\n")
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
