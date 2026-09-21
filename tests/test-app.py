#!/usr/bin/env python3
"""Tests for cachy-console-app, the wrapper library tiles are launched through.

Two decisions in it are worth pinning down, because both failure modes are
silent and land on the user as "the tile is broken".

Getting the single-instance sweep wrong is destructive: match too widely and it
quits something the user was using, match too narrowly and the launch is a
secondary instance that exits at once. Getting the close detection wrong is the
other half: quit too eagerly and the application is killed while it is still
starting, quit never and it survives with no window, holding its lock and
keeping Steam's tile stuck on "Stop".

Nothing here starts a process or talks to an X server; /proc is a directory of
fakes and the window lists are strings captured from a real gamescope session.
"""

import importlib.machinery
import importlib.util
import os
import signal
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "bin", "cachy-console-app")
loader = importlib.machinery.SourceFileLoader("cca_app", TARGET)
spec = importlib.util.spec_from_loader("cca_app", loader)
app = importlib.util.module_from_spec(spec)
loader.exec_module(app)

FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"        got  = {got!r}")
        print(f"        want = {want!r}")
        FAILURES.append(label)


# ---- reading what xprop says --------------------------------------------

# Captured from a live gamescope session; ids come back in decimal there.
GAMESCOPE_LIST = "GAMESCOPE_FOCUSABLE_WINDOWS(CARDINAL) = 4194308, 4194308, 1779245\n"
GAMESCOPE_EMPTY = "GAMESCOPE_FOCUSABLE_WINDOWS(CARDINAL) = \n"
GAMESCOPE_ABSENT = "GAMESCOPE_FOCUSABLE_WINDOWS:  no such atom on any window.\n"
DESKTOP_LIST = "_NET_CLIENT_LIST(WINDOW): window id # 0x1e00035, 0x1400005\n"
CLASS_LINE = 'WM_CLASS(STRING) = "discord", "discord"\n'
PID_LINE = "_NET_WM_PID(CARDINAL) = 1723061\n"
MISSING = "WM_CLASS:  not found.\n"

print("reading xprop output:")
check("gamescope's decimal ids are read", app.numbers(GAMESCOPE_LIST),
      [4194308, 4194308, 1779245])
check("the desktop's hex ids are read", app.numbers(DESKTOP_LIST),
      [0x1e00035, 0x1400005])
check("an empty list is empty, not an error", app.numbers(GAMESCOPE_EMPTY), [])
check("a window class is lowercased", app.strings(CLASS_LINE), {"discord"})
check("a pid is read", app.numbers(PID_LINE), [1723061])

# An application that has just hidden its last window leaves the property in
# place and empty. Reading that as "absent" would fall through to the desktop
# atom and lose track of the session entirely.
check("an empty property still counts as present",
      app.prop_exists(GAMESCOPE_EMPTY), True)
check("a missing atom does not", app.prop_exists(GAMESCOPE_ABSENT), False)
check("a missing property does not", app.prop_exists(MISSING), False)
check("no output at all does not", app.prop_exists(None), False)


class FakeXprop:
    """Stands in for the xprop binary, one canned answer per property."""

    def __init__(self, props, display_gone=False):
        self.props = props
        self.display_gone = display_gone
        self.calls = 0

    def __call__(self, argv, timeout=5):
        self.calls += 1
        if self.display_gone:
            return None
        if argv[3] == "-root":
            return self.props.get(argv[4])
        return self.props.get((argv[4], argv[5]))


def windows_with(props, display_gone=False):
    """A Windows reading from canned xprop output instead of an X server."""
    fake = FakeXprop(props, display_gone)
    app.run = fake
    return app.Windows(":1"), fake


print()
print("finding the window list:")
windows, fake = windows_with({app.GAMESCOPE_WINDOW_LIST: GAMESCOPE_LIST})
check("gamescope's repeated ids are counted once", windows.listed(),
      [4194308, 1779245])
check("and the atom is remembered", windows.atom, app.GAMESCOPE_WINDOW_LIST)

windows, _ = windows_with({app.GAMESCOPE_WINDOW_LIST: GAMESCOPE_ABSENT,
                           app.DESKTOP_WINDOW_LIST: DESKTOP_LIST})
check("a desktop falls back to the ordinary client list", windows.listed(),
      [0x1e00035, 0x1400005])

windows, _ = windows_with({}, display_gone=True)
check("an unreachable X server is None, not an empty screen",
      windows.listed(), None)

print()
print("whose window is it:")
check("a pid in our tree is ours",
      app.window_is_ours(4242, set(), {1, 4242}, {"discord"}), True)
check("a matching class is ours when the pid is not ours",
      app.window_is_ours(99, {"discord"}, {1}, {"discord"}), True)
check("a window with neither is someone else's",
      app.window_is_ours(99, {"steamwebhelper"}, {1}, {"discord"}), False)
# Big Picture is on the same display the whole time; counting it as the
# application's window would mean never noticing the application had closed.
check("Steam's own window is not ours",
      app.window_is_ours(None, {"steamwebhelper", "steam"}, {1}, {"discord"}),
      False)
check("a window that reports no pid at all can still match by class",
      app.window_is_ours(None, {"discord"}, {1}, {"discord"}), True)

windows, fake = windows_with({
    app.GAMESCOPE_WINDOW_LIST: GAMESCOPE_LIST,
    ("4194308", "_NET_WM_PID"): "_NET_WM_PID(CARDINAL) = 4242\n",
    ("4194308", "WM_CLASS"): CLASS_LINE,
    ("1779245", "_NET_WM_PID"): "_NET_WM_PID(CARDINAL) = 777\n",
    ("1779245", "WM_CLASS"): 'WM_CLASS(STRING) = "steamwebhelper", "steam"\n',
})
check("only our window is counted among Steam's",
      app.count_ours(windows, {4242}, {"discord"}), 1)
after_first = fake.calls
app.count_ours(windows, {4242}, {"discord"})
check("a window's owner is read once and remembered",
      fake.calls - after_first, 1)


# ---- which processes are already running --------------------------------

def fake_proc(entries):
    """A /proc with the given {pid: (comm, cmdline, ppid)}."""
    root = tempfile.mkdtemp()
    for pid, (comm, cmdline, ppid) in entries.items():
        where = os.path.join(root, str(pid))
        os.makedirs(where)
        with open(os.path.join(where, "comm"), "w") as fh:
            fh.write(comm + "\n")
        with open(os.path.join(where, "cmdline"), "w") as fh:
            fh.write("\0".join(cmdline.split(" ")) + "\0")
        with open(os.path.join(where, "status"), "w") as fh:
            fh.write(f"Name:\t{comm}\nPPid:\t{ppid}\n")
    # Something that is not a pid at all, which /proc is full of.
    os.makedirs(os.path.join(root, "self"), exist_ok=True)
    return root


# The shape a running Discord actually has: a launcher script that has exec'd a
# binary with a different name, plus a crowd of helpers sharing that name.
DISCORD_PROC = fake_proc({
    1723061: ("Discord", "/home/u/.config/discord/app-1.0.158/Discord --url --", 1),
    1723064: ("Discord", "/home/u/.config/discord/app-1.0.158/Discord --type=zygote", 1723061),
    1723120: ("Discord", "/home/u/.config/discord/app-1.0.158/Discord --type=gpu-process", 1723061),
    1723085: ("chrome_crashpad", "/home/u/.config/discord/app-1.0.158/chrome_crashpad_handler", 1723061),
    9001: ("steam", "/usr/bin/steam -gamepadui", 1),
})

print()
print("finding a copy that is already running:")
check("the launcher script's name finds the binary it execs into",
      app.instance_names("/usr/bin/discord"), {"discord"})
check("comm is matched without case", app.comm_matches("Discord", {"discord"}), True)
check("an unrelated process is not", app.comm_matches("steam", {"discord"}), False)
# /proc/PID/comm is cut at 15 characters, so a long name can only match by its
# prefix -- otherwise a program like chrome_crashpad_handler never matches.
check("a name too long for comm matches on its prefix",
      app.comm_matches("chrome_crashpad", {"chrome_crashpad_handler"}), True)
check("and a short comm is still compared whole",
      app.comm_matches("chrome", {"chrome_crashpad_handler"}), False)

check("only the main process counts as a running copy",
      app.running_instances({"discord"}, proc=DISCORD_PROC), [1723061])
check("a helper process is recognised by its --type",
      app.is_helper("/home/u/Discord --type=zygote"), True)
check("the main process is not, despite the same binary",
      app.is_helper("/home/u/Discord --url --"), False)
check("we never count ourselves",
      app.running_instances({"discord"}, ignore={1723061}, proc=DISCORD_PROC), [])
check("nothing running means nothing to quit",
      app.running_instances({"slack"}, proc=DISCORD_PROC), [])

check("the process tree below the launcher is ours",
      app.descendants(1723061, proc=DISCORD_PROC),
      {1723061, 1723064, 1723120, 1723085})
check("and a sibling process is not",
      9001 in app.descendants(1723061, proc=DISCORD_PROC), False)


# ---- quitting it ---------------------------------------------------------

class FakeProcesses:
    """Processes that die on SIGTERM after a given number of polls."""

    def __init__(self, dies_after=0, stubborn=()):
        self.dies_after = dies_after
        self.stubborn = set(stubborn)
        self.signals = []
        self.polls = {}
        self.killed = set()

    def send(self, pid, sig):
        self.signals.append((pid, sig))
        if sig == signal.SIGKILL:
            self.killed.add(pid)

    def alive(self, pid):
        if pid in self.killed:
            return False
        if pid in self.stubborn:
            return True
        if not any(p == pid for p, _ in self.signals):
            return True
        self.polls[pid] = self.polls.get(pid, 0) + 1
        return self.polls[pid] <= self.dies_after


print()
print("quitting what is in the way:")
procs = FakeProcesses(dies_after=0)
ticks = []
check("a polite quit is enough for an application that listens",
      app.stop([1723061], grace=15, sleep=ticks.append,
               send=procs.send, alive=procs.alive), True)
check("and it is asked with SIGTERM", procs.signals, [(1723061, signal.SIGTERM)])
check("nothing is killed", procs.killed, set())

procs = FakeProcesses(stubborn=[42])
check("something wedged is killed in the end",
      app.stop([42], grace=1, sleep=lambda _s: None,
               send=procs.send, alive=procs.alive), False)
check("after being asked first",
      procs.signals, [(42, signal.SIGTERM), (42, signal.SIGKILL)])

procs = FakeProcesses()
check("a process that is already gone is not signalled",
      app.stop([7], grace=1, sleep=lambda _s: None,
               send=procs.send, alive=lambda _p: False), True)
check("nothing was sent", procs.signals, [])


# ---- deciding the last window has gone -----------------------------------

print()
print("deciding the application has closed:")
watch = app.CloseWatch(grace=4.0)
# Discord shows a splash, checks for updates and only then opens its window.
# Quitting during that would look exactly like the crash this prevents.
check("no window before the first one has ever appeared is startup, not a close",
      [watch.step(False, t) for t in (0, 10, 60, 600)], [False] * 4)
check("and the watch is still unarmed", watch.seen, False)

watch = app.CloseWatch(grace=4.0)
check("a window appearing arms it", watch.step(True, 0), False)
check("losing it is not instantly a close", watch.step(False, 1), False)
check("nor is it before the grace period is up", watch.step(False, 4), False)
check("but staying gone past it is", watch.step(False, 5.1), True)

watch = app.CloseWatch(grace=4.0)
watch.step(True, 0)
watch.step(False, 1)
# A window is destroyed and remade when it changes fullscreen state, which is a
# blink, not a close.
check("a window that comes straight back is not a close",
      watch.step(True, 2), False)
check("and the clock restarts from there", watch.step(False, 3), False)
check("so the old disappearance does not count", watch.step(False, 6), False)
check("only the new one does", watch.step(False, 7.5), True)


# ---- the command line Steam hands us -------------------------------------

print()
print("splitting our options from the program:")
# Steam expands the tile's launch options into: cachy-console-app -- /usr/bin/discord
check("everything after -- is the program",
      app.split_command(["--", "/usr/bin/discord"]), ([], ["/usr/bin/discord"]))
check("our own options stay on our side",
      app.split_command(["--close-grace", "2", "--", "/usr/bin/discord", "--url"]),
      (["--close-grace", "2"], ["/usr/bin/discord", "--url"]))
check("without a separator it is all the program",
      app.split_command(["/usr/bin/discord"]), ([], ["/usr/bin/discord"]))
# The program's own long options must not be eaten as ours.
check("only the first separator splits",
      app.split_command(["--", "/usr/bin/discord", "--", "%u"]),
      ([], ["/usr/bin/discord", "--", "%u"]))

print()
print("finding the application inside Steam's launch chain:")

# Captured from a real tile launch: this is what %command% expanded to.
STEAM_CHAIN = [
    "/home/u/.local/share/Steam/ubuntu12_32/steam-launch-wrapper", "--",
    "/home/u/.local/share/Steam/ubuntu12_64/reaper", "SteamLaunch",
    "AppId=3214031495", "--", "/usr/bin/discord",
]

check("the application is found past the wrapper and the reaper",
      app.real_program(STEAM_CHAIN), ["/usr/bin/discord"])
# The name everything else is decided from. Getting this wrong is what left
# Discord running with no window after Steam's Stop button.
check("so it is named after the application, not the wrapper",
      os.path.basename(app.real_program(STEAM_CHAIN)[0]), "discord")
check("and its instance names are the application's",
      app.instance_names(app.real_program(STEAM_CHAIN)[0]), {"discord"})

check("the application's own arguments come with it",
      app.real_program(STEAM_CHAIN + ["--", "%u"]),
      ["/usr/bin/discord", "--", "%u"])
check("a bare program is left alone",
      app.real_program(["/usr/bin/discord"]), ["/usr/bin/discord"])
check("as is one that merely has arguments",
      app.real_program(["/usr/bin/discord", "--start-minimized"]),
      ["/usr/bin/discord", "--start-minimized"])
check("the reaper on its own is skipped too",
      app.real_program(["/path/reaper", "SteamLaunch", "AppId=7", "--", "/usr/bin/app"]),
      ["/usr/bin/app"])
# Never an empty command: a chain with nothing after it is a launch we cannot
# interpret, and guessing would be worse than running what we were given.
check("a chain with nothing after it falls back to the chain",
      app.real_program(["/path/steam-launch-wrapper"]),
      ["/path/steam-launch-wrapper"])

print()
print("taking Steam's overlay out of the way:")

# The exact value Steam sets for a non-Steam shortcut, 32-bit and 64-bit, with
# the empty leading field it really has.
STEAM_PRELOAD = (":/home/u/.local/share/Steam/ubuntu12_32/gameoverlayrenderer.so"
                 ":/home/u/.local/share/Steam/ubuntu12_64/gameoverlayrenderer.so")


def stripped(value):
    """The LD_PRELOAD left behind, with None for 'gone entirely'."""
    env = {} if value is None else {"LD_PRELOAD": value}
    dropped = app.strip_overlay(env)
    return env.get("LD_PRELOAD"), dropped


left, dropped = stripped(STEAM_PRELOAD)
check("Steam's overlay is dropped", len(dropped), 2)
# Nothing left worth setting, and an empty LD_PRELOAD is not the same as none:
# the dynamic linker treats the empty entry as the current directory.
check("and LD_PRELOAD goes with it rather than being left empty", left, None)

left, dropped = stripped(
    "/usr/lib/libsomething.so:"
    "/home/u/.local/share/Steam/ubuntu12_64/gameoverlayrenderer.so")
check("a preload the user chose is kept", left, "/usr/lib/libsomething.so")
check("and only the overlay is dropped", dropped,
      ["/home/u/.local/share/Steam/ubuntu12_64/gameoverlayrenderer.so"])

# LD_PRELOAD is whitespace-separated as well as colon-separated, and Steam is not
# the only thing that writes it.
left, dropped = stripped("/usr/lib/a.so /path/gameoverlayrenderer.so /usr/lib/b.so")
check("spaces separate entries too", left, "/usr/lib/a.so:/usr/lib/b.so")
check("and the overlay is still found", len(dropped), 1)

check("nothing to do without LD_PRELOAD", stripped(None), (None, []))
# Left exactly as found: there is no overlay in it to take out, and a variable we
# had no reason to touch is not ours to remove.
check("nor with an empty one", stripped(""), ("", []))
left, dropped = stripped("/usr/lib/only-mine.so")
check("a preload with no overlay in it is untouched", left, "/usr/lib/only-mine.so")
check("and reports nothing dropped", dropped, [])

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
    sys.exit(1)
print("all app tests passed")
