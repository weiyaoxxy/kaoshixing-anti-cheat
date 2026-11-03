"""Non-root native acceptance of the exact service source and command() function.

Never starts/stops remote applications, installs services, or enters root mode.
Fixtures and binaries live in a temporary directory. Every command harness owns
a private process group and stays alive until the test cleans up that group.
"""
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'Sources/ExamGuardService/main.swift'

FIXTURE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
int main(int argc, char **argv) {
    if (argc < 2) return 64;
    if (!strcmp(argv[1], "group")) {
        printf("{\"pid\":%d,\"pgid\":%d,\"ppid\":%d}\n",getpid(),getpgrp(),getppid());
    } else if (!strcmp(argv[1], "exit")) {
        return argc > 2 ? atoi(argv[2]) : 42;
    } else if (!strcmp(argv[1], "signal")) {
        raise(SIGTERM);
    } else if (!strcmp(argv[1], "sleep")) {
        printf("{\"pid\":%d,\"pgid\":%d}\n", getpid(), getpgrp());
        fflush(stdout); sleep(8);
    } else if (!strcmp(argv[1], "descendant") || !strcmp(argv[1], "timeout-descendant")) {
        pid_t child = fork();
        if (child == 0) { sleep(8); _exit(0); }
        if (child < 0) return 71;
        printf("{\"descendant\":%d,\"pgid\":%d}\n", child, getpgrp());
        fflush(stdout);
        if (!strcmp(argv[1], "timeout-descendant")) sleep(8);
    } else if (!strcmp(argv[1], "large")) {
        char bytes[16384]; memset(bytes, 'X', sizeof(bytes));
        for (int i = 0; i < 384; i++) if (write(1, bytes, sizeof(bytes)) < 0) return 73;
    } else if (!strcmp(argv[1], "literal")) {
        if (argc != 3) return 64;
        printf("%s", argv[2]);
    } else if (!strcmp(argv[1], "environment")) {
        printf("{\"sentinelPresent\":%s}", getenv("EXAM_GUARD_TEST_SENTINEL") ? "true" : "false");
    } else return 64;
    return 0;
}
'''


class ExamGuardNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.geteuid() == 0:
            raise unittest.SkipTest('These tests must never execute as root')
        cls.temporary = tempfile.TemporaryDirectory(prefix='exam-guard-native-tests-')
        cls.folder = Path(cls.temporary.name)
        source = SOURCE.read_text()
        cls.source_sha256 = hashlib.sha256(source.encode()).hexdigest()
        cls.supports_owner_birth = '"--owner-birth"' in source
        cls.service = cls.folder / 'GuardService'
        (cls.folder / 'main.swift').write_text(source)
        (cls.folder / 'EmbeddedInventory.swift').write_text(
            'enum EmbeddedInventory { static let source = "/not-used-by-nonroot-tests"; '
            'static let sha256 = "not-used"; static let policyBase64 = "e30=" }\n')
        compiled = subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-O',
            '-framework', 'Foundation', '-framework', 'Security', '-framework', 'CryptoKit',
            str(cls.folder / 'main.swift'), str(cls.folder / 'EmbeddedInventory.swift'),
            '-o', str(cls.service)], capture_output=True, text=True, timeout=45)
        if compiled.returncode != 0:
            raise AssertionError(compiled.stderr)
        # Extract the current function verbatim; tests exercise real implementation,
        # not a Python imitation or a rewritten approximation.
        clock = source[source.index('func continuous()'):source.index('func birth(')]
        command = source[source.index('struct CommandResult'):source.index('func atomicJSON')]
        supervisor_start = source.index('func supervise(')
        supervisor = source[supervisor_start:source.index('\ndo {', supervisor_start)]
        # The root recovery object is deliberately unavailable. A random session
        # has no journal; this stub can only signal a test failure if reached.
        stubs = '''
enum HarnessError: Error { case unexpected(String) }
func fail(_ message: String) throws -> Never { throw HarnessError.unexpected(message) }
final class Worker {
    init(recover: String) throws { throw HarnessError.unexpected("recoveryMustNotRunInNonrootHarness") }
    func restore() {}
}
'''
        harness = 'import Foundation\nimport Darwin\n' + clock + command + stubs + supervisor + r'''
guard geteuid() != 0 else { exit(64) }
if CommandLine.arguments.count == 3 && CommandLine.arguments[1] == "--worker" {
    let result = command(CommandLine.arguments[2], ["descendant"], timeout: 2)
    let data = try! JSONSerialization.data(withJSONObject: ["kind": "worker", "output": result.output,
        "pid": getpid(), "pgid": getpgrp()])
    FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10]))
    exit(0)
}
if CommandLine.arguments.count == 4 && CommandLine.arguments[1] == "--supervise-probe" {
    try! supervise([CommandLine.arguments[2]], session: CommandLine.arguments[3], lease: 0.1)
    let data = try! JSONSerialization.data(withJSONObject: ["kind": "supervisor", "pid": getpid()])
    FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10]))
    _ = readLine(); exit(0)
}
guard geteuid() != 0, CommandLine.arguments.count >= 4,
      let timeout = Double(CommandLine.arguments[1]), timeout.isFinite else { exit(64) }
let began = continuous()
let result = command(CommandLine.arguments[2], Array(CommandLine.arguments.dropFirst(3)), timeout: timeout)
let data = try! JSONSerialization.data(withJSONObject: ["code": result.code, "output": result.output,
    "timedOut": result.timedOut, "elapsed": continuous() - began, "pid": getpid(), "pgid": getpgrp()])
FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10]))
// Keep the process-group leader alive/unreaped until its owning Python test
// kills this private group. This reserves the identity during descendant cleanup.
_ = readLine()
'''
        (cls.folder / 'command-harness.swift').write_text(harness)
        cls.harness = cls.folder / 'CommandHarness'
        compiled = subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-O',
            str(cls.folder / 'command-harness.swift'), '-o', str(cls.harness)],
            capture_output=True, text=True, timeout=30)
        if compiled.returncode != 0:
            raise AssertionError(compiled.stderr)
        (cls.folder / 'fixture.c').write_text(FIXTURE)
        cls.fixture = cls.folder / 'Fixture'
        compiled = subprocess.run(['xcrun', 'clang', str(cls.folder / 'fixture.c'),
            '-o', str(cls.fixture)], capture_output=True, text=True, timeout=20)
        if compiled.returncode != 0:
            raise AssertionError(compiled.stderr)
        print(f'ExamGuardService tested source SHA256={cls.source_sha256}', flush=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_command(self, mode, *args, timeout=2, executable=None, observe=None):
        environment = dict(os.environ, EXAM_GUARD_TEST_SENTINEL='owned-test-value')
        process = subprocess.Popen([str(self.harness), str(timeout), str(executable or self.fixture),
                                    mode, *map(str, args)], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=environment, start_new_session=True)
        try:
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            self.assertTrue(selector.select(timeout + 5), 'native command did not return within bound')
            selector.close()
            line = process.stdout.readline()
            self.assertTrue(line, 'command harness returned no JSON')
            result = json.loads(line)
            self.assertEqual(result['pid'], process.pid)
            self.assertEqual(result['pgid'], process.pid)
            if observe:
                observe(result)
            return result
        finally:
            # This is our still-unreaped, intentionally held group leader. All
            # members are test descendants; no searched application PID is killed.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
            process.stdin.close(); process.stdout.close(); process.stderr.close()

    def cli(self, *args):
        return subprocess.run([str(self.service), *map(str, args)], capture_output=True,
                              text=True, timeout=15)

    def session_args(self, session=None, lease=10):
        args = ['--session', session or str(uuid.uuid4()), '--uid', os.getuid(), '--owner', os.getpid()]
        if self.supports_owner_birth:
            result = self.cli('--owner-identity', os.getpid())
            self.assertEqual(result.returncode, 0, result.stderr)
            life = json.loads(result.stdout)['birth']
            args += ['--owner-birth', f'{life[1]}:{life[2]}']
        return args + ['--vendors', 'uu', '--lease', lease]

    def test_cli_rejects_missing_extra_and_malformed_arguments(self):
        for args in [[], ['--unknown'], ['--inspect', 'extra'], ['--session', '../bad'],
                     ['--recover'], ['--uid', '-1']]:
            with self.subTest(args=args):
                self.assertNotEqual(self.cli(*args).returncode, 0)

    def test_nonroot_cannot_start_mutating_or_root_inspect_session(self):
        session = str(uuid.uuid4()).upper()
        path = Path('/private/var/tmp') / ('exam-remote-guard-' + session)
        args = self.session_args(session=session)
        for prefix in ([], ['--worker'], ['--root-inspect']):
            with self.subTest(prefix=prefix):
                result = self.cli(*prefix, *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('rootAndFiniteLeaseRequired', result.stderr)
                self.assertFalse(path.exists())

    def test_nonroot_recovery_rejected(self):
        result = self.cli('--recover', str(uuid.uuid4()))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('invalidRecovery', result.stderr)

    def test_cli_rejects_nonfinite_and_out_of_range_leases(self):
        for lease in ('nan', 'inf', '-1', '0', '9', '601'):
            with self.subTest(lease=lease):
                result = self.cli(*self.session_args(lease=lease))
                self.assertNotEqual(result.returncode, 0)

    def test_owner_birth_binding_rejects_mismatched_instance(self):
        if not self.supports_owner_birth:
            self.skipTest('source snapshot does not yet expose owner-birth binding')
        args = self.session_args()
        args[args.index('--owner-birth') + 1] = '1:1'
        result = self.cli(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('usage:', result.stderr)

    def test_readonly_owner_identity_reports_current_uid(self):
        if not self.supports_owner_birth:
            self.skipTest('source snapshot does not yet expose owner identity')
        result = self.cli('--owner-identity', os.getpid())
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['pid'], os.getpid())
        self.assertEqual(report['birth'][0], os.getuid())
        self.assertGreater(report['birth'][1], 0)

    def test_inspect_is_readonly_and_does_not_claim_production(self):
        result = self.cli('--inspect')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['mode'], 'inspectOnly')
        self.assertIs(report['productionReady'], False)
        self.assertIsInstance(report['targets'], list)
        for target in report['targets']:
            self.assertIn(target['vendor'], ('uu', 'todesk', 'sunlogin'))
            self.assertEqual(len(target['life'] if 'life' in target else target['birth']), 3)
            self.assertTrue(target['cdhash'])

    def test_command_child_stays_in_supervised_group(self):
        result = self.run_command('group')
        child = json.loads(result['output'])
        self.assertEqual(result['code'], 0)
        self.assertFalse(result['timedOut'])
        self.assertEqual(child['pgid'], result['pgid'])
        self.assertEqual(child['ppid'], result['pid'])

    def test_command_exit_code_is_preserved(self):
        result = self.run_command('exit', 42)
        self.assertEqual(result['code'], 42)
        self.assertFalse(result['timedOut'])

    def test_command_signal_exit_is_reported(self):
        result = self.run_command('signal')
        self.assertEqual(result['code'], 128 + signal.SIGTERM)
        self.assertFalse(result['timedOut'])

    def test_command_timeout_kills_and_reaps_direct_child(self):
        def observe(result):
            child = json.loads(result['output'])
            state = subprocess.run(['/bin/ps', '-p', str(child['pid']), '-o', 'stat='],
                                   capture_output=True, text=True, timeout=3)
            self.assertEqual(state.stdout.strip(), '')
        result = self.run_command('sleep', timeout=0.15, observe=observe)
        self.assertTrue(result['timedOut'])
        self.assertEqual(result['code'], 128 + signal.SIGKILL)
        self.assertLess(result['elapsed'], 1.5)

    def test_command_output_limit_is_exposed(self):
        result = self.run_command('large')
        self.assertTrue(result['timedOut'])
        self.assertLessEqual(len(result['output'].encode()), 4 * 1024 * 1024)
        self.assertGreater(len(result['output']), 0)

    def test_command_does_not_wait_for_descendant_pipe_eof(self):
        def observe(result):
            child = json.loads(result['output'])
            state = subprocess.run(['/bin/ps', '-p', str(child['descendant']), '-o', 'pgid=,stat='],
                                   capture_output=True, text=True, timeout=3).stdout.strip()
            if state:
                self.assertEqual(int(state.split()[0]), result['pgid'])
        result = self.run_command('descendant', timeout=2, observe=observe)
        self.assertEqual(result['code'], 0)
        self.assertFalse(result['timedOut'])
        self.assertLess(result['elapsed'], 1.5)

    def test_timedout_descendant_is_in_supervised_group_until_group_cleanup(self):
        def observe(result):
            child = json.loads(result['output'])
            state = subprocess.run(['/bin/ps', '-p', str(child['descendant']), '-o', 'pgid=,stat='],
                                   capture_output=True, text=True, timeout=3).stdout.strip()
            if state and not state.split()[-1].startswith('Z'):
                self.assertEqual(int(state.split()[0]), result['pgid'])
                print('Observed: command timeout leaves live descendant for supervisor group cleanup', flush=True)
        result = self.run_command('timeout-descendant', timeout=0.15, observe=observe)
        self.assertTrue(result['timedOut'])
        self.assertLess(result['elapsed'], 1.5)

    def test_command_arguments_are_literal_and_environment_is_restricted(self):
        sentinel = self.folder / 'must-not-be-created'
        literal = '$(touch ' + str(sentinel) + '); `id`'
        result = self.run_command('literal', literal)
        self.assertEqual(result['output'], literal)
        self.assertFalse(sentinel.exists())
        result = self.run_command('environment')
        self.assertIs(json.loads(result['output'])['sentinelPresent'], False)

    def test_command_spawn_failure_is_visible(self):
        result = self.run_command('unused', executable=self.folder / 'does-not-exist')
        self.assertEqual(result['code'], -1)
        self.assertIn('spawnFailed', result['output'])
        self.assertFalse(result['timedOut'])

    def test_supervisor_cleans_worker_group_after_worker_exit(self):
        session = str(uuid.uuid4())
        process = subprocess.Popen([str(self.harness), '--supervise-probe', str(self.fixture), session],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        descendant = None
        try:
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            received = b''
            while received.count(b'\n') < 2:
                self.assertTrue(selector.select(5), 'supervisor probe did not return')
                chunk = os.read(process.stdout.fileno(), 65536)
                self.assertTrue(chunk, 'supervisor probe returned no JSON')
                received += chunk
            reports = [json.loads(line) for line in received.splitlines()[:2]]
            selector.close()
            self.assertEqual([row['kind'] for row in reports], ['worker', 'supervisor'])
            worker = reports[0]
            self.assertEqual(worker['pid'], worker['pgid'])
            descendant = json.loads(worker['output'])['descendant']
            inactive = False
            for _ in range(30):
                state = subprocess.run(['/bin/ps', '-p', str(descendant), '-o', 'stat='],
                                       capture_output=True, text=True, timeout=3).stdout.strip()
                if not state or state.startswith('Z'):
                    inactive = True; break
                time.sleep(0.02)
            self.assertTrue(inactive, 'worker exited but supervisor left its descendant executing')
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
            process.stdin.close(); process.stdout.close(); process.stderr.close()
            if descendant:
                # In a failing implementation the harmless child naturally exits
                # after eight seconds; never signal an unowned/reused process ID.
                for _ in range(90):
                    state = subprocess.run(['/bin/ps', '-p', str(descendant), '-o', 'stat='],
                                           capture_output=True, text=True, timeout=3).stdout.strip()
                    if not state or state.startswith('Z'):
                        break
                    time.sleep(0.1)


if __name__ == '__main__':
    unittest.main()
