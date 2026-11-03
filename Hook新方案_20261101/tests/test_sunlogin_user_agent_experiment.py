"""Mock-only controller tests. No launchctl, vmmap, or third-party process calls."""
import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/sunlogin-user-agent-experiment.py'
SPEC = importlib.util.spec_from_file_location('sunlogin_experiment', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeOperations:
    domain = 'gui/501'

    def __init__(self, modified):
        self.modified = modified
        self.current = self.registered(MODULE.SOURCE)
        self.elapsed = 0
        self.mutations = []
        self.source_changed = False
        self.signature_failed = False
        self.library_changed = False
        self.verification_calls = 0
        self.verification_action = None
        self.fail_bootstrap = False
        self.timeout_bootstrap = False
        self.sleep_action = None

    @staticmethod
    def registered(path):
        return {'loaded': True, 'printReturnCode': 0, 'definitionPath': str(path),
                'program': MODULE.PROGRAM, 'state': 'running', 'pid': 123}

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        self.elapsed += seconds
        if self.sleep_action:
            action, self.sleep_action = self.sleep_action, None
            action()

    def job(self):
        return dict(self.current)

    def verify_original_files(self, _state):
        if self.source_changed:
            raise MODULE.ExperimentError('Original source changed')
        if self.signature_failed:
            raise MODULE.ExperimentError('Original signature failed')

    def verify_files(self, state):
        self.verify_original_files(state)
        self.verification_calls += 1
        if self.verification_action:
            self.verification_action(self.verification_calls)
        if self.library_changed:
            raise MODULE.ExperimentError('Library unavailable or changed')

    def snapshot(self):
        return {'processes': [], 'unresolved': [], 'enumerationComplete': True}

    def mapping_check(self):
        return {'checks': [], 'status': 'unknown', 'knownHookAbsentInObservedDesktopProcesses': False}

    def launchctl(self, args):
        self.mutations.append(args)
        if args[0] == 'bootout':
            self.current = {'loaded': False, 'printReturnCode': 113}
        elif args[0] == 'bootstrap':
            if args[2] == str(self.modified) and self.fail_bootstrap:
                return 5, ''
            self.current = self.registered(args[2])
            if args[2] == str(self.modified) and self.timeout_bootstrap:
                raise subprocess.TimeoutExpired('launchctl', 15)
        else:
            raise AssertionError('Unexpected operation')
        return 0, ''


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.modified = self.directory / 'instrumented-job.plist'
        self.modified.write_bytes(b'mock definition')
        self.state = {'runDirectory': str(self.directory), 'modifiedPlist': str(self.modified),
                      'modifiedSHA256': MODULE.sha(self.modified), 'events': [],
                      'sourceSHA256': 'mock', 'programSHA256': 'mock',
                      'sessionID': 'test-session', 'logPattern': str(self.directory / 'hook-%p.jsonl')}
        self.ops = FakeOperations(self.modified)
        self.experiment = MODULE.Experiment(self.state, self.ops, 1)

    def assert_restored(self):
        self.assertEqual(self.state['status'], 'original_job_restored')
        self.assertTrue(self.state['originalJobRunning'])
        self.assertTrue(MODULE.expected_job(self.ops.job(), MODULE.SOURCE))
        self.assertFalse(self.state['rootJobsChanged'])
        self.assertFalse(self.state['childProcessesTerminated'])
        self.assertFalse(self.state['remoteRecoveryVerified'])
        self.assertTrue((self.directory / 'result.json').exists())
        for args in self.ops.mutations:
            self.assertTrue(args[1].startswith('gui/501'))

    def test_deadline_restores_with_one_serial_controller(self):
        self.assertEqual(self.experiment.run(), 0)
        self.assert_restored()
        self.assertEqual([args[0] for args in self.ops.mutations], ['bootout', 'bootstrap', 'bootout', 'bootstrap'])
        self.assertEqual(self.experiment.request_reason, 'deadline_reached')
        ready = json.loads((self.directory / 'ready.json').read_text())
        self.assertLessEqual(ready['remainingSeconds'], 1)
        self.assertEqual(ready['libraryLoaded'], 'unverified')
        self.assertEqual(sum(e['event'] == 'restore_started' for e in self.state['events']), 1)

    def test_request_file_restores_early(self):
        self.ops.sleep_action = lambda: (self.directory / 'restore.request').touch()
        self.assertEqual(self.experiment.run(), 0)
        self.assert_restored()
        self.assertLess(self.ops.elapsed, 1)
        self.assertEqual(self.experiment.request_reason, 'restore_request_file')

    def test_signal_only_sets_flag_then_restores_serially(self):
        def signal_action():
            before = list(self.ops.mutations)
            self.experiment.signal_handler(signal.SIGTERM, None)
            self.assertEqual(self.ops.mutations, before)
        self.ops.sleep_action = signal_action
        self.assertEqual(self.experiment.run(), 0)
        self.assert_restored()
        self.assertEqual(self.experiment.request_reason, f'signal_{signal.SIGTERM}')

    def test_bootstrap_failure_restores_original(self):
        self.ops.fail_bootstrap = True
        self.assertEqual(self.experiment.run(), 1)
        self.assert_restored()
        self.assertIn('experimentError', self.state)
        self.assertEqual(len(self.ops.mutations), 3)
        self.assertFalse((self.directory / 'ready.json').exists())

    def test_timeout_with_possible_side_effect_rechecks_and_restores(self):
        self.ops.timeout_bootstrap = True
        self.assertEqual(self.experiment.run(), 1)
        self.assert_restored()
        self.assertEqual(len(self.ops.mutations), 4)

    def test_changed_source_before_start_never_mutates(self):
        self.ops.source_changed = True
        self.assertEqual(self.experiment.run(), 1)
        self.assertEqual(self.ops.mutations, [])
        self.assertEqual(self.state['status'], 'not_started')

    def test_changed_source_during_audit_does_not_use_changed_definition(self):
        self.ops.sleep_action = lambda: setattr(self.ops, 'source_changed', True)
        self.assertEqual(self.experiment.run(), 1)
        self.assertEqual(len(self.ops.mutations), 2)
        self.assertEqual(self.state['status'], 'restore_incomplete')
        self.assertTrue(MODULE.expected_job(self.ops.job(), self.modified))

    def test_unknown_job_is_not_removed_during_restore(self):
        self.ops.sleep_action = lambda: setattr(self.ops, 'current', self.ops.registered('/unknown/job.plist'))
        self.assertEqual(self.experiment.run(), 1)
        self.assertEqual(len(self.ops.mutations), 2)
        self.assertEqual(self.state['status'], 'restore_incomplete')
        self.assertEqual(self.ops.job()['definitionPath'], '/unknown/job.plist')

    def test_signature_failure_before_start_never_mutates(self):
        self.ops.signature_failed = True
        self.assertEqual(self.experiment.run(), 1)
        self.assertEqual(self.ops.mutations, [])

    def test_preexisting_restore_request_never_mutates(self):
        (self.directory / 'restore.request').touch()
        self.assertEqual(self.experiment.run(), 1)
        self.assertEqual(self.ops.mutations, [])
        self.assertEqual(self.state['status'], 'not_started')

    def test_deleted_or_changed_library_does_not_block_restoration(self):
        self.ops.sleep_action = lambda: setattr(self.ops, 'library_changed', True)
        self.assertEqual(self.experiment.run(), 0)
        self.assert_restored()
        self.assertEqual(len(self.ops.mutations), 4)

    def test_deadline_during_slow_guard_never_bootstraps_experiment(self):
        def slow_verification(count):
            if count == 2:
                self.ops.elapsed += 30
        self.ops.verification_action = slow_verification
        self.assertEqual(self.experiment.run(), 1)
        self.assert_restored()
        self.assertEqual(self.ops.mutations,
                         [['bootout', f'{self.ops.domain}/{MODULE.LABEL}'],
                          ['bootstrap', self.ops.domain, str(MODULE.SOURCE)]])
        self.assertEqual(self.experiment.request_reason, 'deadline_reached')
        self.assertFalse((self.directory / 'ready.json').exists())

    def test_signal_during_slow_guard_never_bootstraps_experiment(self):
        def interrupted_verification(count):
            if count == 2:
                self.experiment.signal_handler(signal.SIGTERM, None)
        self.ops.verification_action = interrupted_verification
        self.assertEqual(self.experiment.run(), 1)
        self.assert_restored()
        self.assertEqual(len(self.ops.mutations), 2)
        self.assertEqual(self.ops.mutations[-1], ['bootstrap', self.ops.domain, str(MODULE.SOURCE)])
        self.assertFalse((self.directory / 'ready.json').exists())


if __name__ == '__main__':
    unittest.main()
