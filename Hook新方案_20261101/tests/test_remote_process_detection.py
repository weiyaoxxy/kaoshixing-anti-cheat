"""Synthetic policy/identity tests. No real process or signing commands run."""
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('remote_detection', ROOT / 'scripts/detect-remote-processes.py')
detector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(detector)
POLICY = json.loads(detector.DEFAULT_POLICY.read_text())


def candidate():
    return {'pid': 123, 'uid': 501, 'parentPID': 1,
            'executable': '/synthetic/UURemote', 'startTimeSeconds': 100,
            'startTimeMicroseconds': 20, 'candidateVendors': ['uu'], 'role': 'gui'}


def signed():
    return {'status': 'validForConfiguredRequirement', 'matchedVendors': ['uu'],
            'metadata': {'Identifier': 'com.netease.uuremote', 'TeamIdentifier': 'PU9BNSBJW7'},
            'fileStableAcrossVerification': True}


class DetectionTests(unittest.TestCase):
    def test_vendor_match_requires_team_and_component(self):
        m = signed()['metadata']
        self.assertEqual(detector.match_policy(m, ['uu'], POLICY), ['uu'])
        m['TeamIdentifier'] = 'OTHERTEAM1'
        self.assertEqual(detector.match_policy(m, ['uu'], POLICY), [])

    def test_same_team_other_product_is_not_remote(self):
        m = {'Identifier': 'com.netease.anotherproduct', 'TeamIdentifier': 'PU9BNSBJW7'}
        self.assertEqual(detector.match_policy(m, ['uu'], POLICY), [])

    def test_name_candidate_without_signing_identity_is_not_verified(self):
        s = signed(); s['status'] = 'identityNotMatched'; s['matchedVendors'] = []
        self.assertEqual(detector.classify(candidate(), s, candidate(), POLICY)['status'], 'candidateUnconfirmed')

    def test_pid_reuse_uid_change_and_path_change(self):
        for field, replacement in [('startTimeMicroseconds', 21), ('startTimeSeconds', 101),
                                   ('uid', 0), ('executable', '/other'), ('pid', 124)]:
            with self.subTest(field=field):
                after = candidate(); after[field] = replacement
                self.assertFalse(detector.same_lifetime(candidate(), after))

    def test_reparenting_does_not_change_birth_identity(self):
        after = candidate(); after['parentPID'] = 99
        self.assertTrue(detector.same_lifetime(candidate(), after))

    def test_missing_identity_or_exited_process_not_verified(self):
        self.assertFalse(detector.same_lifetime({}, {}))
        self.assertEqual(detector.classify(candidate(), signed(), None, POLICY)['status'], 'candidateUnconfirmed')

    def test_file_changed_not_verified(self):
        s = signed(); s['fileStableAcrossVerification'] = False
        self.assertEqual(detector.classify(candidate(), s, candidate(), POLICY)['status'], 'candidateUnconfirmed')

    def test_permission_unknown_and_signature_invalid_not_verified(self):
        for status in ['unknown', 'verificationFailed', 'identityNotMatched']:
            with self.subTest(status=status):
                s = signed(); s['status'] = status
                self.assertEqual(detector.classify(candidate(), s, candidate(), POLICY)['status'], 'candidateUnconfirmed')

    def test_running_result_does_not_assert_session_or_enforcement(self):
        row = detector.classify(candidate(), signed(), candidate(), POLICY)
        self.assertEqual(row['verifiedRole'], 'gui')
        self.assertFalse(row['remoteSessionVerified'])
        self.assertFalse(row['runningMemoryAttested'])
        summary = detector.summarize({'enumerationComplete': True}, [row], POLICY)
        self.assertEqual(summary['recommendedExamAction'], 'block_start_recommended')
        self.assertFalse(summary['examGateActuallyEnforced'])

    def test_positive_survives_other_unreadable_processes(self):
        row = detector.classify(candidate(), signed(), candidate(), POLICY)
        summary = detector.summarize({'enumerationComplete': False, 'unresolved': [{'pid': 999}]}, [row], POLICY)
        self.assertEqual(summary['vendors']['uu']['status'], 'runningVerifiedComponents')
        self.assertEqual(summary['vendors']['todesk']['status'], 'inspectionIncomplete')
        self.assertEqual(summary['recommendedExamAction'], 'block_start_recommended')

    def test_failed_enumeration_cannot_be_clean(self):
        s = detector.summarize({'enumerationComplete': False}, [], POLICY)
        self.assertEqual(s['recommendedExamAction'], 'review_required')
        self.assertTrue(all(v['status'] == 'inspectionIncomplete' for v in s['vendors'].values()))

    def test_complete_negative_only_claims_declared_scope(self):
        s = detector.summarize({'enumerationComplete': True, 'unresolved': []}, [], POLICY)
        self.assertEqual(s['recommendedExamAction'], 'no_supported_target_observed')
        self.assertTrue(all(v['status'] == 'notObservedWithinScope' for v in s['vendors'].values()))

    def test_unresolved_overrides_inconsistent_complete_flag(self):
        s = detector.summarize({'enumerationComplete': True, 'unresolved': [{'pid': 5}]}, [], POLICY)
        self.assertEqual(s['recommendedExamAction'], 'review_required')

    def test_updater_alone_requires_review_not_active_session_claim(self):
        s = signed(); s['metadata']['Identifier'] = 'com.netease.uuremote.updater'
        row = detector.classify(candidate(), s, candidate(), POLICY)
        result = detector.summarize({'enumerationComplete': True}, [row], POLICY)
        self.assertEqual(result['vendors']['uu']['verifiedRuntimeCount'], 0)
        self.assertEqual(result['recommendedExamAction'], 'review_required')

    def test_unknown_candidate_is_not_silently_dropped(self):
        s = signed(); s['status'] = 'unknown'
        row = detector.classify(candidate(), s, candidate(), POLICY)
        result = detector.summarize({'enumerationComplete': True}, [row], POLICY)
        self.assertEqual(result['vendors']['uu']['unconfirmedCount'], 1)
        self.assertEqual(result['recommendedExamAction'], 'review_required')

    def test_literal_dollar_identifier_uses_inline_requirement_argument(self):
        metadata = {'returnCode': 0, 'stderr': 'Identifier=$(PRODUCT_BUNDLE_IDENTIFIER)\nTeamIdentifier=ZBNMDRTU32\nCDHash=e3a12b43dfba8ef18382d5ae85d3e53a9b0937c2\n'}
        checked = {'returnCode': 0, 'stderr': '', 'timedOut': False}
        with patch.object(detector, 'file_identity', return_value={'inode': 2}), \
                patch.object(detector, 'run', side_effect=[metadata, checked]) as run:
            result = detector.signature('/synthetic/AweSun_Helper', ['sunlogin'], POLICY)
        self.assertEqual(result['status'], 'validForConfiguredRequirement')
        args = run.call_args_list[1].args[0]
        self.assertTrue(args[args.index('-R') + 1].startswith('=anchor apple generic'))
        self.assertIn('identifier "$(PRODUCT_BUNDLE_IDENTIFIER)"', args[args.index('-R') + 1])

    def test_verifier_tool_failure_is_unknown_not_invalid_app(self):
        metadata = {'returnCode': 0, 'stderr': 'Identifier=com.netease.uuremote\nTeamIdentifier=PU9BNSBJW7\n'}
        checked = {'returnCode': 1, 'stderr': 'invalid requirement specification', 'timedOut': False}
        with patch.object(detector, 'file_identity', return_value={'inode': 2}), \
                patch.object(detector, 'run', side_effect=[metadata, checked]):
            result = detector.signature('/synthetic/UURemote', ['uu'], POLICY)
        self.assertEqual(result['status'], 'unknown')

    def test_running_inputs_changed_does_not_relabel_initial_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            policy = folder / 'policy.json'
            policy.write_text(json.dumps(POLICY))
            initial_hash = hashlib.sha256(policy.read_bytes()).hexdigest()
            binary = folder / 'fake-inventory'
            binary.write_bytes(b'synthetic; never executed')
            output = folder / 'result'
            def synthetic_scan(*unused, **unused_keywords):
                policy.write_text(json.dumps(POLICY) + '\n')
                return {'startedAtUTC': 'synthetic', 'elapsedSeconds': 0,
                        'enumerationComplete': False, 'recommendedExamAction': 'review_required', 'vendors': {}}
            argv = ['detect-remote-processes.py', '--inventory', str(binary), '--policy', str(policy), '--output', str(output)]
            with patch('sys.argv', argv), patch.object(detector, 'scan', side_effect=synthetic_scan), \
                    patch('sys.stdout', new_callable=io.StringIO):
                detector.main()
            result = json.loads((output / 'summary.json').read_text())
            self.assertEqual(result['policySHA256'], initial_hash)
            self.assertTrue(result['provenanceChanged'])
            self.assertFalse(result['observationsUsableWithDeclaredLimitations'])

    def test_renamed_identity_matches_without_hints(self):
        self.assertEqual(detector.match_policy(signed()['metadata'], [], POLICY), ['uu'])

    def test_unhinted_verified_process_survives_summary(self):
        c = candidate(); c['candidateVendors'] = []; c['executable'] = '/random/moved'
        row = detector.classify(c, signed(), c, POLICY)
        result = detector.summarize({'enumerationComplete': True}, [row], POLICY)
        self.assertEqual(result['vendors']['uu']['verifiedCount'], 1)
        self.assertEqual(result['recommendedExamAction'], 'block_start_recommended')

    def test_unrelated_rows_do_not_mean_remote_running(self):
        c = candidate(); c['candidateVendors'] = []; c['category'] = 'unknownSignedCode'
        result = detector.summarize({'enumerationComplete': True}, [c], POLICY)
        self.assertEqual(result['recommendedExamAction'], 'no_supported_target_observed')
        self.assertFalse(result['unclassifiedCodeMeansAllowed'])

    def test_generic_helper_without_pin_is_not_confirmed(self):
        m = {'Identifier': '$(PRODUCT_BUNDLE_IDENTIFIER)', 'TeamIdentifier': 'ZBNMDRTU32'}
        self.assertEqual(detector.match_policy(m, ['sunlogin'], POLICY), [])
        m['CDHash'] = '0' * 40
        self.assertEqual(detector.match_policy(m, [], POLICY), [])
        m['CDHash'] = 'e3a12b43dfba8ef18382d5ae85d3e53a9b0937c2'
        self.assertEqual(detector.match_policy(m, [], POLICY), ['sunlogin'])

    def native_row(self):
        row = candidate()
        row.update(verifiedVendor='uu', verifiedRole='gui', category='knownRemoteIdentityVerified',
                   status='verifiedComponentRunning', identityStableAcrossReads=True)
        row['codeIdentity'] = {'metadata': signed()['metadata'],
                               'dynamicValidation': {'status': 'verified', 'OSStatus': 0},
                               'staticValidation': {'status': 'failed', 'OSStatus': -67054}}
        return row

    def test_dynamic_identity_survives_separate_static_resource_failure(self):
        row = detector.classify_native(self.native_row(), POLICY)
        self.assertEqual(row['verifiedVendor'], 'uu')
        self.assertEqual(row['codeIdentity']['staticValidation']['status'], 'failed')
        self.assertFalse(row['runningMemoryAttested'])

    def test_native_claim_requires_status_code_and_lifetime_consistency(self):
        for bad_field in ('OSStatus', 'status', 'identityStableAcrossReads', 'verifiedRole', 'TeamIdentifier'):
            row = self.native_row()
            if bad_field == 'OSStatus': row['codeIdentity']['dynamicValidation']['OSStatus'] = -54
            elif bad_field == 'status': row['codeIdentity']['dynamicValidation']['status'] = 'unknown'
            elif bad_field == 'TeamIdentifier': row['codeIdentity']['metadata']['TeamIdentifier'] = 'OTHERTEAM1'
            elif bad_field == 'verifiedRole': row['verifiedRole'] = 'daemon'
            else: row[bad_field] = False
            checked = detector.classify_native(row, POLICY)
            self.assertNotIn('verifiedVendor', checked, bad_field)
            self.assertEqual(checked['category'], 'inspectionUnavailable')

    def test_unhinted_permission_failure_still_requires_review(self):
        row = candidate(); row['candidateVendors'] = []; row['category'] = 'inspectionUnavailable'
        result = detector.summarize({'enumerationComplete': True}, [row], POLICY)
        self.assertEqual(result['recommendedExamAction'], 'review_required')

    def test_native_old_schema_or_invalid_return_not_accepted(self):
        for schema, return_code in [(1, 0), (2, 64), (2, None)]:
            raw = {'returnCode': return_code, 'stdout': json.dumps({'schemaVersion': schema, 'processes': []}),
                   'timedOut': return_code is None}
            with patch.object(detector, 'run', return_value=raw):
                result = detector.inventory('/synthetic')
            self.assertFalse(result['enumerationComplete'])

    def test_policy_provenance_failure_clears_positive_rows(self):
        native = {'schemaVersion': 2, 'processes': [self.native_row()], 'enumerationComplete': True,
                  'policySHA256': 'incorrect', 'policyFileUnchanged': True, 'testPolicy': False}
        with patch.object(detector, 'inventory', return_value=native):
            result = detector.scan('/synthetic', POLICY)
        self.assertFalse(result['nativePolicyBound'])
        self.assertNotIn('verifiedVendor', result['processes'][0])
        self.assertEqual(result['recommendedExamAction'], 'review_required')

    def test_test_policy_report_cannot_enter_production_summary(self):
        def fake_inventory(binary, pid=None, policy_path=None, budget=None):
            return {'processes': [self.native_row()], 'enumerationComplete': True,
                    'policySHA256': hashlib.sha256(policy_path.read_bytes()).hexdigest(),
                    'policyFileUnchanged': True, 'testPolicy': True}
        with patch.object(detector, 'inventory', side_effect=fake_inventory):
            result = detector.scan('/synthetic', POLICY)
        self.assertFalse(result['nativePolicyBound'])
        self.assertNotIn('verifiedVendor', result['processes'][0])

    def test_successful_native_scan_binds_snapshot_policy(self):
        def fake_inventory(binary, pid=None, policy_path=None, budget=None):
            return {'processes': [self.native_row()], 'enumerationComplete': True,
                    'policySHA256': hashlib.sha256(policy_path.read_bytes()).hexdigest(),
                    'policyFileUnchanged': True, 'testPolicy': False}
        with patch.object(detector, 'inventory', side_effect=fake_inventory):
            result = detector.scan('/synthetic', POLICY)
        self.assertTrue(result['nativePolicyBound'])
        self.assertEqual(result['vendors']['uu']['verifiedCount'], 1)


if __name__ == '__main__':
    unittest.main()
