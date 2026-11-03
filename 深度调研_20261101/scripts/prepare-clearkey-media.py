#!/usr/bin/env python3
"""Make synthetic, locally served HLS controls with actual SAMPLE-AES encryption.

Uses Bento4's open-source mp42hls. The key is a public test key. No production
FairPlay certificate, licensed programme, or real examination data is used.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
tool = root / "research/clearkey/Bento4/Build/Targets/any-gnu-gcc/Release/mp42hls"
source = root.parent / "artifacts/matrix-20261101T082724Z/baseline/self-recording-A1C86017.mp4"
webroot = root / "research/clearkey/media"
webroot.mkdir(parents=True, exist_ok=True)
key = bytes.fromhex("00112233445566778899aabbccddeeff")
commands = []
for mode in ["plain", "encrypted"]:
    directory = webroot / mode
    directory.mkdir(exist_ok=True)
    command = [str(tool), "--hls-version", "5", "--segment-duration", "3", "--audio-track-id", "0"]
    if mode == "encrypted":
        command += ["--encryption-mode", "SAMPLE-AES", "--encryption-key", key.hex(),
                    "--encryption-iv-mode", "random", "--encryption-key-uri", "key.bin",
                    "--encryption-key-format", "identity"]
        (directory / "key.bin").write_bytes(key)
    command.append(str(source))
    completed = subprocess.run(command, cwd=directory, capture_output=True, text=True, check=True)
    commands.append({"mode": mode, "command": command, "stdout": completed.stdout, "stderr": completed.stderr})
    playlist = (directory / "stream.m3u8").read_text()
    if mode == "encrypted":
        assert "METHOD=SAMPLE-AES" in playlist and 'KEYFORMAT="identity"' in playlist
        assert len((directory / "key.bin").read_bytes()) == 16
    else:
        assert "#EXT-X-KEY" not in playlist
    # A one-variant master makes the source explicit and easy to inspect.
    (directory / "master.m3u8").write_text('#EXTM3U\n#EXT-X-VERSION:5\n#EXT-X-STREAM-INF:BANDWIDTH=8000000,RESOLUTION=1800x1000,CODECS="avc1.640028"\nstream.m3u8\n')
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root / "research/clearkey/Bento4", text=True).strip()
manifest = {"source": str(source), "sourceSHA256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "toolRepository": "https://github.com/axiomatic-systems/Bento4", "toolCommit": commit,
            "encryption": "SAMPLE-AES in MPEG-TS, identity key delivery (not whole-segment AES-128)",
            "testKeyHex": key.hex(), "commands": commands,
            "files": {str(p.relative_to(webroot)): hashlib.sha256(p.read_bytes()).hexdigest() for p in webroot.rglob("*") if p.is_file()}}
(root / "research/clearkey/media-generation.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print(webroot)
print((webroot / "encrypted/stream.m3u8").read_text())
