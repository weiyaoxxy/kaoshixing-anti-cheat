#!/usr/bin/env python3
"""Read-only process detection. Never launches/stops remote apps or changes policy.

Full PID discovery and native dynamic identity plus independent static validation.
This is a bounded snapshot tool, not a production exam guard or attestation agent.
All command arguments are passed without a shell, including literal signing IDs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / 'Sources/RemoteProcessInventory/policy.json'
IDENTITY_FIELDS = ('pid', 'uid', 'executable', 'startTimeSeconds', 'startTimeMicroseconds')
RUNTIME_ROLES = {'gui', 'service', 'sessionProxy', 'session', 'server', 'daemon',
                 'desktopAgent', 'helper', 'screenwallHelper'}


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def run(argv, timeout=8):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, errors='replace',
                                timeout=timeout, check=False)
        return {'returnCode': result.returncode, 'stdout': result.stdout,
                'stderr': result.stderr, 'timedOut': False}
    except subprocess.TimeoutExpired:
        return {'returnCode': None, 'stdout': '', 'stderr': 'command timeout', 'timedOut': True}
    except OSError as exc:
        return {'returnCode': None, 'stdout': '', 'stderr': str(exc), 'timedOut': False}


def inventory(binary, pid=None, policy_path=None, budget=12):
    argv = [str(binary), '--budget', str(budget)]
    if pid is not None:
        argv += ['--pid', str(pid)]
    if policy_path is not None:
        argv += ['--policy', str(policy_path)]
    result = run(argv, timeout=budget + 3)
    try:
        value = json.loads(result['stdout'])
        if (result['returnCode'] not in (0, 2) or value.get('schemaVersion') != 2
                or not isinstance(value.get('processes'), list)):
            raise ValueError('invalid inventory result')
        return value
    except (ValueError, TypeError, AttributeError):
        return {'processes': [], 'enumerationComplete': False, 'coverage': {},
                'unresolved': [{'reason': 'inventoryFailed',
                                'returnCode': result['returnCode'], 'timedOut': result['timedOut']}]}


def same_lifetime(before, after):
    return (bool(before) and bool(after)
            and all(field in before and field in after and before[field] == after[field]
                    for field in IDENTITY_FIELDS))


def file_identity(path):
    try:
        s = Path(path).stat()
        return {'realPath': str(Path(path).resolve()), 'device': s.st_dev, 'inode': s.st_ino,
                'bytes': s.st_size, 'mtimeNS': s.st_mtime_ns, 'ctimeNS': s.st_ctime_ns}
    except OSError:
        return None


def requirement_literal(value):
    # Escape the codesign requirement language, never a shell command.
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def match_policy(metadata, hints, policy):
    return [key for key, vendor in policy['vendors'].items()
            if metadata.get('TeamIdentifier') == vendor['teamID']
            and metadata.get('Identifier') in vendor['identifiers']
            and (metadata.get('Identifier') not in vendor.get('requiredCDHashes', {})
                 or metadata.get('CDHash') in vendor['requiredCDHashes'][metadata['Identifier']])]


def signature(path, hints, policy):
    before = file_identity(path)
    meta_result = run(['/usr/bin/codesign', '-d', '--verbose=4', path])
    metadata = {}
    for line in meta_result['stderr'].splitlines():
        if line.startswith(('Identifier=', 'TeamIdentifier=', 'CDHash=')):
            key, value = line.split('=', 1)
            metadata[key] = value
    matches = match_policy(metadata, hints, policy)
    answer = {'status': 'unknown', 'metadata': metadata, 'matchedVendors': matches,
              'metadataReadReturnCode': meta_result['returnCode'], 'fileBefore': before}
    if meta_result['returnCode'] != 0:
        answer['reason'] = 'signatureMetadataUnavailable'
    elif len(matches) != 1:
        answer['status'] = 'identityNotMatched'
        answer['reason'] = 'metadataDoesNotMatchConfiguredTeamComponentAndBuild'
    else:
        vendor = policy['vendors'][matches[0]]
        req = ('anchor apple generic and certificate leaf[subject.OU] = '
               + requirement_literal(vendor['teamID']) + ' and identifier '
               + requirement_literal(metadata['Identifier']))
        if metadata['Identifier'] in vendor.get('requiredCDHashes', {}):
            req += ' and cdhash H"' + metadata['CDHash'] + '"'
        # codesign treats a requirement without '=' as a file name.
        checked = run(['/usr/bin/codesign', '--verify', '--strict', '-R', '=' + req, path])
        answer.update(verificationReturnCode=checked['returnCode'], timedOut=checked['timedOut'],
                      requirement=req, diagnostic=checked['stderr'][:2000])
        if checked['returnCode'] == 0:
            answer['status'] = 'validForConfiguredRequirement'
        elif (checked['returnCode'] is None or any(token in checked['stderr'].lower()
              for token in ('permission denied', 'not permitted', 'access denied',
                            'invalid requirement specification', 'no such file or directory'))):
            answer['status'] = 'unknown'
            answer['reason'] = 'verificationUnavailable'
        else:
            answer['status'] = 'verificationFailed'
    answer['fileAfter'] = file_identity(path)
    answer['fileStableAcrossVerification'] = before is not None and before == answer['fileAfter']
    if not answer['fileStableAcrossVerification']:
        answer['status'] = 'unknown'
        answer['reason'] = 'fileChangedOrUnavailableDuringVerification'
    return answer


def classify(candidate, signed, after, policy):
    stable = same_lifetime(candidate, after)
    matches = signed.get('matchedVendors', [])
    verified = (stable and signed.get('status') == 'validForConfiguredRequirement'
                and signed.get('fileStableAcrossVerification') is True and len(matches) == 1)
    row = dict(candidate)
    row.update(signature=signed, processStableAfterVerification=stable,
               status='verifiedComponentRunning' if verified else 'candidateUnconfirmed',
               remoteSessionVerified=False, runningMemoryAttested=False)
    if verified:
        vendor = matches[0]
        row['verifiedVendor'] = vendor
        row['verifiedRole'] = policy['vendors'][vendor]['identifiers'][signed['metadata']['Identifier']]
    if not stable:
        row['uncertaintyReason'] = 'processExitedChangedOrBecameUnreadable'
    return row


def classify_native(candidate, policy):
    """Validate native result consistency. This is not an independent signature verifier."""
    row = dict(candidate)
    evidence = row.get('codeIdentity', {})
    metadata = evidence.get('metadata', {})
    matches = match_policy(metadata, [], policy)
    validation = evidence.get('dynamicValidation', {})
    valid = (row.get('identityStableAcrossReads') is True and len(matches) == 1
             and validation.get('status') == 'verified' and validation.get('OSStatus') == 0
             and row.get('category') == 'knownRemoteIdentityVerified'
             and row.get('verifiedVendor') == matches[0]
             and row.get('verifiedRole') == policy['vendors'][matches[0]]['identifiers'][metadata['Identifier']])
    if row.get('verifiedVendor') and not valid:
        row.pop('verifiedVendor', None)
        row.pop('verifiedRole', None)
        row['status'] = row['category'] = 'inspectionUnavailable'
        row['uncertaintyReason'] = 'nativeEvidenceInconsistentWithPolicy'
    row['remoteSessionVerified'] = False
    row['runningMemoryAttested'] = False
    return row


def summarize(native, rows, policy):
    complete = native.get('enumerationComplete') is True and not native.get('unresolved')
    result = {}
    suspicious = False
    for key, vendor in policy['vendors'].items():
        # Identity confirmation is independent of discovery hints. Renamed and
        # moved binaries must survive aggregation just as they survive discovery.
        confirmed = [row for row in rows if row.get('verifiedVendor') == key]
        candidates = [row for row in rows if key in row.get('candidateVendors', [])
                      or key in row.get('codeIdentity', {}).get('matchedVendors', [])
                      or row.get('verifiedVendor') == key]
        unknown = [row for row in candidates if row.get('verifiedVendor') != key]
        runtime = [row for row in confirmed if row.get('verifiedRole') in RUNTIME_ROLES]
        status = ('runningVerifiedComponents' if confirmed else 'candidateUnconfirmed' if candidates
                  else 'notObservedWithinScope' if complete else 'inspectionIncomplete')
        result[key] = {'displayName': vendor['displayName'], 'status': status,
                       'candidateCount': len(candidates), 'verifiedCount': len(confirmed),
                       'unconfirmedCount': len(unknown), 'verifiedRuntimeCount': len(runtime),
                       'candidatePIDs': sorted(row['pid'] for row in candidates),
                       'verifiedPIDs': sorted(row['pid'] for row in confirmed),
                       'discoveryCompleteWithinDeclaredScope': complete}
        suspicious |= bool(unknown or confirmed and not runtime)
    category_counts = {}
    for row in rows:
        category = row.get('category', row.get('status', 'unknown'))
        category_counts[category] = category_counts.get(category, 0) + 1
    if any(row['verifiedRuntimeCount'] for row in result.values()):
        action = 'block_start_recommended'
    elif suspicious or not complete or any(row.get('category') in
            ('inspectionUnavailable', 'processExitedOrChanged', 'knownMetadataButValidationFailed') for row in rows):
        action = 'review_required'
    else:
        action = 'no_supported_target_observed'
    return {'vendors': result, 'recommendedExamAction': action,
            'examGateActuallyEnforced': False, 'enumerationComplete': complete,
            'categoryCounts': category_counts,
            'unclassifiedCodeMeansAllowed': False}


def scan(binary, policy, budget=12):
    started = utc()
    started_clock = time.monotonic()
    # Snapshot the parsed policy once for this native invocation. No mutable
    # source path is reread between candidate checks.
    with tempfile.TemporaryDirectory(prefix='exam-identity-policy-') as temporary:
        policy_path = Path(temporary) / 'policy.json'
        policy_bytes = (json.dumps(policy, ensure_ascii=False, sort_keys=True) + '\n').encode()
        policy_path.write_bytes(policy_bytes)
        native = inventory(binary, policy_path=policy_path, budget=budget)
    bound = (native.get('policySHA256') == hashlib.sha256(policy_bytes).hexdigest()
             and native.get('policyFileUnchanged') is True and native.get('testPolicy') is False)
    if not bound:
        native = dict(native)
        native['enumerationComplete'] = False
        native['unresolved'] = list(native.get('unresolved', [])) + [{'reason': 'nativePolicyProvenanceUnconfirmed'}]
    rows = [classify_native(row, policy) for row in native['processes']]
    if not bound:
        for row in rows:
            row.pop('verifiedVendor', None); row.pop('verifiedRole', None)
            row['status'] = row['category'] = 'inspectionUnavailable'
    return {'schemaVersion': 2, 'startedAtUTC': started, 'finishedAtUTC': utc(),
            'elapsedSeconds': time.monotonic() - started_clock,
            'policyVersion': policy['policyVersion'], 'policyScope': policy['scope'],
            'policySHA256': native.get('policySHA256'), 'nativePolicyBound': bound,
            'processes': rows, 'coverage': native.get('coverage', {}),
            'unresolved': native.get('unresolved', []), **summarize(native, rows, policy),
            'systemMutationPerformed': False, 'screenOrInputCaptured': False,
            'remoteSessionVerified': False, 'serverReported': False,
            'limitations': [
                'All enumerated PIDs are attempted within a bounded, non-atomic scan.',
                'Permission failures, exits, timeouts and same-PID exec remain explicit coverage limitations.',
                'Unclassified signed or ad-hoc code is not proof that the code is allowed or non-remote.',
                'Dynamic identity validation and static validation are separate; neither attests all running memory.',
                'A remote-software component running does not prove an active remote session or cheating.',
                'This diagnostic CLI does not terminate targets, enforce an exam gate or report to a server.'
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New result directory')
    parser.add_argument('--policy', type=Path, default=DEFAULT_POLICY)
    parser.add_argument('--samples', type=int, default=1, choices=range(1, 11))
    parser.add_argument('--interval', type=float, default=1)
    parser.add_argument('--budget', type=float, default=12, help='Native scan deadline in seconds')
    args = parser.parse_args()
    if not 0 < args.budget <= 120:
        parser.error('--budget must be in (0, 120]')
    if not 0 <= args.interval <= 30:
        parser.error('--interval must be between 0 and 30 seconds')
    if not args.inventory.is_file():
        parser.error('Build the native inventory first')
    policy_bytes = args.policy.read_bytes()
    policy = json.loads(policy_bytes)
    input_hashes = {'inventorySHA256': digest(args.inventory),
                    'scriptSHA256': digest(__file__),
                    'policySHA256': hashlib.sha256(policy_bytes).hexdigest()}
    args.output.mkdir(parents=True, exist_ok=False)
    reports = []
    for number in range(args.samples):
        report = scan(args.inventory.resolve(), policy, budget=args.budget)
        name = f'snapshot-{number + 1:02d}.json'
        (args.output / name).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        reports.append({'file': name, 'startedAtUTC': report['startedAtUTC'],
                        'elapsedSeconds': report['elapsedSeconds'],
                        'enumerationComplete': report['enumerationComplete'],
                        'recommendedExamAction': report['recommendedExamAction'], 'vendors': report['vendors']})
        print(json.dumps(reports[-1], ensure_ascii=False), flush=True)
        if number + 1 < args.samples:
            time.sleep(args.interval)
    final_hashes = {'inventorySHA256': digest(args.inventory),
                    'scriptSHA256': digest(__file__), 'policySHA256': digest(args.policy)}
    unchanged = all(value is not None and value == final_hashes[key]
                    for key, value in input_hashes.items())
    summary = {'schemaVersion': 2, 'samples': reports, **input_hashes,
               'inputHashesAtEnd': final_hashes, 'inputFilesUnchanged': unchanged,
               'provenanceChanged': not unchanged,
               'observationsUsableWithDeclaredLimitations': unchanged,
               'systemMutationPerformed': False, 'remoteSessionVerified': False,
               'examGateActuallyEnforced': False}
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
