#!/usr/bin/env python3
"""Exercise only private Demo copies. Never modifies or restarts UU.

Usage: python3 scripts/test-runtime-integrity.py /absolute/path/Test.app /new/artifact/dir
The supplied app must be a monitoring build from build-native-demo.sh.
"""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time

app = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
output.mkdir(parents=True, exist_ok=False)

fixture = output / "Fixture.m"
fixture.write_text(r'''
#import <AppKit/AppKit.h>
#import <objc/runtime.h>
#include <dlfcn.h>
static IMP original;
static void no_tick(id self, SEL cmd) { (void)self; (void)cmd; }
static void replacement(id self, SEL cmd, NSEvent *event) {
    ((void (*)(id, SEL, NSEvent *))original)(self, cmd, event);
}
__attribute__((constructor)) static void start_fixture(void) {
    const char *kind = getenv("INTEGRITY_FIXTURE_ACTION");
    if (!kind) return;
    if (strcmp(kind, "late-swizzle") == 0) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            Method method = class_getInstanceMethod([NSApplication class], @selector(sendEvent:));
            original = method_setImplementation(method, (IMP)replacement);
        });
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 7 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            if (original) method_setImplementation(class_getInstanceMethod([NSApplication class], @selector(sendEvent:)), original);
        });
    } else if (strcmp(kind, "disable-ui-tick") == 0) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            Class target = NSClassFromString(@"NativeExamAppDelegate");
            method_setImplementation(class_getInstanceMethod(target, NSSelectorFromString(@"tick")), (IMP)no_tick);
        });
    } else if (strcmp(kind, "late-load-unload") == 0) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            void *handle = dlopen(getenv("INTEGRITY_FIXTURE_PAYLOAD"), RTLD_NOW);
            if (handle) dlclose(handle);
        });
    }
}
''')
payload_source = output / "Payload.c"
payload_source.write_text("int integrity_fixture_payload(void) { return 7; }\n")
fixture_lib = output / "libIntegrityFixture.dylib"
payload_lib = output / "libTransientFixture.dylib"
for source, target, flags in [(fixture, fixture_lib, ["-framework", "AppKit"]), (payload_source, payload_lib, [])]:
    subprocess.run(["xcrun", "clang", "-dynamiclib", "-target", "arm64-apple-macos13.0", str(source), "-o", str(target)] + flags, check=True)
    subprocess.run(["codesign", "--force", "--sign", "-", str(target)], check=True, capture_output=True)

results = []

def run(name, *, inject=False, action=None, tamper=False, resign=False, deny_output=False, ui=False):
    if len(sys.argv) > 3 and name not in sys.argv[3:]:
        return
    case = output / name
    case.mkdir()
    copy = case / "IntegrityFixture.app"
    shutil.copytree(app, copy, symlinks=True)
    plist = copy / "Contents/Info.plist"
    original_plist = plist.read_bytes()
    changed = plistlib.loads(original_plist)
    changed["CFBundleDisplayName"] = "Integrity verification test fixture"
    if resign:
        plist.write_bytes(plistlib.dumps(changed))
        subprocess.run(["codesign", "--force", "--sign", "-", str(copy)], check=True, capture_output=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DYLD_", "INTEGRITY_FIXTURE_"))}
    if inject:
        env["DYLD_INSERT_LIBRARIES"] = str(fixture_lib)
    if action:
        env["INTEGRITY_FIXTURE_ACTION"] = action
        env["INTEGRITY_FIXTURE_PAYLOAD"] = str(payload_lib)
    run_output = case / "run"
    args = [str(copy / "Contents/MacOS/NativeExamHookDemo"), "--output", str(run_output), "--duration", "12"]
    args += ["--auto-type"] if ui else ["--integrity-probe"]
    process = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        if tamper or deny_output:
            time.sleep(2)
            if tamper:
                plist.write_bytes(plistlib.dumps(changed))
            if deny_output:
                for path in run_output.iterdir():
                    path.chmod(0o400)
                run_output.chmod(0o500)
            time.sleep(5)
            if tamper:
                plist.write_bytes(original_plist)
            if deny_output:
                run_output.chmod(0o700)
                for path in run_output.iterdir():
                    path.chmod(0o600)
        stdout, stderr = process.communicate(timeout=25)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        if run_output.exists():
            run_output.chmod(0o700)
            for path in run_output.iterdir():
                path.chmod(0o600)
    (case / "stdout.txt").write_text(stdout)
    (case / "stderr.txt").write_text(stderr)
    assert process.returncode == 0, (name, process.returncode, stderr)
    if ui:
        report = json.loads((run_output / "state.json").read_text())
        status = report["integrity"]
        assert report["finishing"]
        if action == "disable-ui-tick":
            assert report["publicLiveTick"] < 5, report["publicLiveTick"]
            assert status["elapsedSeconds"] >= 9, status
        else:
            assert report["publicLiveTick"] >= 10
            assert report["automaticTextUpdates"] >= 5
        assert "uuHook" in report
    else:
        status = json.loads(stdout)["integrity"]
    codes = {item["code"] for item in status["findings"]}
    if inject:
        assert "unexpected_loaded_image" in codes, (name, codes)
        assert status["requiresReview"]
    if action == "late-swizzle":
        assert "method_implementation_changed" in codes, codes
        assert "method_implementation_outside_expected_image" in codes, codes
    if action == "disable-ui-tick":
        assert any(item["code"] == "method_implementation_changed" and item["subject"] == "NativeExamAppDelegate.tick" for item in status["findings"]), status
    if action == "late-load-unload":
        assert any("libTransientFixture.dylib" in item["subject"] for item in status["findings"]), status
    if tamper:
        assert "signature_validation_failed" in codes, status
        assert status["signatures"]["bundleSeal"]["status"] == "valid", status
    if resign:
        assert status["signatures"]["bundleSeal"]["status"] == "valid", status
        assert status["signatures"]["releaseIdentity"]["status"] == "unknown", status
    if deny_output:
        assert status["recordingError"] and status["checksIncomplete"], status
    if not inject and not tamper:
        assert not status["requiresReview"], status
    events = [json.loads(line) for line in (run_output / "integrity-events.jsonl").read_text().splitlines()]
    assert len({row["sessionID"] for row in events}) == 1
    assert [row["sequence"] for row in events] == sorted({row["sequence"] for row in events})
    results.append({"case": name, "passed": True, "status": status["status"], "findingCodes": sorted(codes)})
    (output / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results[-1], ensure_ascii=False), flush=True)

run("clean")
run("startup-injection", inject=True)
run("runtime-swizzle-restored", inject=True, action="late-swizzle")
run("late-load-unload", inject=True, action="late-load-unload")
run("bundle-tampered-restored", tamper=True)
run("modified-then-resigned", resign=True)
run("output-unwritable-restored", deny_output=True)
run("ui-auto-type", ui=True)
run("ui-tick-hooked-monitor-continues", ui=True, inject=True, action="disable-ui-tick")
print(f"PASS: {len(results)} scenarios; artifacts: {output}")
