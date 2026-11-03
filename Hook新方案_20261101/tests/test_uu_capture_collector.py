"""Collector failure regressions with synthetic sample output; never touches UU."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('collector_under_test', ROOT/'scripts/observe-uu-capture-path.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
fixture_spec = importlib.util.spec_from_file_location('sample_fixtures', ROOT/'tests/test_uu_capture_sample.py')
fixtures = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(fixtures)
ROW = {'pid': 123, 'uid': os.getuid(), 'role': 'server',
       'executable': str(collector.PATHS['server']), 'startTimeSeconds': 1234,
       'startTimeMicroseconds': 5678}
INVENTORY = {'schemaVersion': 1, 'processes': [ROW], 'enumerationComplete': True, 'unresolved': []}
SIGNING = {'originalVendorSignatureVerified': True}


def synthetic_sample(arguments, duration):
    text = fixtures.sample().replace('/test/UURemoteServer', ROW['executable'])
    Path(arguments[-1]).write_text(text)
    return {'exitCode': 0, 'timedOut': False, 'cleanupConfirmed': True}


class CollectorTests(unittest.TestCase):
    def setUp(self):
        collector.STOP_REQUESTED = False

    def execute(self, *, inventories=None, signature=None, hashes=None, sampler=synthetic_sample):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with patch.object(collector, 'inventory', side_effect=inventories or [INVENTORY]*3), \
                 patch.object(collector, 'signing', return_value=signature or SIGNING), \
                 patch.object(collector, 'digest', side_effect=hashes or ['a'*64]*2), \
                 patch.object(collector.Path, 'is_file', return_value=True), \
                 patch.object(collector, 'run_sample', side_effect=sampler) as run:
                result = collector.sample_one(ROW, Path('/fixture/inventory'), 1, 5,
                                              fixtures.module.analyze, output, 1)
            saved = json.loads(next(output.glob('*-result.json')).read_text())
            analyses = [json.loads(p.read_text()) for p in output.glob('*-analysis.json')]
            self.assertEqual(saved, result)
            self.assertIs(result['rawSampleRetained'], False)
            return result, analyses, run.call_count

    def test_success_requires_identity_and_reports_external_only(self):
        result, analyses, count = self.execute()
        self.assertEqual(count, 1)
        self.assertEqual(result['status'], 'path_observed')
        self.assertTrue(analyses[0]['identityContinuityVerified'])
        self.assertTrue(analyses[0]['outputCompletenessVerified'])
        for key in ['captureHookHitVerified', 'validFrameVerified', 'remoteSessionVerified']:
            self.assertIs(result[key], False)

    def test_reused_pid_is_not_sampled(self):
        changed = {**INVENTORY, 'processes': [{**ROW, 'startTimeMicroseconds': 9999}]}
        result, analyses, count = self.execute(inventories=[changed])
        self.assertEqual(count, 0)
        self.assertEqual(result['status'], 'processChangedBeforeSampling')
        self.assertFalse(analyses)

    def test_unverified_signature_is_not_sampled(self):
        result, _, count = self.execute(signature={'originalVendorSignatureVerified': False})
        self.assertEqual(count, 0)
        self.assertEqual(result['status'], 'originalSignatureUnverified')

    def test_post_sample_identity_failure_is_persisted_and_invalid(self):
        result, analyses, count = self.execute(inventories=[INVENTORY, INVENTORY, RuntimeError('unavailable')])
        self.assertEqual(count, 1)
        self.assertEqual(result['postIdentityError'], 'RuntimeError')
        self.assertFalse(analyses[0]['pathObserved'])
        self.assertEqual(result['status'], 'invalid_or_incomplete')

    def test_changed_executable_does_not_preserve_positive(self):
        result, analyses, _ = self.execute(hashes=['a'*64, 'b'*64])
        self.assertFalse(result['executableUnchanged'])
        self.assertFalse(analyses[0]['pathObserved'])

    def test_tool_timeout_never_analyzed_as_success(self):
        def interrupted(args, duration):
            synthetic_sample(args, duration)
            return {'exitCode': 0, 'timedOut': True, 'cleanupConfirmed': True}
        result, analyses, _ = self.execute(sampler=interrupted)
        self.assertEqual(result['status'], 'sampleToolTimeout')
        self.assertFalse(analyses)

    def test_different_owner_or_copy_excluded(self):
        rows = [ROW, {**ROW, 'uid': 0}, {**ROW, 'executable': '/tmp/UURemoteServer'}]
        self.assertEqual(collector.original_targets({'processes': rows}, ['server']), [ROW])

    def test_final_check_failure_still_writes_unknown_summary(self):
        job = {'exitCode': 0, 'path': str(collector.PLISTS[0]),
               'program': str(collector.PATHS['service']), 'experimentalEnvironmentKeys': []}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'run'
            with patch.object(sys, 'argv', ['observe', '--phase', 'preflight', '--output', str(output)]), \
                 patch.object(collector, 'baseline', side_effect=[{'atUTC':'test', 'files': []}, OSError('unavailable')]), \
                 patch.object(collector, 'inventory', return_value=INVENTORY), \
                 patch.object(collector, 'launch_job', return_value=job), \
                 patch.object(collector.signal, 'signal'), \
                 patch.object(collector.os, 'umask'), \
                 patch.object(collector.Path, 'is_file', return_value=True):
                with self.assertRaises(SystemExit):
                    collector.main()
            report = json.loads((output/'summary.json').read_text())
            self.assertIsNone(report['originalFilesUnchanged'])
            self.assertFalse(report['collectionComplete'])
            self.assertEqual(report['finalCheckErrors']['baseline-after'], 'OSError')


if __name__ == '__main__':
    unittest.main()
