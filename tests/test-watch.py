#!/usr/bin/env python3
"""Drive cachy-console-watch's state machine with fakes. No X11, no gamescope.

usage: ./test-watch.py [path-to-cachy-console-watch]

Defaults to the copy in ../bin, so a bare run exercises the working tree rather
than whatever happens to be installed.
"""

import importlib.machinery
import importlib.util
import os
import re
import sys
import types

DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "bin", "cachy-console-watch")
TARGET = sys.argv[1] if len(sys.argv) > 1 else DEFAULT

loader = importlib.machinery.SourceFileLoader("pw", TARGET)
spec = importlib.util.spec_from_loader("pw", loader)
pw = importlib.util.module_from_spec(spec)
loader.exec_module(pw)

BPM = {"id": "1", "classes": {"steam", "steamwebhelper"},
       "name": "Steam Big Picture Mode"}
DESKTOP = {"id": "2", "classes": {"steam", "steamwebhelper"}, "name": "Steam"}
GAME = {"id": "3", "classes": {"steam_app_1623730"}, "name": "Pal"}
OTHER = {"id": "4", "classes": {"firefox"}, "name": "Web"}
NOPROPS = {"id": "5", "classes": set(), "name": ""}
# gamescope's own window on the host: the title says Big Picture but the class
# is gamescope, so it must never be read as a request for another session.
GSWIN = {"id": "6", "classes": {"gamescope"}, "name": "Steam Big Picture Mode"}


class FakeXprop:
    """Each script entry is the set of windows mapped at that poll."""

    def __init__(self, script):
        self.script = [s if isinstance(s, list) else [s] for s in script]
        self.i = 0

    def _current(self):
        return self.script[self.i] if self.i < len(self.script) else []

    def client_list(self):
        return [w["id"] for w in self._current()]

    def active_window(self):
        wins = self._current()
        return wins[0]["id"] if wins else None

    def window(self, wid):
        for w in self._current():
            if w["id"] == wid:
                return w
        return None


class FakeSession:
    """Records what the loop asked for, and fakes gamescope's lifetime.

    `up_after` is how many polls gamescope takes to appear once started;
    `lifetime` is how many polls it then stays up. None means "never dies".
    """

    def __init__(self, connected=True, start_ok=True, up_after=1,
                 lifetime=None):
        self.actions = []
        self.started_on = []
        self.display = "HDMI-1"
        self._connected = connected
        self._start_ok = start_ok
        self._up_after = up_after
        self._lifetime = lifetime
        self._started_at = None
        self._alive = False
        self.clock = 0
        self.log_path = "/tmp/fake.log"

    def connected(self):
        return self._connected

    def refresh_target(self):
        return self.display

    def running(self):
        if self._started_at is None:
            return self._alive
        elapsed = self.clock - self._started_at
        if elapsed < self._up_after:
            return False
        if self._lifetime is not None and elapsed >= self._up_after + self._lifetime:
            return False
        return True

    def start(self):
        self.actions.append("start")
        self.started_on.append(self.display)
        if self._start_ok:
            self._started_at = self.clock
        return self._start_ok

    def restore_audio(self):
        self.actions.append("restore-audio")

    def relaunch_desktop_steam(self):
        self.actions.append("relaunch-steam")
        self._started_at = None
        self._alive = False


def run(script, **kw):
    """What the loop did, which is what almost every test here is about."""
    return run_session(script, **kw).actions


def run_session(script, connected=True, engage_polls=2, start_ok=True, up_after=1,
                lifetime=None, max_starts=3, start_window=300.0, polls=None,
                display="HDMI-1"):
    """The session itself, for the few tests that also care what was said."""
    xprop = FakeXprop(script)
    session = FakeSession(connected, start_ok, up_after, lifetime)
    session.display = display
    args = types.SimpleNamespace(
        interval=0, engage_polls=engage_polls,
        start_timeout=10, max_starts=max_starts,
        start_window=start_window)
    stopping = {"now": False}
    limit = polls if polls is not None else len(script)
    ticks = {"n": 0}

    def now():
        return float(ticks["n"])

    def sleep(_secs):
        ticks["n"] += 1
        session.clock = ticks["n"]
        xprop.i = min(ticks["n"], len(script) - 1) if script else 0
        if ticks["n"] >= limit:
            stopping["now"] = True

    said = []
    pw.run_loop(xprop, session, re.compile("big.?picture", re.I), args,
                stopping, sleep, now,
                announce=lambda summary, body: said.append((summary, body)))
    session.announced = said
    return session


FAILURES = 0


def check(name, got, want):
    global FAILURES
    ok = got == want
    if not ok:
        FAILURES += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"          got  {got}\n          want {want}")


print("starting a session:")

check("desktop only never starts anything",
      run([DESKTOP] * 8), [])

check("a game launched from the desktop never starts anything",
      run([GAME] * 8), [])

check("one Big Picture poll is not enough (debounce)",
      run([BPM, DESKTOP, DESKTOP, DESKTOP, DESKTOP]), [])

check("two Big Picture polls start a gamescope session",
      run([BPM] * 6, lifetime=None), ["start"])

check("chosen display switched off: stays on the desktop, never starts",
      run([BPM] * 10, connected=False), [])

check("no display saved: never starts, will not pick another screen",
      run([BPM] * 10, display=""), [])

check("window with no properties never starts anything",
      run([NOPROPS] * 8), [])

check("Big Picture behind an unrelated focused window still starts",
      run([[NOPROPS, BPM]] * 6), ["start"])

print()
print("gamescope's own window:")

# The regression this guards: gamescope's host window is titled "Steam Big
# Picture Mode". Reading that as Big Picture would start a session on top of
# the session that owns the window.
check("gamescope's own window is not mistaken for Big Picture",
      run([GSWIN] * 10), [])

print()
print("leaving and re-entering:")

# gamescope comes up after 1 poll and lives for 3, so the loop should notice it
# died and put the desktop client back. Leftover Big Picture after that is
# Steam restoring itself — not a new Steam-button press.
check("session ending relaunches the desktop Steam client",
      run([BPM] * 20, up_after=1, lifetime=3, polls=20),
      ["start", "restore-audio", "relaunch-steam"])

check("leftover Big Picture after exit does not start another session",
      run([BPM] * 24, up_after=1, lifetime=3, polls=24),
      ["start", "restore-audio", "relaunch-steam"])

# Real second press: Big Picture has to go away (desktop) and come back.
def bpm_roundtrip(sessions):
    seq = []
    for _ in range(sessions):
        seq += [BPM] * 8 + [DESKTOP] * 4
    return seq

check("a second Big Picture press after it has closed starts a second session",
      run(bpm_roundtrip(2), up_after=1, lifetime=3, polls=24),
      ["start", "restore-audio", "relaunch-steam",
       "start", "restore-audio", "relaunch-steam"])

check("--no-steam-relaunch equivalent: session end without relaunch is still IDLE",
      run([BPM] * 12, up_after=1, lifetime=3)[:1], ["start"])

print()
print("failure handling:")

# A start that fails must leave the loop in IDLE so it can try again, rather
# than waiting forever for a gamescope that was never launched.
retried = run([BPM] * 12, start_ok=False, engage_polls=2, max_starts=99)
check("a failed start is retried, never wedges",
      (set(retried), len(retried) >= 4), ({"start"}, True))

# gamescope never appearing must time out rather than hanging forever. With a
# 10-poll timeout over 30 polls there is room for several attempts.
timed_out = run([BPM] * 30, up_after=999, lifetime=None, polls=30,
                max_starts=99)
check("gamescope never appearing times out and retries",
      (set(timed_out), len(timed_out) >= 2), ({"start"}, True))

print()
print("loop protection:")

# Steam set to open in Big Picture would otherwise restart forever. After a
# session, leftover Big Picture is ignored, so persistent BPM is no longer a
# restart loop — throttle still applies when BPM closes and reopens.
check("repeated sessions are throttled by --max-starts",
      run(bpm_roundtrip(5), up_after=1, lifetime=1, max_starts=2, polls=60),
      ["start", "restore-audio", "relaunch-steam",
       "start", "restore-audio", "relaunch-steam"])

check("a wide --start-window still allows the configured number of starts",
      run(bpm_roundtrip(5), up_after=1, lifetime=1, max_starts=3, polls=60),
      ["start", "restore-audio", "relaunch-steam"] * 3)

print()
print("zombie detection:")

# The regression: an exited gamescope stays
# in /proc as our unreaped child, still reporting its name. Counting it kept the
# watcher in GAME forever and the desktop Steam client was never restored.
import subprocess as _sp
import time as _time

_zombie = _sp.Popen(["true"])
for _ in range(50):
    _time.sleep(0.02)
    if pw.proc_state(_zombie.pid) == "Z":
        break
check("an unreaped exited process is seen as a zombie",
      pw.proc_state(_zombie.pid), "Z")
check("gamescope_pids never includes a zombie",
      _zombie.pid in pw.gamescope_pids(), False)
_zombie.wait()
check("a reaped process has no state at all",
      pw.proc_state(_zombie.pid) in (None, "Z"), True)

check("a live process reports a non-zombie state",
      pw.proc_state(os.getpid()) not in (None, "Z"), True)

print()
print("handing the desktop client back to the wrapper:")


class FakePopen:
    """Records a launch instead of performing one."""

    calls = []

    def __init__(self, argv, **kwargs):
        FakePopen.calls.append((argv, kwargs))


def relaunch(**kwargs):
    FakePopen.calls.clear()
    real, pw.subprocess.Popen = pw.subprocess.Popen, FakePopen
    try:
        pw.Session("/opt/bin/cachy-console", "/opt/bin/cachy-console-display",
                   "HDMI-1", **kwargs).relaunch_desktop_steam()
    finally:
        pw.subprocess.Popen = real
    return list(FakePopen.calls)


# The watcher used to start Steam itself, with an extest preload nobody asked
# for and no idea what console mode had exported into Steam's environment. That
# knowledge lives in the wrapper, which also has to do this from its own exit
# path, so there is one implementation and the watcher calls it.
launched = relaunch()
check("the client is put back by the wrapper, not started here",
      [argv for argv, _ in launched],
      [["/opt/bin/cachy-console", "restart-steam"]])
check("and detached, so restarting this service cannot take it down again",
      launched[0][1].get("start_new_session"), True)
check("a dry run only says what it would do",
      relaunch(dry_run=True), [])
check("--no-steam-relaunch leaves Steam alone",
      relaunch(relaunch_steam=False), [])

print()
print("saying on screen what the journal already knew")
# The reason for all of this: with the projector off, the button leaves Big
# Picture on a desktop monitor, which is indistinguishable from console mode
# having opened on the wrong screen. A stand-down nobody can see is how that
# gets reported as a display bug three times over.
off = run_session([BPM] * 4, connected=False, display="HDMI-A-1")
check("a screen that is off is announced, not just logged",
      [s for s, _ in off.announced], ["Console mode is waiting for HDMI-A-1"])
check("and the notification names the screen and what to do about it",
      [("HDMI-A-1" in b, "Turn it on" in b) for _, b in off.announced],
      [(True, True)])
check("nothing was started on another screen",
      off.actions, [])

quiet = run_session([BPM] * 3)
check("a start that works says nothing on screen",
      quiet.announced, [])

# One per stand-down, not one per poll: stand_down already dedupes by reason,
# and the notification follows it rather than the loop.
insistent = run_session([BPM] * 12, connected=False)
check("a long wait still only notifies once",
      len(insistent.announced), 1)

nothing_saved = run_session([BPM] * 3, display="")
check("no saved screen is announced too, since nothing will ever start",
      [s for s, _ in nothing_saved.announced],
      ["Console mode has no screen saved"])

broken = run_session([BPM] * 3, start_ok=False)
check("a session that refuses to start says so on screen",
      [s for s, _ in broken.announced], ["Console mode could not start"])
check("and points at the log that has the reason",
      ["/tmp/fake.log" in b for _, b in broken.announced], [True])

print()
if FAILURES:
    print(f"{FAILURES} failure(s)")
    sys.exit(1)
print("all state machine tests passed")
