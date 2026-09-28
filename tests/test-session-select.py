#!/usr/bin/env python3
"""Switch to Desktop has to reach our leave path, and no one else's.

Steam looks up the exact name steamos-session-select. Console mode keeps that
file off the ordinary PATH and only shows it to the Steam it starts, so a real
gamescope login session keeps its own helper. These drive the script with a
fake cachy-console-exit, so nothing here leaves a real session.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "bin", "steamos-session-select")

FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        FAILURES.append(label)
        print(f"          got  {got!r}\n          want {want!r}")


EXIT = """#!/usr/bin/env bash
printf '%s\\n' "exit $*" >> "$STATE/sequence"
exit 0
"""

STEAM = """#!/usr/bin/env bash
printf '%s\\n' "steam $*" >> "$STATE/sequence"
exit 0
"""


def run_select(layout, extra_env=None):
    root = tempfile.mkdtemp(prefix="cachy-select-")
    state = os.path.join(root, "state")
    os.makedirs(state)
    env = dict(os.environ)
    env["STATE"] = state
    # Fake bin first, then a PATH with no user install, so a real
    # cachy-console-exit cannot hide a miss and readlink still works.
    env["PATH"] = os.pathsep.join([
        os.path.join(root, "bin"), "/usr/bin", "/bin",
    ])
    if extra_env:
        env.update(extra_env)

    if layout == "beside":
        bindir = os.path.join(root, "bin")
        os.makedirs(bindir)
        shutil.copy(SCRIPT, os.path.join(bindir, "steamos-session-select"))
        os.chmod(os.path.join(bindir, "steamos-session-select"), 0o755)
        with open(os.path.join(bindir, "cachy-console-exit"), "w") as fh:
            fh.write(EXIT)
        os.chmod(os.path.join(bindir, "cachy-console-exit"), 0o755)
        cmd = os.path.join(bindir, "steamos-session-select")
    elif layout == "lib":
        lib = os.path.join(root, "lib")
        bindir = os.path.join(root, "bin")
        os.makedirs(lib)
        os.makedirs(bindir)
        shutil.copy(SCRIPT, os.path.join(lib, "steamos-session-select"))
        os.chmod(os.path.join(lib, "steamos-session-select"), 0o755)
        with open(os.path.join(bindir, "cachy-console-exit"), "w") as fh:
            fh.write(EXIT)
        os.chmod(os.path.join(bindir, "cachy-console-exit"), 0o755)
        cmd = os.path.join(lib, "steamos-session-select")
    else:
        bindir = os.path.join(root, "bin")
        os.makedirs(bindir)
        shutil.copy(SCRIPT, os.path.join(bindir, "steamos-session-select"))
        os.chmod(os.path.join(bindir, "steamos-session-select"), 0o755)
        with open(os.path.join(bindir, "steam"), "w") as fh:
            fh.write(STEAM)
        os.chmod(os.path.join(bindir, "steam"), 0o755)
        cmd = os.path.join(bindir, "steamos-session-select")

    res = subprocess.run([cmd, "plasma"], env=env, text=True,
                         capture_output=True)
    sequence = []
    recorded = os.path.join(state, "sequence")
    if os.path.exists(recorded):
        with open(recorded) as fh:
            sequence = [line.rstrip("\n") for line in fh]
    shutil.rmtree(root, True)
    return res.returncode, sequence


print()
print("Switch to Desktop reaches the same leave path as the library tile")
code, seq = run_select("beside")
check("the helper next to the script is used", (code, seq), (0, ["exit plasma"]))

code, seq = run_select("lib")
check("a packaged helper in lib/ finds ../bin/cachy-console-exit",
      (code, seq), (0, ["exit plasma"]))

code, seq = run_select("missing")
check("a missing exit helper still asks Steam to quit",
      (code, seq), (0, ["steam -shutdown"]))

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
    sys.exit(1)
print("all passed")
