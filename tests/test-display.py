#!/usr/bin/env python3
"""Tests for how displays are found, merged and chosen.

This is the part that has to work on hardware nobody here can test: one monitor
or four, GNOME or KDE, a TV that reports its refresh rate honestly and an
XWayland that does not. Choosing the wrong display puts Big Picture on a screen
the user is not looking at, and taking the wrong refresh rate makes gamescope
drive their TV at the wrong rate, so both merges are pinned down here with
faked SDL output rather than whatever hardware happens to be plugged in.
"""

import importlib.machinery
import importlib.util
import os
import sys
import tempfile

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


def display(index, name, x, y, w, h, refresh):
    return {"index": index, "name": name, "x": x, "y": y,
            "w": w, "h": h, "refresh": refresh}


def fake_sdl(x11, wayland):
    """Stand in for both SDL backends."""
    def enumerate_sdl(driver):
        return [dict(d) for d in (x11 if driver == "x11" else wayland)]
    cd.enumerate_sdl = enumerate_sdl


def no_config():
    cd.CONFIG_PATH = "/nonexistent/cachy-console/config"


no_config()

# The situation this project exists for: XWayland lies about the refresh rate of
# one screen, and the wayland backend knows better, but only the x11 backend
# knows the connector names and the ordering gamescope will use.
X11 = [
    display(0, 'DP-1 49"', 1920, 0, 5120, 1440, 60),      # really 240Hz
    display(1, 'DP-2 24"', 0, 0, 1920, 1080, 240),
    display(2, "HDMI-1", 7040, 0, 1920, 1080, 240),
]
WAYLAND = [
    display(0, "Samsung Electric Company 49\"", 1920, 0, 5120, 1440, 240),
    display(1, "BenQ Corporation 24\"", 0, 0, 1920, 1080, 240),
    display(2, "Optoma Corporation", 7040, 0, 1920, 1080, 240),
]

print("merging the two SDL views:")
fake_sdl(X11, WAYLAND)
found = cd.displays()

check("every display is reported once", len(found), 3)
check("indices come from x11, which is what gamescope uses",
      [d["index"] for d in found], [0, 1, 2])
check("a refresh rate XWayland got wrong is corrected from wayland",
      found[0]["refresh"], 240)
check("a refresh rate both agree on is left alone", found[2]["refresh"], 240)
check("connector names come from x11",
      [cd.connector_of(d) for d in found], ["DP-1", "DP-2", "HDMI-1"])
check("the friendly model name is kept for matching",
      found[2]["model"], "Optoma Corporation")

print()
print("when the two views disagree about more than refresh:")
# Different resolutions mean the position match was a coincidence, or one view
# is stale. Trusting it could hand gamescope a mode the display cannot show.
fake_sdl([display(0, "HDMI-1", 0, 0, 1920, 1080, 60)],
         [display(0, "TV", 0, 0, 3840, 2160, 120)])
check("a mismatched resolution means the refresh is not borrowed",
      cd.displays()[0]["refresh"], 60)

fake_sdl([display(0, "HDMI-1", 0, 0, 1920, 1080, 60)],
         [display(0, "TV", 500, 500, 1920, 1080, 120)])
check("a display at a different position is not treated as the same one",
      cd.displays()[0]["refresh"], 60)

print()
print("when only one backend answers:")
fake_sdl([], WAYLAND)
check("with no x11, the wayland view is used rather than failing",
      [d["refresh"] for d in cd.displays()], [240, 240, 240])

fake_sdl(X11, [])
check("with no wayland, x11 is used as-is",
      [d["refresh"] for d in cd.displays()], [60, 240, 240])

fake_sdl([], [])
try:
    cd.displays()
    check("no displays at all raises", "returned", "DisplayError")
except cd.DisplayError:
    check("no displays at all raises DisplayError", "DisplayError", "DisplayError")

print()
print("choosing a display:")
fake_sdl(X11, WAYLAND)

check("by connector name", cd.connector_of(cd.pick("HDMI-1")), "HDMI-1")
check("connector matching ignores case", cd.connector_of(cd.pick("hdmi-1")), "HDMI-1")

try:
    cd.pick("auto")
    check("auto is refused rather than picking another screen", "returned", "DisplayError")
except cd.DisplayError:
    check("auto is refused rather than picking another screen", "DisplayError", "DisplayError")

try:
    cd.pick("Optoma")
    check("a model substring is not used as a substitute", "returned", "DisplayError")
except cd.DisplayError:
    check("a model substring is not used as a substitute", "DisplayError", "DisplayError")

check("by SDL index only when allow_index is set",
      cd.connector_of(cd.pick("2", allow_index=True)), "HDMI-1")
check("index 0 with allow_index",
      cd.connector_of(cd.pick("0", allow_index=True)), "DP-1")

try:
    cd.pick("2")
    check("an index is refused unless explicitly allowed", "returned", "DisplayError")
except cd.DisplayError:
    check("an index is refused unless explicitly allowed", "DisplayError", "DisplayError")

try:
    cd.pick("7", allow_index=True)
    check("an index that does not exist is an error", "returned", "DisplayError")
except cd.DisplayError:
    check("an index that does not exist is an error", "DisplayError", "DisplayError")

try:
    cd.pick("DP-9")
    check("an unplugged display is an error", "returned", "DisplayError")
except cd.DisplayError as exc:
    check("an unplugged display is an error", "DisplayError", "DisplayError")
    check("and it refuses to name another screen as a fallback",
          "not using another screen" in str(exc), True)

print()
print("saved display stays put when other screens are on:")
# HDMI-1 is saved but currently off; DP-1 and DP-2 are still live. Picking
# from config must not quietly land on DP-1.
cd.CONFIG_PATH = os.path.join(tempfile.mkdtemp(), "config")
os.makedirs(os.path.dirname(cd.CONFIG_PATH), exist_ok=True)
cd.update_config({"DISPLAY": "HDMI-1", "DISPLAY_MODEL": "Optoma Corporation"})
fake_sdl(
    [display(0, 'DP-1 49"', 1920, 0, 5120, 1440, 60),
     display(1, 'DP-2 24"', 0, 0, 1920, 1080, 240)],
    [display(0, "Samsung Electric Company 49\"", 1920, 0, 5120, 1440, 240),
     display(1, "BenQ Corporation 24\"", 0, 0, 1920, 1080, 240)])
check("saved_connector still reads HDMI-1 while it is off",
      cd.saved_connector(), "HDMI-1")
try:
    cd.pick(None)
    check("launching does not fall through to another display", "returned", "DisplayError")
except cd.DisplayError as exc:
    check("launching does not fall through to another display",
          "HDMI-1" in str(exc) and "not using another screen" in str(exc), True)

print()
print("a connector name should win over a model substring:")
# "DP-1" appears inside the *name* of one display and could appear in another's
# model string; the exact connector must not lose to a loose substring hit.
fake_sdl([display(0, "HDMI-1", 0, 0, 1920, 1080, 60),
          display(1, "DP-1", 1920, 0, 1920, 1080, 60)],
         [display(0, "DP-1 clone TV", 0, 0, 1920, 1080, 60),
          display(1, "Dell", 1920, 0, 1920, 1080, 60)])
check("exact connector match wins", cd.connector_of(cd.pick("DP-1")), "DP-1")

print()
print("reading the config:")
path = os.path.join(tempfile.mkdtemp(), "config")
with open(path, "w") as fh:
    fh.write("# a comment\n"
             "DISPLAY=HDMI-1\n"
             "RESOLUTION = 1920x1080   # trailing comment\n"
             'REFRESH="120"\n'
             "\n"
             "MALFORMED\n")
cd.CONFIG_PATH = path
config = cd.read_config()
check("plain values are read", config["DISPLAY"], "HDMI-1")
check("whitespace and trailing comments are stripped",
      config["RESOLUTION"], "1920x1080")
check("quotes are stripped", config["REFRESH"], "120")
check("lines without a value are skipped", "MALFORMED" in config, False)

cd.update_config({"DISPLAY": "DP-2", "DISPLAY_MODEL": "BenQ"})
again = cd.read_config()
check("set keeps the other keys", again["RESOLUTION"], "1920x1080")
check("set updates DISPLAY", again["DISPLAY"], "DP-2")
check("saved_connector follows the file", cd.saved_connector(), "DP-2")

cd.CONFIG_PATH = "/nonexistent/config"
check("a missing config is not an error", cd.read_config(), {})
check("missing config means no saved display", cd.saved_connector(), None)

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
    sys.exit(1)
print("all display tests passed")
