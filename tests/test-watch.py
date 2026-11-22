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

    def ask_close_games(self, games, family="steam"):
        self.actions.append("ask-close")
        self.asked = games
        self.asked_family = family
        return True

    def relaunch_desktop_steam(self):
        self.actions.append("relaunch-steam")
        self._started_at = None
        self._alive = False


def run(script, **kw):
    """What the loop did, which is what almost every test here is about."""
    return run_session(script, **kw).actions


class FakeGuide:
    """Fires a double-press on the listed clock ticks."""

    def __init__(self, ticks=()):
        self.ticks = set(ticks)

    def double_pressed(self, now):
        return now in self.ticks

    def close(self):
        pass


def run_session(script, connected=True, engage_polls=2, start_ok=True, up_after=1,
                lifetime=None, max_starts=3, start_window=300.0, polls=None,
                display="HDMI-1", guide=None):
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
                announce=lambda summary, body: said.append((summary, body)),
                guide=guide)
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

print()
print("Steam button without Big Picture:")
check("two presses start a session even when Steam is not focused",
      run([DESKTOP] * 8, guide=FakeGuide({2})), ["start"])
check("a desktop game is never closed unasked: the press asks instead",
      run([GAME] * 8, guide=FakeGuide({2})), ["ask-close"])
s = run_session([[GAME, DESKTOP]] * 8, guide=FakeGuide({2}))
check("and it is told which game, by appid and title",
      s.asked, [("1623730", "Pal")])
check("with the console display off it only says so, never asks",
      run_session([GAME] * 8, guide=FakeGuide({2}), connected=False).announced[:1],
      [("Close your game first",
        "Pal is running. Close it, then press the Steam button twice to "
        "open console mode.")])

class FamilyGuide(FakeGuide):
    def __init__(self, ticks, family):
        super().__init__(ticks)
        self.last_family = family


s = run_session([GAME] * 8, guide=FamilyGuide({2}, "playstation"))
check("the prompt shows the buttons of the pad that was pressed",
      s.asked_family, "playstation")
s = run_session([GAME] * 8, guide=FamilyGuide({2}, "xbox"), connected=False)
check("and the fallback names its guide button",
      s.announced[0][1].endswith("press the Xbox button twice to open console mode."),
      True)
check("the primary controller from Cachy Console wins over the device",
      pw.pad_family("xbox", {"PRIMARY_CONTROLLER": "steam"}), "steam")
check("PRIMARY_CONTROLLER=off falls back to the device",
      pw.pad_family("switch", {"PRIMARY_CONTROLLER": "off"}), "switch")
check("and with neither, Steam's own",
      pw.pad_family(None, {}), "steam")
check("no presses, no question",
      run([GAME] * 8), [])

print()
print("double-press timing:")
d = pw.DoublePress(window=0.55, debounce=0.04)
check("one press is not enough", d.feed(1.0), False)
check("a second press inside the window is", d.feed(1.4), True)
check("and the pair is consumed", d.feed(1.41), False)
d = pw.DoublePress(window=0.55, debounce=0.04)
d.feed(1.0)
check("the same press seen twice is ignored", d.feed(1.02), False)
d = pw.DoublePress(window=0.55, debounce=0.04)
d.feed(1.0)
check("a late second press is not a double", d.feed(1.7), False)

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
print("polling fast for the button without paying for it")


def idle_scans(polls, interval=0.2):
    """/proc scans made over `polls` idle polls on a clock that keeps real time."""
    session = FakeSession()
    scans = {"n": 0}
    real_running = session.running

    def counted():
        scans["n"] += 1
        return real_running()

    session.running = counted
    clock = {"t": 0.0, "polls": 0}
    stopping = {"now": False}

    def sleep(secs):
        clock["t"] += secs
        clock["polls"] += 1
        if clock["polls"] >= polls:
            stopping["now"] = True

    args = types.SimpleNamespace(interval=interval, engage_polls=2,
                                 start_timeout=10, max_starts=3,
                                 start_window=300.0)
    pw.run_loop(FakeXprop([OTHER]), session, re.compile("big.?picture", re.I),
                args, stopping, sleep, lambda: clock["t"],
                announce=lambda *_: None)
    return scans["n"]


# Five polls a second is what makes the Steam button feel immediate. The scan for
# a gamescope nobody told us about does not need to keep that pace.
check("ten seconds idle at 0.2s is fifty polls but only ten /proc scans",
      idle_scans(50), 10)


def hand_started(ends_at_poll, polls, interval=0.2):
    """A gamescope already running when the watcher looks, ending on its own."""
    session = FakeSession()
    session._alive = True
    clock = {"t": 0.0, "polls": 0}
    stopping = {"now": False}

    def sleep(secs):
        clock["t"] += secs
        clock["polls"] += 1
        if clock["polls"] == ends_at_poll:
            session._alive = False
        if clock["polls"] >= polls:
            stopping["now"] = True

    args = types.SimpleNamespace(interval=interval, engage_polls=2,
                                 start_timeout=10, max_starts=3,
                                 start_window=300.0)
    pw.run_loop(FakeXprop([OTHER]), session, re.compile("big.?picture", re.I),
                args, stopping, sleep, lambda: clock["t"],
                announce=lambda *_: None)
    return session.actions


check("a session started by hand is still tracked, and the desktop client "
      "comes back when it ends",
      hand_started(ends_at_poll=3, polls=8), ["restore-audio", "relaunch-steam"])

print()
print("guide buttons on every pad, not only Valve")

import struct as _struct
import tempfile as _tempfile

check("BTN_MODE is the bit the kernel names for a guide / PS / Home button",
      pw.BTN_MODE, 0x13C)
# 0x13C = 316, word 4 bit 60. Highest word first, so the first hex long.
btn_mode_cap = f"{1 << 60:x} 0 0 0 0"
check("a capabilities/key bitmap with only BTN_MODE is recognised",
      pw.keycap_has_bit(btn_mode_cap, pw.BTN_MODE), True)
check("and a keyboard bitmap without that bit is not",
      pw.keycap_has_bit("20000 0 0 0 0", pw.BTN_MODE), False)
check("vendor ids match with or without the leading zero sysfs prints",
      (pw.norm_vendor("054c"), pw.norm_vendor("045e"), pw.norm_vendor("28de")),
      ("54c", "45e", "28de"))


def fake_pad(root, name, vendor, cap=None, hid=False, events=b""):
    sysdir = os.path.join(root, "sys-hidraw" if hid else "sys-input")
    devdir = os.path.join(root, "hidraw" if hid else "input")
    node = os.path.join(sysdir, name, "device")
    os.makedirs(os.path.join(node, "id"), exist_ok=True)
    os.makedirs(devdir, exist_ok=True)
    with open(os.path.join(node, "id", "vendor"), "w") as fh:
        fh.write(vendor + "\n")
    if cap is not None:
        os.makedirs(os.path.join(node, "capabilities"), exist_ok=True)
        with open(os.path.join(node, "capabilities", "key"), "w") as fh:
            fh.write(cap + "\n")
    path = os.path.join(devdir, name)
    with open(path, "wb") as fh:
        fh.write(events)
    return path


def evdev_press():
    return _struct.pack(pw.EVENT_FORMAT, 0, 0, pw.EV_KEY, pw.BTN_MODE, 1)


with _tempfile.TemporaryDirectory() as tmp:
    fake_pad(tmp, "event0", "054c", cap=btn_mode_cap, events=evdev_press())
    fake_pad(tmp, "event1", "045e", cap=btn_mode_cap, events=evdev_press())
    fake_pad(tmp, "event2", "0001", cap="20000 0 0 0 0")
    fake_pad(tmp, "hidraw0", "28de", hid=True, events=b"\x00" * 16)
    fake_pad(tmp, "hidraw1", "054c", hid=True, events=b"\xff" * 16)
    guide = pw.GuideButtons(
        evdev_root=os.path.join(tmp, "input"),
        hidraw_root=os.path.join(tmp, "hidraw"),
        sys_input=os.path.join(tmp, "sys-input"),
        sys_hidraw=os.path.join(tmp, "sys-hidraw"),
    )
    try:
        watched = {os.path.basename(p) for p in guide._fds}
        check("PlayStation and Xbox evdev nodes are watched",
              {"event0", "event1"} <= watched, True)
        check("a keyboard without BTN_MODE is left alone",
              "event2" in watched, False)
        check("Valve hidraw is still the grabbed-Steam-Controller path",
              "hidraw0" in watched, True)
        check("and a DualSense hidraw is not parsed as a Steam logo",
              "hidraw1" in watched, False)
        check("one PS-button press is not a double",
              guide.double_pressed(1.0), False)
        # The regular files were consumed on the first read. A second press
        # is fed the same way the real loop feeds a later evdev edge.
        check("two presses inside the window start console mode",
              guide._presses.feed(1.2), True)
    finally:
        guide.close()

print()
print("only the primary controller starts console mode:")
check("by default only the primary controller's kind counts",
      pw.trigger_families({"PRIMARY_CONTROLLER": "steam"}), {"steam"})
check("GUIDE_PRIMARY_ONLY=off lets any pad do it",
      pw.trigger_families({"PRIMARY_CONTROLLER": "steam",
                           "GUIDE_PRIMARY_ONLY": "off"}), None)
check("with no primary controller picked, any pad does",
      (pw.trigger_families({}), pw.trigger_families({"PRIMARY_CONTROLLER": "off"})),
      (None, None))
with _tempfile.TemporaryDirectory() as tmp:
    fake_pad(tmp, "event0", "045e", cap=btn_mode_cap,
             events=evdev_press() + evdev_press())
    guide = pw.GuideButtons(
        evdev_root=os.path.join(tmp, "input"),
        hidraw_root=os.path.join(tmp, "hidraw"),
        sys_input=os.path.join(tmp, "sys-input"),
        sys_hidraw=os.path.join(tmp, "sys-hidraw"),
        families={"steam"})
    try:
        guide.double_pressed(1.0)
        check("an Xbox pad at the desk does not count toward a double press",
              guide._presses.times, [])
    finally:
        guide.close()
with _tempfile.TemporaryDirectory() as tmp:
    fake_pad(tmp, "event0", "045e", cap=btn_mode_cap, events=evdev_press())
    guide = pw.GuideButtons(
        evdev_root=os.path.join(tmp, "input"),
        hidraw_root=os.path.join(tmp, "hidraw"),
        sys_input=os.path.join(tmp, "sys-input"),
        sys_hidraw=os.path.join(tmp, "sys-hidraw"),
        families={"xbox"})
    try:
        guide.double_pressed(1.0)
        check("while the primary kind still does",
              len(guide._presses.times), 1)
    finally:
        guide.close()

print()
print("console mode runs in a unit of its own:")
_rt = _tempfile.mkdtemp()
_saved = os.environ.get("XDG_RUNTIME_DIR")
os.environ["XDG_RUNTIME_DIR"] = _rt
check("without a reachable user manager it runs plainly, as before",
      pw.in_own_scope(["cachy-console"]), ["cachy-console"])
os.makedirs(os.path.join(_rt, "systemd"))
open(os.path.join(_rt, "systemd", "private"), "w").close()
_argv = pw.in_own_scope(["cachy-console", "--display", "HDMI-A-1"])
if pw.shutil.which("systemd-run"):
    check("with one, it is a transient scope that execs the session",
          (_argv[:5], _argv[-4:]),
          (["systemd-run", "--user", "--quiet", "--collect", "--scope"],
           ["--", "cachy-console", "--display", "HDMI-A-1"]))
    check("named so it can be found",
          any(a.startswith("--unit=cachy-console-session-") for a in _argv), True)
if _saved is None:
    del os.environ["XDG_RUNTIME_DIR"]
else:
    os.environ["XDG_RUNTIME_DIR"] = _saved

print()
print("only a real gamescope counts as a session:")
_fake_dir = _tempfile.mkdtemp()
_fake = os.path.join(_fake_dir, "gamescope")
with open(_fake, "w") as _fh:
    _fh.write("#!/bin/bash\nsleep 5\n")
os.chmod(_fake, 0o755)
import subprocess as _sp
_p = _sp.Popen([_fake])
import time as _time
_time.sleep(0.3)
check("a script named gamescope is not taken for a session",
      _p.pid in pw.gamescope_pids(), False)
_p.kill()
_p.wait()

print()
print("the running kernel's modules deleted by an update:")
_mods = _tempfile.mkdtemp()
_said = []
_unclaimed = {}
_k = pw.KernelModules(announce=lambda s, b: _said.append((s, b)), root=_mods,
                      release="9.9.9-test", scan=lambda: dict(_unclaimed))
_k.check(0.0)
check("a pending restart is announced", [t for t, _ in _said], ["Restart needed"])
check("in plain words", "restart" in _said[0][1] and "kernel" not in _said[0][1], True)
_k.check(1.0)
_k.check(500.0)
check("only once, however long it stays that way", len(_said), 1)

_unclaimed["/sys/hid/0003:054C:0CE6.0002"] = \
    "Sony Interactive Entertainment DualSense Wireless Controller"
_k.check(502.0)
check("a pad still probing is not reported yet", len(_said), 1)
_k.check(507.0)
check("a pad left with no driver is reported by name",
      _said[-1][0], "Restart to use your PS5 controller")
_k.check(530.0)
check("once per plug-in", len(_said), 2)
_unclaimed.clear()
_k.check(533.0)
_unclaimed["/sys/hid/0003:054C:0CE6.0003"] = \
    "Sony Interactive Entertainment DualSense Wireless Controller"
_k.check(536.0)
_k.check(541.0)
check("and again when it is plugged in again", len(_said), 3)
_unclaimed.clear()
_unclaimed["/sys/usb/1-4:1.0"] = "Some Gadget"
_k.check(544.0)
_k.check(549.0)
check("anything else gets a general title",
      _said[-1][0], "Restart to use what you plugged in")

_said.clear()
_unclaimed.clear()
_unclaimed["/sys/hid/already"] = "Old Pad"
_k3 = pw.KernelModules(announce=lambda s, b: _said.append(s), root=_mods,
                       release="8.8.8-test", scan=lambda: dict(_unclaimed))
_k3.check(0.0)
_k3.check(10.0)
check("what was already unclaimed is covered by the first message", _said,
      ["Restart needed"])

_said.clear()
os.mkdir(os.path.join(_mods, "9.9.9-test"))
_unclaimed["/sys/hid/x"] = "Sony Interactive Entertainment DualSense Wireless Controller"
_k2 = pw.KernelModules(announce=lambda s, b: _said.append(s), root=_mods,
                       release="9.9.9-test", scan=lambda: dict(_unclaimed))
_k2.check(0.0)
_k2.check(10.0)
check("with the kernel's modules present nothing is ever said", _said, [])

print()
print("finding devices left without a driver:")
_sys = _tempfile.mkdtemp()
_hid = os.path.join(_sys, "hid"); _usb = os.path.join(_sys, "usb")
def _mk(path, files, driver=False):
    os.makedirs(path, exist_ok=True)
    for k, v in files.items():
        with open(os.path.join(path, k), "w") as fh:
            fh.write(v)
    if driver:
        os.makedirs(os.path.join(path, "driver"), exist_ok=True)
_mk(os.path.join(_hid, "0003:054C:0CE6.0001"),
    {"uevent": "HID_ID=0003:0000054C:00000CE6\nHID_NAME=Sony Interactive "
               "Entertainment DualSense Wireless Controller\n"})
_mk(os.path.join(_hid, "0003:28DE:1304.0002"),
    {"uevent": "HID_NAME=Valve Software Steam Controller Puck\n"}, driver=True)
_mk(os.path.join(_usb, "1-3"), {"product": "DualSense Wireless Controller\n"})
_mk(os.path.join(_usb, "1-3:1.0"), {"bInterfaceClass": "01\n"})
_mk(os.path.join(_usb, "1-3:1.3"), {"bInterfaceClass": "03\n"}, driver=True)
_mk(os.path.join(_usb, "5-1"), {"product": "Wooting 80HE\n"})
_mk(os.path.join(_usb, "5-1:1.2"), {"bInterfaceClass": "03\n", "authorized": "0\n"})
_found = pw.stranded_devices(_hid, _usb)
check("the DualSense with no HID driver is found, nothing else",
      sorted(_found.values()),
      ["Sony Interactive Entertainment DualSense Wireless Controller"])
check("and called a PS5 controller", pw.friendly_name(list(_found.values())[0]),
      "PS5 controller")

print()
if FAILURES:
    print(f"{FAILURES} failure(s)")
    sys.exit(1)
print("all state machine tests passed")
