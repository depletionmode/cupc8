#!/usr/bin/env python3
"""One bounded Freerouting trial against the saved main-board salt-9 DSN.

This is deliberately separate from kicadgen's multi-attempt router. It does
not import the session or claim board closure; use main_ses_salvage.py for that.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time


SALT9_SHA256 = "10cbd97dc043be4d4b86715b286c6924763b697cb44ab191190d82dd30072316"
ACTIVE_ROUTE_DIR = Path("/home/depmod/code/cupc8/build/hw/main/route-parallel")


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def active_root_routers():
    """Detect the original ten jobs without querying or signaling them."""
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            argv = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except (OSError, PermissionError):
            continue
        if str(ACTIVE_ROUTE_DIR) in argv and re.search(r"route-\d+\.dsn", argv) and "freerouting" in argv:
            found.append(int(entry.name))
    return sorted(found)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", type=Path, required=True, help="saved route-9.dsn, SHA verified")
    parser.add_argument("--out", type=Path, required=True, help="new, isolated output directory")
    parser.add_argument("--timeout", type=int, default=150 * 60, help="single-job wall cap in seconds")
    args = parser.parse_args()
    source = args.dsn.resolve(strict=True)
    output = args.out.resolve()
    if source.is_dir() or digest(source) != SALT9_SHA256:
        parser.error("DSN is not the saved salt-9 input with expected SHA-256")
    if args.timeout < 60 or args.timeout > 180 * 60:
        parser.error("timeout must be between 60 and 10800 seconds")
    if output == ACTIVE_ROUTE_DIR or ACTIVE_ROUTE_DIR in output.parents:
        parser.error("output must not be inside the root route directory")
    if output.exists():
        parser.error("output already exists; use a fresh directory")
    running = active_root_routers()
    if running:
        parser.error(f"root Freerouting jobs still active (PIDs {running}); wait for current batch")

    output.mkdir(parents=True)
    local_dsn = output / "route-9.dsn"
    session = output / "route-9.ses"
    log = output / "freerouting.log"
    shutil.copyfile(source, local_dsn)
    command = ["freerouting", "-de", str(local_dsn), "-do", str(session),
               "-mp", "30", "-mt", "0", "--router.optimizer.enabled=false",
               "--gui.enabled=false"]
    env = os.environ.copy()
    env["JAVA_TOOL_OPTIONS"] = "-Djava.awt.headless=true -Xmx1g"
    start = time.monotonic()
    timed_out = False
    with open(log, "wb") as stream:
        proc = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                env=env, start_new_session=True)
        try:
            returncode = proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                returncode = proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                returncode = proc.wait()
    result = {
        "input_sha256": digest(local_dsn),
        "command": command,
        "optimizer_enabled": False,
        "intermediate_session_checkpoint": False,
        "timeout_seconds": args.timeout,
        "elapsed_seconds": round(time.monotonic() - start, 1),
        "timed_out": timed_out,
        "returncode": returncode,
        "log_sha256": digest(log),
        "session_sha256": digest(session) if session.exists() else None,
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if returncode == 0 and session.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
