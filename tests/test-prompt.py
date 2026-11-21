#!/usr/bin/env python3
"""The close-games prompt's logic, against a fake /proc. No windows, no KWin.

usage: ./test-prompt.py [path-to-cachy-console-prompt]
"""

import importlib.machinery
import importlib.util
import os
import struct
import sys
import tempfile

DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "bin", "cachy-console-prompt")
TARGET = sys.argv[1] if len(sys.argv) > 1 else DEFAULT

loader = importlib.machinery.SourceFileLoader("ccp", TARGET)
spec = importlib.util.spec_from_loader("ccp", loader)
pr = importlib.util.module_from_spec(spec)
loader.exec_module(pr)

FAILURES = 0


def check(name, got, want):
    global FAILURES
    ok = got == want
    if not ok:
        FAILURES += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"          got  {got}\n          want {want}")


def fake_proc(root, pid, ppid, argv, comm=None):
    d = os.path.join(root, str(pid))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "cmdline"), "wb") as fh:
        fh.write(b"\0".join(a.encode() for a in argv) + b"\0")
    comm = comm or os.path.basename(argv[0])
    with open(os.path.join(d, "stat"), "w") as fh:
        fh.write(f"{pid} ({comm}) S {ppid} 0 0\n")


print("finding the games Steam started:")
with tempfile.TemporaryDirectory() as proc:
    steam = "/home/u/.local/share/Steam/steamrt64/reaper"
    fake_proc(proc, 100, 1, ["steam"])
    fake_proc(proc, 200, 100, [steam, "SteamLaunch", "AppId=1422450", "--",
                               "proton", "waitforexitandrun", "deadlock.exe"])
    fake_proc(proc, 201, 200, ["proton", "waitforexitandrun"])
    fake_proc(proc, 202, 201, ["deadlock.exe"], comm="deadlock.exe")
    fake_proc(proc, 203, 200, ["wineserver"])
    fake_proc(proc, 300, 100, [steam, "SteamLaunch", "AppId=620", "--", "portal2"])
    fake_proc(proc, 301, 300, ["portal2"])
    # A game whose own arguments happen to mention another appid.
    fake_proc(proc, 400, 100, [steam, "SteamLaunch", "AppId=70", "--",
                               "hl", "AppId=620"])
    # Not a reaper at all, despite the arguments.
    fake_proc(proc, 500, 1, ["grep", "SteamLaunch", "AppId=620"])

    check("every Steam launch, for close-all",
          pr.reapers(proc_root=proc), [200, 300, 400])
    check("one appid, matched only in reaper's own arguments",
          pr.reapers("620", proc_root=proc), [300])
    order = pr.tree([200], proc_root=proc)
    check("the whole tree under a reaper, wineserver included",
          sorted(order), [200, 201, 202, 203])
    check("children are signalled before their parents",
          order.index(202) < order.index(201) < order.index(200), True)

print()
print("hands off the mouse:")
check("there is no pointer device to move it with",
      any(hasattr(pr, n) for n in ("AbsPointer", "abs_value")), False)
check("focus is given back to the window that had it",
      "workspace.activeWindow = w" in pr.RESTORE_JS, True)

print()
print("hands off the keyboard:")
SOURCE = open(TARGET).read()
check("the prompt is never made the active window",
      "workspace.activeWindow = win" in pr.PLACE_JS, False)
check("if KWin activated it on opening, focus goes straight back",
      "workspace.activeWindow === win && P.prev" in pr.PLACE_JS, True)
check("on closing, focus is only moved if the prompt somehow holds it",
      "a.pid === P.pid" in pr.RESTORE_JS, True)
check("no keyboard key answers it, so Enter at the desk cannot close games",
      ("key-press-event" in SOURCE, "KEY_Return" in SOURCE), (False, False))
check("controllers that appear after the prompt opens are picked up",
      "GLib.timeout_add(1000, listen)" in SOURCE, True)
check("and GTK is asked not to take focus",
      ("set_accept_focus(False)" in SOURCE, "set_focus_on_map(False)" in SOURCE),
      (True, True))

print()
print("A and B from a plain gamepad:")


def ev(typ, code, value):
    return struct.pack(pr.EVENT_FORMAT, 0, 0, typ, code, value)


raw = (ev(pr.EV_KEY, pr.BTN_SOUTH, 1) + ev(0, 0, 0) + ev(pr.EV_KEY, pr.BTN_SOUTH, 0)
       + ev(pr.EV_KEY, pr.BTN_EAST, 1) + ev(pr.EV_KEY, 0x133, 1))
check("presses only, releases and other buttons ignored",
      pr.face_presses(raw), ["a", "b"])
check("a Switch pad confirms with A on the right, as it is labelled",
      pr.face_presses(ev(pr.EV_KEY, pr.BTN_EAST, 1) + ev(pr.EV_KEY, pr.BTN_SOUTH, 1),
                      pr.PADS["switch"]), ["a", "b"])
check("PlayStation shows a cross to confirm and a circle to go back",
      (pr.PADS["playstation"]["confirm"], pr.PADS["playstation"]["back"]),
      ("\u2715", "\u25cb"))
check("--pad wins; an unknown one falls back to a known pad",
      (pr.pick_pad("xbox"), pr.pick_pad("nonsense") in pr.PADS), ("xbox", True))
with tempfile.TemporaryDirectory() as tmp:
    for name, cap in (("event0", f"{1 << (pr.BTN_SOUTH - 256):x} 0 0 0 0"),
                      ("event1", "20000 0 0 0 0")):
        d = os.path.join(tmp, name, "device", "capabilities")
        os.makedirs(d)
        with open(os.path.join(d, "key"), "w") as fh:
            fh.write(cap + "\n")
    check("gamepads are found by BTN_SOUTH, keyboards are not",
          pr.gamepad_nodes(tmp, "/dev/input"), ["/dev/input/event0"])

with tempfile.TemporaryDirectory() as tmp:
    south = f"{1 << (pr.BTN_SOUTH - 256):x} 0 0 0 0"
    for name, vendor in (("event3", "28de"),     # Steam's virtual pad
                         ("event4", "045e"),     # an Xbox pad at the desk
                         ("event5", "054c")):    # a DualSense
        d = os.path.join(tmp, name, "device")
        os.makedirs(os.path.join(d, "capabilities"))
        os.makedirs(os.path.join(d, "id"))
        with open(os.path.join(d, "capabilities", "key"), "w") as fh:
            fh.write(south + "\n")
        with open(os.path.join(d, "id", "vendor"), "w") as fh:
            fh.write(vendor + "\n")
    check("a Steam Controller prompt hears Steam's virtual pad, not the desk's "
          "Xbox pad", pr.pads_for("steam", tmp, "/dev/input"), ["/dev/input/event3"])
    check("a PlayStation prompt hears the DualSense and Steam's pad",
          pr.pads_for("playstation", tmp, "/dev/input"),
          ["/dev/input/event3", "/dev/input/event5"])
    check("an unknown family still hears every pad rather than none",
          pr.pads_for("nonsense", tmp, "/dev/input") != [], True)

print()
print("wording:")
check("one game", pr.games_line([("1", "Deadlock")]),
      "Deadlock will be closed. Anything unsaved will be lost.")
check("several", pr.games_line([("1", "A"), ("2", "B"), ("3", "C")]),
      "A, B and C will be closed. Anything unsaved will be lost.")
check("bad --game values are dropped",
      pr.parse_games(["1422450=Deadlock", "junk", "620="]),
      [("1422450", "Deadlock"), ("620", "App 620")])

print()
if FAILURES:
    print(f"{FAILURES} failure(s)")
    sys.exit(1)
print("all prompt tests passed")
