#!/usr/bin/env python3
"""Runs only the newly built GUI and synthetic pipe fixtures. No remote-app operations."""
import argparse, json, os, subprocess, time
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--app', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--scenarios', nargs='+', default=['ready_only','normal','pause','stale','invalid','replay','wrong_session','oversized','exit','workspace_sleep','no_end_ack'])
a = p.parse_args()
a.output.mkdir(parents=True, mode=0o700, exist_ok=False)
fixture = Path(__file__).resolve().parent/'mock_guard.py'
binary = a.app/'Contents/MacOS/NativeExamHookDemo'
results=[]
for scenario in a.scenarios:
    folder=a.output/scenario
    folder.mkdir(mode=0o700)
    policy=folder/'fixture-policy.json'
    policy.write_text(json.dumps({'scenario':scenario}))
    output=folder/'ui'
    duration=8 if scenario=='stale' else 4
    args=[str(binary),'--output',str(output),'--guard-runner',str(fixture),
          '--guard-inventory','/usr/bin/true','--guard-policy',str(policy),
          '--guard-test-mode','--duration',str(duration)]
    if scenario!='ready_only': args.append('--guard-test-auto-start')
    if scenario=='workspace_sleep': args.extend(['--guard-test-workspace-event-after','2'])
    log=(folder/'stdout-stderr.log').open('wb')
    proc=subprocess.Popen(args,stdout=log,stderr=log)
    snapshots=[]
    deadline=time.monotonic()+(21 if scenario=='no_end_ack' else duration+3)
    try:
        while time.monotonic()<deadline:
            try:
                state=json.loads((output/'state.json').read_text())
                if not snapshots or state != snapshots[-1]: snapshots.append(state)
            except (FileNotFoundError,json.JSONDecodeError): pass
            if proc.poll() is not None: break
            time.sleep(.08)
        # Any unresolved fixture scenario intentionally cancels AppKit quit. We
        # stop only our own GUI child after observing the failed recovery state.
        if proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=3)
    finally:
        log.close()
    (folder/'snapshots.json').write_text(json.dumps(snapshots,ensure_ascii=False,indent=2))
    assert snapshots, (scenario,'no UI states', (folder/'stdout-stderr.log').read_text())
    checks={
        'private_output_permissions':output.stat().st_mode&0o777 == 0o700,
        'no_answers_in_guard_state':all('shortAnswer' not in s and 'longAnswer' not in s and s.get('answerContentPersisted') is False for s in snapshots),
        'no_unpermitted_visible_questions':all(not s['questionsVisible'] or s['questionsAllowed'] for s in snapshots),
        'explicit_test_mode':all(s['testOnlyMode'] for s in snapshots),
    }
    if scenario=='ready_only':
        checks['ready_does_not_create_questions']=all(not s['questionControlsCreated'] for s in snapshots)
    else:
        checks['start_reaches_synthetic_exam']=any(s['questionsVisible'] for s in snapshots)
    if scenario in ('pause','stale','invalid','replay','wrong_session','oversized','exit','workspace_sleep'):
        visible_index=next((i for i,s in enumerate(snapshots) if s['questionsVisible']),None)
        after=snapshots[visible_index+1:] if visible_index is not None else []
        hidden_index=next((i for i,s in enumerate(after) if not s['questionsVisible']),None)
        checks['fault_hides_questions']=hidden_index is not None
        checks['no_automatic_resume']=hidden_index is not None and all(not s['questionsVisible'] for s in after[hidden_index:])
    if scenario=='no_end_ack':
        checks['quit_timeout_preserves_recovery_unknown']=any(s.get('recoveryWaitTimedOut') is True for s in snapshots)
        checks['never_claims_finished']=all(s['guardState']!='finished' for s in snapshots)
    else:
        if scenario!='exit': checks['end_ack_received']=snapshots[-1]['guardState']=='finished'
    result={'scenario':scenario,'checks':checks,'passed':all(checks.values()),'guiExitCode':proc.returncode,
            'actualRemoteTerminationTested':False, 'actualDeviceSleepTested':False}
    results.append(result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    (a.output/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
assert all(r['passed'] for r in results), 'one or more UI fixture scenarios failed'
