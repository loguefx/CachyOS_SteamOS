#!/usr/bin/env python3
"""The way out of console mode, which has to work the first time.

Steam hides its own exits whenever it sees gamescope, so this tile is the only
way back to the desktop from the couch. It used to signal gamescope and wait:
gamescope ignored SIGTERM, sat there for the whole grace period and then had to
be killed, so the screen did not change for ten seconds and Steam came back up
convinced it had crashed. Now Steam is asked to close itself first -- it is
gamescope's primary child, so the session follows it out -- and the signals are
only the fallback for a Steam that will not answer.

The other half is what happens with no session to end. The Steam button does not
launch anything; a double press asks the running client to switch to Big Picture,
so whenever the watcher is not there to turn that into a session, Big Picture
opens on the desktop and on whichever screen the desktop client felt like. The
tile is in the same library, and answering "console mode is not running" left the
user in Big Picture with no way out.

These tests drive the script with a fake Steam, a fake pgrep and a /proc built by
hand, so nothing here shuts down a real client or signals a real session. The
stand-in for gamescope is a real process, because the escalation is all about
what a process does with the signals it is sent -- including ignoring them.
"""

import atexit
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "bin", "cachy-console-exit")

FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        FAILURES.append(label)
        print(f"          got  {got!r}\n          want {want!r}")


# Records how it was called. With "steam-answers" it also models the client going
# away, and gamescope with it, which is what closing Steam really does.
STEAM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STATE/steam-argv"
if [[ "${1-}" == -shutdown && -f "$STATE/steam-answers" ]]; then
    kill -KILL "$(< "$STATE/gamescope-pid")" 2>/dev/null || true
fi
exit 0
"""

# Only `pgrep -x steam` reaches this: the script reads /proc itself to find
# gamescope, because gamescope runs under the name gamescope-wl.
PGREP = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STATE/pgrep-argv"
[[ -f "$STATE/steam-running" ]]
"""


class World:
    """A fake /proc, a fake Steam, and optionally something to stand in for
    gamescope."""

    def __init__(self, session=True, steam_running=True, steam_answers=True,
                 ignores_term=False, console=True):
        self.dir = tempfile.mkdtemp(prefix="cachy-exit-")
        atexit.register(shutil.rmtree, self.dir, True)
        self.state = os.path.join(self.dir, "state")
        self.proc = os.path.join(self.dir, "proc")
        self.bin = os.path.join(self.dir, "bin")
        for d in (self.state, self.proc, self.bin):
            os.makedirs(d)

        for name, body in (("steam", STEAM), ("pgrep", PGREP)):
            path = os.path.join(self.bin, name)
            with open(path, "w") as fh:
                fh.write(body)
            os.chmod(path, 0o755)

        if steam_running:
            open(os.path.join(self.state, "steam-running"), "w").close()
        if steam_answers:
            open(os.path.join(self.state, "steam-answers"), "w").close()

        self.child = None
        if session:
            # A real process, so the signals the script sends land somewhere.
            # `trap "" TERM` is the behaviour that caused the ten-second exit.
            body = 'trap "" TERM; sleep 60' if ignores_term else "sleep 60"
            self.child = subprocess.Popen(["bash", "-c", body],
                                          stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
            atexit.register(self.cleanup)
            self.fake_proc_entry(self.child.pid, console=console)
            with open(os.path.join(self.state, "gamescope-pid"), "w") as fh:
                fh.write(str(self.child.pid))

    def fake_proc_entry(self, pid, console=True):
        d = os.path.join(self.proc, str(pid))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "comm"), "w") as fh:
            fh.write("gamescope-wl\n")
        with open(os.path.join(d, "status"), "w") as fh:
            fh.write("Name:\tgamescope-wl\nState:\tS (sleeping)\nPPid:\t1\n")
        argv = ["gamescope", "-W", "1920", "-H", "1080", "--backend", "sdl"]
        # Console mode is the gamescope that launched Big Picture. Without that,
        # it is somebody else's gamescope and none of our business.
        argv += ["--steam", "--", "env", "steam", "-gamepadui"] if console \
            else ["--", "env", "vkcube"]
        with open(os.path.join(d, "cmdline"), "wb") as fh:
            fh.write(b"\0".join(a.encode() for a in argv) + b"\0")

    def cleanup(self):
        if self.child and self.child.poll() is None:
            self.child.kill()

    def run(self, *args):
        env = dict(os.environ)
        env["PATH"] = self.bin + os.pathsep + env["PATH"]
        env["STATE"] = self.state
        env["CACHY_CONSOLE_PROC"] = self.proc
        # Short enough that the tests do not sit through the real waits, long
        # enough that each step is still distinguishable.
        env["CACHY_CONSOLE_QUIT"] = "2"
        env["CACHY_CONSOLE_GRACE"] = "2"
        return subprocess.run([SCRIPT, *args], env=env, text=True,
                              capture_output=True)

    def lines(self, name, expect=1, timeout=6):
        """What a fake recorded, once it has had the chance to record it.

        The script hands the work to a detached helper and returns, because Steam
        kills the tile's process group on its way out, so nothing it records is
        there the moment the script exits.
        """
        path = os.path.join(self.state, name)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with open(path) as fh:
                    got = [l.strip() for l in fh if l.strip()]
                if len(got) >= expect:
                    return got
            except FileNotFoundError:
                pass
            time.sleep(0.1)
        try:
            with open(path) as fh:
                return [l.strip() for l in fh if l.strip()]
        except FileNotFoundError:
            return []

    def settled(self, name, wait=2.0):
        """What a fake recorded after being given the chance to record anything,
        for the cases where the right answer is nothing at all."""
        time.sleep(wait)
        return self.lines(name, timeout=0)

    def wait_for_exit(self, timeout):
        """Whether the stand-in gamescope is gone within timeout seconds."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.child.poll() is not None:
                return True
            time.sleep(0.1)
        return self.child.poll() is not None

    def died_of(self):
        """The signal that ended it, or None while it is still running."""
        code = self.child.poll()
        if code is None:
            return None
        return -code if code < 0 else code


print("closing a session the polite way:")

# Deaf to SIGTERM, so the fallback could only end this by SIGKILL, and that is
# 0.4 + QUIT + GRACE away. Ending sooner is Steam closing the session.
w = World(ignores_term=True)
proc = w.run()
check("it says which session it is ending", "gamescope pid" in proc.stderr, True)
check("the tile returns at once rather than blocking Steam", proc.returncode, 0)
check("Steam is asked to close itself", "-shutdown" in w.lines("steam-argv"), True)
check("and it is asked once", w.lines("steam-argv"), ["-shutdown"])
check("the session ends without waiting out the fallback",
      w.wait_for_exit(3), True)


print()
print("a Steam that will not answer:")

# The real failure: gamescope ignoring SIGTERM. Steam is asked, says nothing, and
# the fallback has to finish the job rather than leave the user on a dead screen.
w = World(steam_answers=False, ignores_term=True)
w.run()
check("Steam is still asked first", "-shutdown" in w.lines("steam-argv"), True)
check("and a session that ignores both is killed",
      w.wait_for_exit(12), True)
check("by SIGKILL, since SIGTERM was ignored", w.died_of(), signal.SIGKILL)

# One that does answer SIGTERM never reaches SIGKILL, so it is not killed
# mid-write when a signal would have done.
w = World(steam_answers=False, ignores_term=False)
w.run()
check("a session that answers SIGTERM is not killed", w.wait_for_exit(8), True)
check("it stops on the signal it was sent", w.died_of(), signal.SIGTERM)


print()
print("with no session to end:")

w = World(session=False, steam_running=True)
proc = w.run()
check("Big Picture is closed instead of doing nothing",
      w.lines("steam-argv"), ["steam://close/bigpicture"])
check("and it says so", "leave Big Picture" in proc.stderr, True)
check("Steam itself is left running", "-shutdown" in w.lines("steam-argv"), False)

w = World(session=False, steam_running=False)
proc = w.run()
check("no client means nothing to ask", w.settled("steam-argv"), [])
check("and it says there is nothing to do",
      "nothing to do" in proc.stderr, True)
check("which is not an error the caller has to handle", proc.returncode, 0)


print()
print("whose session it is:")

# Somebody else's gamescope is not console mode. Ending it would take down
# whatever they were running.
w = World(console=False)
proc = w.run()
check("and Steam is not asked to shut down",
      "-shutdown" in w.settled("steam-argv"), False)
check("a gamescope that did not start Big Picture is left alone",
      w.child.poll(), None)
# It is still Big Picture the user wants to be out of, and there is no session
# here to end, so the fallback is the right answer rather than nothing.
check("Big Picture is still closed for them",
      w.lines("steam-argv"), ["steam://close/bigpicture"])

w = World()
check("--running reports a session", w.run("--running").returncode, 0)
w = World(session=False)
check("and reports none when there is none", w.run("--running").returncode, 1)


print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s)")
    sys.exit(1)
print("all exit tests passed")
