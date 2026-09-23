#!/usr/bin/env python3
"""Which screen console mode picks, and when it refuses to guess.

gamescope's nested backend can be pointed at a screen one way only: by index.
--prefer-output is read by the DRM backend alone, and SDL handed an index that
is not there does not fail -- it puts the window on the first display, which is
the monitor being played on. So an index resolved against a layout that is still
changing is how console mode ends up on the wrong screen with nothing in the log
to show for it.

A screen that has just woken is what makes a layout change: KWin places it at
0,0 until the arrangement is applied, where it shares a position with whatever
is already there. These pin both halves of that -- the merge not attributing one
screen's mode to another, and resolve refusing to answer while it is happening.

Nothing here touches SDL: both backends are replaced with lists of our own.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "bin", "cachy-console-display")
loader = importlib.machinery.SourceFileLoader("cd", TARGET)
spec = importlib.util.spec_from_loader("cd", loader)
cd = importlib.util.module_from_spec(spec)
loader.exec_module(cd)

FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"        got  = {got!r}")
        print(f"        want = {want!r}")
        FAILURES.append(label)


def screen(index, name, x, w=1920, h=1080, refresh=60, y=0):
    return {"index": index, "name": name, "x": x, "y": y,
            "w": w, "h": h, "refresh": refresh}


def backends(x11, wayland):
    """Answer enumerate_sdl from lists instead of a display server."""
    cd.enumerate_sdl = lambda driver: [
        dict(entry) for entry in (x11 if driver == "x11" else wayland)]


# The arrangement this was found on: a 240Hz monitor at 0,0 and a projector
# beside it. x11 names connectors, wayland names manufacturers.
MONITOR = screen(0, 'DP-2 25"', 0, refresh=240)
PROJECTOR = screen(1, 'HDMI-A-1 36"', 1920, w=3840, h=2160)
MONITOR_WL = screen(0, "BNQ ZOWIE XL LCD", 0, refresh=240)
PROJECTOR_WL = screen(1, "Optoma UHD", 1920, w=3840, h=2160)

print("\nmerging what each backend knows")
backends([MONITOR, PROJECTOR], [MONITOR_WL, PROJECTOR_WL])
found = cd.displays()
check("the connector and index come from x11",
      [(d["index"], cd.connector_of(d)) for d in found],
      [(0, "DP-2"), (1, "HDMI-A-1")])
check("the manufacturer comes from wayland",
      [d["model"] for d in found], ["BNQ ZOWIE XL LCD", "Optoma UHD"])
check("and so does the refresh rate, per screen",
      [d["refresh"] for d in found], [240, 60])

print("\na screen that has just woken, still sitting at 0,0")
# The projector has appeared to x11 at its real place, while wayland still has
# it stacked on the monitor. Keying the merge on position alone hands the
# projector the monitor's 240Hz -- which is what console mode asked gamescope
# for, on a projector that cannot do it.
backends([MONITOR, PROJECTOR],
         [MONITOR_WL, screen(1, "Optoma UHD", 0, w=3840, h=2160)])
found = cd.displays()
check("neither screen at the shared position is merged from",
      [d["model"] for d in found], ["", ""])
check("so no screen is given another's refresh rate",
      [d["refresh"] for d in found], [240, 60])
check("and both are still there, with their own indices",
      [(d["index"], cd.connector_of(d)) for d in found],
      [(0, "DP-2"), (1, "HDMI-A-1")])

print("\nspotting a layout that is still moving")
check("two screens at one position are both reported",
      [cd.connector_of(d) for d in
       cd.stacked_displays([MONITOR, screen(1, 'HDMI-A-1 36"', 0)])],
      ["DP-2", "HDMI-A-1"])
check("a settled arrangement has none",
      cd.stacked_displays([MONITOR, PROJECTOR]), [])
check("nor does a single screen",
      cd.stacked_displays([MONITOR]), [])
check("three on top of each other are all reported",
      len(cd.stacked_displays([MONITOR, screen(1, "DP-1", 0),
                               screen(2, "DP-3", 0)])), 3)

print("\nresolve, asked to be strict about it")


class Args:
    def __init__(self, name, strict):
        self.name = name
        self.strict = strict
        self.json = True


def resolve(name, strict):
    """cmd_resolve's answer, or the message it refused with."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            cd.cmd_resolve(Args(name, strict))
    except cd.DisplayError as exc:
        return ("refused", str(exc))
    return ("resolved", buf.getvalue().strip())


cd.read_config = lambda: {}
backends([MONITOR, PROJECTOR], [MONITOR_WL, PROJECTOR_WL])
kind, answer = resolve("HDMI-A-1", True)
check("a settled layout resolves to the index of the screen asked for",
      (kind, json.loads(answer)["index"]), ("resolved", 1))

backends([MONITOR, screen(1, 'HDMI-A-1 36"', 0)],
         [MONITOR_WL, screen(1, "Optoma UHD", 0)])
kind, answer = resolve("HDMI-A-1", True)
check("a stacked one refuses rather than name an index",
      (kind, "still arranging themselves" in answer), ("refused", True))
check("and says which screens are stacked, so the wait is explicable",
      ("DP-2" in answer, "HDMI-A-1" in answer), (True, True))

kind, answer = resolve("HDMI-A-1", False)
check("without --strict the same layout still answers, for callers that must",
      (kind, json.loads(answer)["index"]), ("resolved", 1))

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
    sys.exit(1)
print("all display choice tests passed")
