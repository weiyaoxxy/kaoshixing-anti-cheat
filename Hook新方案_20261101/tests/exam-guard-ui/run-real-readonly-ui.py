#!/usr/bin/env python3
"""Real GUI + real runner + real inventory. Only inspect/end UI actions; no worker configured."""
import argparse, datetime, hashlib, json, sqlite3, subprocess, time
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--app',type=Path,required=True)
p.add_argument('--inventory',type=Path,required=True)
p.add_argument('--policy',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--ax-controller',type=Path,required=True)
a=p.parse_args()
a.output.mkdir(parents=True,mode=0o700,exist_ok=False)
project=Path(__file__).resolve().parents[2]
runner=project/'scripts/exam-guard.py'
binary=a.app/'Contents/MacOS/NativeExamHookDemo'
ui=a.output/'ui'; session=ui/'guard-session'
initial_hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in (binary,runner,a.inventory,a.policy)}
ui_actions=[]; snapshots=[]; child_pids=[]

def state():
    try:
        value=json.loads((ui/'state.json').read_text())
        if not snapshots or snapshots[-1]!=value: snapshots.append(value)
        return value
    except (FileNotFoundError,json.JSONDecodeError): return None

def wait_for(predicate, seconds, label):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        value=state()
        if predicate(value): return value
        if proc.poll() is not None: raise AssertionError('GUI exited while waiting for '+label)
        time.sleep(.1)
    raise AssertionError('Timed out: '+label)

def click(title=None,close=False):
    # Interact only with the GUI child created by this harness. Never press
    # requestAuthorization, never supply a worker executable, and never send
    # keystrokes to an unrelated frontmost application.
    if title not in (None,'开始检查 / 重新检查','结束并恢复'): raise ValueError('unsafe UI action')
    operation = 'close' if close else 'inspect' if title == '开始检查 / 重新检查' else 'end'
    result=subprocess.run([str(a.ax_controller),str(proc.pid),operation],capture_output=True,text=True,timeout=8)
    ui_actions.append({'operation':operation,'guiPID':proc.pid,'backend':'AXUIElementCreateApplication',
                       'exitCode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    if result.returncode: raise AssertionError(result.stderr)

commands=[str(binary),'--output',str(ui),'--guard-runner',str(runner),'--guard-inventory',str(a.inventory),'--guard-policy',str(a.policy)]
with (a.output/'app-output.log').open('wb') as log:
    proc=subprocess.Popen(commands,stdout=log,stderr=log)
    try:
        initial=wait_for(lambda s:s and s.get('guardSequence',0)>0,12,'initial real guard status')
        assert not initial['questionControlsCreated'] and not initial['questionsVisible']
        raw=subprocess.run(['/bin/ps','-axo','pid=,ppid=,comm='],capture_output=True,text=True,check=True).stdout
        for line in raw.splitlines():
            bits=line.strip().split(None,2)
            if len(bits)==3 and int(bits[1])==proc.pid:
                child_pids.append({'pid':int(bits[0]),'comm':bits[2]})
        click('开始检查 / 重新检查')
        evidence_state=wait_for(lambda s:s and (session/'latest-inventory.json').exists(),38,'real inventory observation')
        inventory=json.loads((session/'latest-inventory.json').read_text())
        # Wait for a subsequent status and at least one recorded reference receipt.
        observed_sequence=evidence_state['guardSequence']
        final_inspection=wait_for(lambda s:s and s['guardSequence']>observed_sequence and s.get('guardStatus',{}).get('serverReported') is True,12,'reference acknowledgement')
        assert final_inspection['guardState'] in ('preparing','paused')
        assert not final_inspection['questionControlsCreated'] and not final_inspection['questionsVisible']
        assert final_inspection['guardStatus']['backend']=='unprivileged'
        win=final_inspection['preparation']['windowID']
        capture=subprocess.run(['/usr/sbin/screencapture','-x','-l',str(win),str(a.output/'preparation-real.png')],capture_output=True,text=True,timeout=5)
        (a.output/'capture-result.json').write_text(json.dumps({'exitCode':capture.returncode,'stderr':capture.stderr}))
        click('结束并恢复')
        finished=wait_for(lambda s:s and s['guardState']=='finished',12,'finished read-only session')
        click(close=True)
        proc.wait(timeout=6)
        assert proc.returncode==0
    except Exception:
        # A recovery-safe UI end is attempted before ending only this test GUI.
        if proc.poll() is None:
            try: click('结束并恢复'); time.sleep(1)
            except Exception: pass
            proc.terminate(); proc.wait(timeout=4)
        raise
    finally:
        (a.output/'ui-actions.json').write_text(json.dumps(ui_actions,ensure_ascii=False,indent=2))
        (a.output/'ui-snapshots.json').write_text(json.dumps(snapshots,ensure_ascii=False,indent=2))

# Verify child runner exit without sending any signal.
remaining=[]
for child in child_pids:
    deadline=time.monotonic()+6
    while time.monotonic()<deadline:
        result=subprocess.run(['/bin/ps','-p',str(child['pid']),'-o','comm='],capture_output=True,text=True)
        if not result.stdout.strip(): break
        time.sleep(.1)
    if result.stdout.strip(): remaining.append(child)
assert not remaining, remaining

def read_db(path, query):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db: return db.execute(query).fetchall()
outbox=read_db(session/'outbox/outbox.sqlite3','SELECT sequence,payload,receipt FROM events ORDER BY sequence')
receipts=read_db(session/'receiver/receipts.sqlite3','SELECT sequence,payload,receipt FROM receipts ORDER BY sequence')
rows=[]
for seq,payload,receipt in outbox:
    event=json.loads(payload)
    rows.append({'sequence':seq,'event':event.get('event'),'receiptAcknowledged':receipt is not None,
                 'receipt':json.loads(receipt) if receipt else None})
products={}
for row in inventory['processes']:
    vendor=row.get('verifiedVendor') or row.get('codeIdentity',{}).get('verifiedVendor')
    if vendor: products[vendor]=products.get(vendor,0)+1
assert {'uu','todesk','sunlogin'} <= set(products), products
assert receipts, 'No reference receipt recorded'
assert all('requestAuthorization' not in json.dumps(x) for x in ui_actions)
assert all(not s['questionControlsCreated'] and not s['questionsVisible'] and s.get('answerContentPersisted') is False for s in snapshots)
manifest={'inputHashes':initial_hashes,'inputFilesUnchanged':all(hashlib.sha256(Path(f).read_bytes()).hexdigest()==h for f,h in initial_hashes.items())}
assert manifest['inputFilesUnchanged']
summary={'testKind':'real_gui_real_runner_readonly_inventory','observedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'verifiedProductComponents':products,'enumerationComplete':inventory.get('enumerationComplete'),
         'coverage':inventory.get('coverage'),'allQuestionsWithheld':True,'neverCreatedQuestionControls':True,
         'guardBackend':'unprivileged','administratorAuthorizationRequested':False,'workerConfigured':False,
         'systemMutationRequested':False,'appExitCode':proc.returncode,'runnerChildren':child_pids,'runnerExited':not remaining,
         'referenceReceipts':len(receipts),'outboxTotal':len(rows),'pendingEvents':sum(not x['receiptAcknowledged'] for x in rows),
         'formalServerReported':False,'passed':True}
(a.output/'events-and-receipts.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
(a.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
