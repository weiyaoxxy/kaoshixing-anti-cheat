#!/usr/bin/env python3
"""Run native identity cases against owned, harmless fixtures. Never touch remote apps."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def command(argv, **kwargs):
    return subprocess.run([str(x) for x in argv], capture_output=True, text=True,
                          timeout=kwargs.pop('timeout', 20), **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    results, owned = [], []
    production = ROOT / 'Sources/RemoteProcessInventory/policy.json'

    def check(label, passed, evidence=None):
        results.append({'case': label, 'passed': bool(passed), 'evidence': evidence})
        if not passed:
            raise AssertionError(label)

    def observe(label, pid=None, policy=None, extra=(), budget=5):
        argv = [args.inventory, '--policy', policy or production, '--budget', str(budget)]
        if pid is not None:
            argv += ['--pid', str(pid)]
        argv += list(extra)
        result = command(argv, timeout=budget + 5)
        (args.output / f'{label}.stdout.json').write_text(result.stdout)
        (args.output / f'{label}.stderr.txt').write_text(result.stderr)
        return result, json.loads(result.stdout) if result.stdout.strip() else None

    def spawn(path, *argv):
        process = subprocess.Popen([str(path), *map(str, argv)], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        owned.append(process)
        return process

    try:
        paths, hashes = [], []
        for variant in (1, 2):
            dest = args.output / f'identity-fixture-{variant}'
            built = command(['xcrun', 'clang', f'-DFIXTURE_VARIANT={variant}',
                             Path(__file__).parent / 'fixture.c', '-o', dest])
            check(f'compile_fixture_{variant}', built.returncode == 0, built.stderr)
            signed = command(['/usr/bin/codesign', '--force', '--sign', '-', '--identifier',
                              f'org.example.exam.identityfixture.{variant}', dest])
            check(f'sign_fixture_{variant}', signed.returncode == 0, signed.stderr)
            info = command(['/usr/bin/codesign', '-d', '--verbose=4', dest])
            cdhash = next(x.split('=', 1)[1] for x in info.stderr.splitlines() if x.startswith('CDHash='))
            paths.append(dest); hashes.append(cdhash)
        policy = args.output / 'test-policy.json'
        policy.write_text(json.dumps({'schemaVersion': 2, 'testOnly': True,
            'policyVersion': 'isolated-fixture-test-v1', 'scope': 'owned harmless fixtures only',
            'vendors': {'fixture': {'teamID': '', 'displayName': 'Fixture',
                'identifiers': {f'org.example.exam.identityfixture.{i}': 'fixture' for i in (1, 2)},
                'testCDHashes': hashes}}}, indent=2))

        # Test policy cannot weaken the production path silently.
        result, _ = observe('test-policy-rejected', policy=policy)
        check('test_policy_requires_explicit_flag', result.returncode == 64)
        malformed_policy = args.output / 'malformed-policy.json'
        malformed = json.loads(production.read_text())
        malformed['vendors']['sunlogin']['requiredCDHashes'] = 'must-not-be-ignored'
        malformed_policy.write_text(json.dumps(malformed))
        result, _ = observe('malformed-pins-rejected', policy=malformed_policy)
        check('malformed_pin_constraint_rejected', result.returncode == 64)

        moved = args.output / 'unrelated-directory' / 'document-worker'
        moved.parent.mkdir()
        shutil.copy2(paths[0], moved)
        process = spawn(moved, 12)
        process.stdout.readline()
        result, report = observe('renamed', process.pid, policy, ['--allow-test-policy'])
        row = report['processes'][0]
        check('renamed_moved_has_no_name_hint', row['candidateVendors'] == [])
        check('renamed_dynamic_identity_verified', row.get('verifiedVendor') == 'fixture'
              and row['codeIdentity']['dynamicValidation']['status'] == 'verified')
        check('separate_static_validation_verified', row['codeIdentity']['staticValidation']['status'] == 'verified')
        check('test_policy_label_preserved', report['testPolicy'] is True)

        # Full enumeration must also return the renamed process, not only --pid.
        result, report = observe('full-enumeration-renamed', policy=policy,
                                 extra=['--allow-test-policy', '--skip-static'], budget=12)
        matches = [row for row in report['processes'] if row['pid'] == process.pid]
        check('full_scan_keeps_unhinted_fixture', len(matches) == 1 and matches[0].get('verifiedVendor') == 'fixture')

        fake = args.output / 'UURemote'
        shutil.copy2(paths[0], fake)
        fake_process = spawn(fake, 8)
        fake_process.stdout.readline()
        _, report = observe('same-name-impostor', fake_process.pid)
        row = report['processes'][0]
        check('same_name_is_hint_only', row['candidateVendors'] == ['uu'] and 'verifiedVendor' not in row)

        # Unknown process path is still attempted using the PID's runtime guest.
        _, report = observe('nonexistent', 2147483647)
        check('missing_pid_is_unknown', report['enumerationComplete'] is False
              and report['processes'][0]['codeIdentity']['guestOSStatus'] != 0)

        _, report = observe('deadline', budget=0.0001)
        check('deadline_returns_incomplete_not_clean', report['coverage']['scanDeadlineExceeded'] is True
              and report['enumerationComplete'] is False)
        check('deadline_owned_child_reaped', report['ownedWorkerTerminatedForBudget'] is True
              and report['workerWaitStatus'] == 9)
        check('deadline_bounded_wall_time', report['elapsedSeconds'] < 2)

        # Kill only our own inventory supervisor, then verify its worker stops
        # itself rather than becoming a long-lived orphan. Never signal a PID
        # obtained from a system-wide search.
        supervisor = spawn(args.inventory, '--policy', production, '--budget', '30')
        worker_pid = None
        for _ in range(50):
            children = command(['/usr/bin/pgrep', '-P', str(supervisor.pid)])
            if children.stdout.strip():
                worker_pid = int(children.stdout.split()[0]); break
            time.sleep(0.02)
        check('owned_worker_observed_for_supervisor_failure', worker_pid is not None)
        supervisor.kill(); supervisor.wait(timeout=3)
        inactive = False
        for _ in range(50):
            state = command(['/bin/ps', '-p', str(worker_pid), '-o', 'stat=']).stdout.strip()
            if not state or state.startswith('Z'):
                inactive = True; break
            time.sleep(0.02)
        check('worker_exits_after_supervisor_death', inactive)

        exec_process = spawn(paths[0], 'exec-after', paths[1])
        _, before = observe('before-exec', exec_process.pid, policy, ['--allow-test-policy'])
        time.sleep(1.7)
        _, after = observe('after-exec', exec_process.pid, policy, ['--allow-test-policy'])
        first, second = before['processes'][0], after['processes'][0]
        check('same_pid_exec_identity_changes', first['pid'] == second['pid']
              and first['codeIdentity']['metadata']['CDHash'] != second['codeIdentity']['metadata']['CDHash'])
        check('exec_coverage_limit_not_hidden', first['samePIDExecCoverageGuaranteed'] is False
              and second['samePIDExecCoverageGuaranteed'] is False)
        check('new_exec_identity_revalidated', second.get('verifiedVendor') == 'fixture'
              and second['codeIdentity']['metadata']['Identifier'].endswith('.2'))

        short = spawn(paths[0], 1)
        # Deliberately do not wait/poll yet: the owned child should be a zombie.
        time.sleep(1.3)
        _, report = observe('zombie', short.pid, policy, ['--allow-test-policy'])
        row = report['processes'][0]
        check('zombie_excluded_only_by_kernel_state', row['category'] == 'nonExecutingZombie'
              and row['kernelProcessStatusBefore'] == 5 and row['kernelProcessStatusAfter'] == 5
              and row['identityStableAcrossReads'] is True and 'verifiedVendor' not in row)
        short.wait(timeout=3)
        _, report = observe('exited', short.pid, policy, ['--allow-test-policy'])
        check('exited_instance_not_verified', all('verifiedVendor' not in row for row in report['processes']))
    finally:
        for process in owned:
            if process.poll() is None:
                # Only exact subprocess handles created above, never remote software.
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=2)
        (args.output / 'result.json').write_text(json.dumps({'cases': results,
            'passed': all(row['passed'] for row in results), 'testPolicyOnly': True,
            'realVendorRenameRuntimeVerified': False,
            'productionPolicySHA256': hashlib.sha256(production.read_bytes()).hexdigest(),
            'inventorySHA256': hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
            'realRemoteApplicationMutationPerformed': False}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': True, 'caseCount': len(results), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
