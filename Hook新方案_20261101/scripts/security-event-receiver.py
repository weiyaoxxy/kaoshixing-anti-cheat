#!/usr/bin/env python3
"""Start the explicitly local test receiver; this is not an exam production server."""

import argparse
import json
import os
from pathlib import Path
import signal
import stat
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from guardlib.receiver import ReceiptStore, ReferenceReceiver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--token-file", required=True, help="Private owner-only file, token never printed")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--ready-file")
    args = parser.parse_args()
    token_path = Path(args.token_file)
    info = token_path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        parser.error("token file must be an owned, non-symlink, private regular file")
    token = token_path.read_text().strip()
    store = ReceiptStore(args.directory, args.session_id)
    server = ReferenceReceiver(("127.0.0.1", args.port), store, token)
    ready = {"referenceServer": True, "productionExamServer": False,
             "endpoint": server.endpoint, "pid": os.getpid(), "sessionId": args.session_id}
    if args.ready_file:
        with open(args.ready_file, "x", encoding="utf-8") as stream:
            json.dump(ready, stream, ensure_ascii=False)
            stream.write("\n")
    print(json.dumps(ready), flush=True)
    def stop(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        store.close()


if __name__ == "__main__":
    main()
