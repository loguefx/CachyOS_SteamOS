#!/usr/bin/env python3
"""Tests for the binary-VDF handling in install-exit-shortcut.py.

shortcuts.vdf is the user's own library of non-Steam games. A serializer bug
here would silently destroy entries they added by hand, and the damage would
only surface the next time they went looking for a game, so the round-trip and
merge behaviour are worth pinning down.
"""

import importlib.machinery
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "bin", "cachy-console-shortcut")
loader = importlib.machinery.SourceFileLoader("ies", TARGET)
spec = importlib.util.spec_from_loader("ies", loader)
ies = importlib.util.module_from_spec(spec)
loader.exec_module(ies)

ART = os.path.join(HERE, "..", "bin", "cachy-console-art")
art_loader = importlib.machinery.SourceFileLoader("cca", ART)
art = importlib.util.module_from_spec(
    importlib.util.spec_from_loader("cca", art_loader))
art_loader.exec_module(art)

FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"        got  = {got!r}")
        print(f"        want = {want!r}")
        FAILURES.append(label)


EXE = "/tmp/cachy-console-exit"
NAME = "Exit Console Mode"

print("round-trip:")
entry = ies.build_entry(EXE, NAME)
raw = ies.dumps({"shortcuts": {"0": entry}})
check("a shortcut survives serialize/parse unchanged",
      ies.parse(raw), {"shortcuts": {"0": entry}})
check("the file is a 'shortcuts' map", raw[:11], b"\x00shortcuts\x00")
check("the implicit root map is terminated", raw[-2:], b"\x08\x08")
check("an empty tags map round-trips", ies.parse(raw)["shortcuts"]["0"]["tags"], {})

print()
print("appid:")
# Steam stores shortcut ids with the high bit set; a signed pack would overflow.
check("the high bit is set", entry["appid"] >> 31, 1)
check("it survives the 32-bit round-trip",
      ies.parse(raw)["shortcuts"]["0"]["appid"], entry["appid"])
check("it is stable for the same exe and name",
      ies.shortcut_appid(f'"{EXE}"', NAME), entry["appid"])
check("a different name gives a different id",
      ies.shortcut_appid(f'"{EXE}"', "Other") != entry["appid"], True)

print()
print("merging into an existing library:")
theirs = ies.build_entry("/usr/bin/foo", "Some Game")
path = os.path.join(tempfile.mkdtemp(), "shortcuts.vdf")
with open(path, "wb") as fh:
    fh.write(ies.dumps({"shortcuts": {"0": theirs}}))

loaded = ies.load(path)
check("their shortcut is read back", loaded["shortcuts"]["0"]["AppName"], "Some Game")
check("we are appended after it", ies.next_index(loaded["shortcuts"]), "1")

loaded["shortcuts"]["1"] = entry
ies.save(path, loaded, dry_run=False)
final = ies.load(path)
check("both entries survive the write", len(final["shortcuts"]), 2)
check("their game is untouched", final["shortcuts"]["0"]["AppName"], "Some Game")
check("ours is present", final["shortcuts"]["1"]["AppName"], NAME)

index = ies.find_entry(final["shortcuts"], EXE, NAME)
check("ours is findable for update and revert", index, "1")

legacy = {"shortcuts": {"0": ies.build_entry("/home/me/.local/bin/projector-exit",
                                             "Exit Game Mode")}}
check("an old Exit Game Mode / projector-exit tile is the same entry",
      ies.find_entry(legacy["shortcuts"], EXE, NAME), "0")
del final["shortcuts"][index]
renumbered = {str(n): v for n, v in enumerate(final["shortcuts"].values())}
check("reverting leaves only their game",
      [e["AppName"] for e in renumbered.values()], ["Some Game"])
check("and renumbers keys consecutively", list(renumbered), ["0"])

print()
print("a second shortcut living alongside the exit tile:")
# Discord has to be launched inside gamescope, so it gets its own tile. The
# legacy fallbacks must not let that run adopt and rename the exit entry.
DISCORD = "/usr/bin/discord"
library = {"0": ies.build_entry(EXE, NAME)}
check("adding Discord does not adopt the exit tile",
      ies.find_entry(library, DISCORD, "Discord"), None)
check("the exit run still finds its own tile", ies.find_entry(library, EXE, NAME), "0")

library["1"] = ies.build_entry(DISCORD, "Discord")
check("Discord is found for a later update", ies.find_entry(library, DISCORD, "Discord"), "1")
check("and the exit tile stays separate", ies.find_entry(library, EXE, NAME), "0")
check("the two get different appids",
      library["0"]["appid"] != library["1"]["appid"], True)

old = {"0": ies.build_entry("/home/me/.local/bin/projector-exit", "Exit Game Mode")}
check("a Discord run leaves an old projector-exit tile alone",
      ies.find_entry(old, DISCORD, "Discord"), None)

print()
print("first run, with no library yet:")
check("a missing file reads as an empty library",
      ies.load(os.path.join(tempfile.mkdtemp(), "absent.vdf")), {"shortcuts": {}})
check("an empty library is still a valid file",
      ies.parse(ies.dumps({"shortcuts": {}})), {"shortcuts": {}})

print()
print("refusing to guess at damaged input:")
# Better to leave a file we do not understand alone than to rewrite it wrongly.
for label, blob in (("an unknown type byte", b"\x99bogus\x00"),
                    ("an unterminated string", b"\x01key\x00no-terminator"),
                    ("a truncated int", b"\x02key\x00\x01\x02"),
                    ("a map that never closes", b"\x00sub\x00\x01k\x00v\x00")):
    try:
        ies.parse(blob)
        check(f"{label} is rejected", "parsed", "VDFError")
    except ies.VDFError:
        check(f"{label} is rejected", "VDFError", "VDFError")

print()
print("library artwork:")
# Steam names a shortcut's art files after the same unsigned appid it keeps in
# shortcuts.vdf, but prints the signed form of that number in its own logs
# when its asset downloader skips the app. Art filed under the signed form is
# art Steam never looks at, so the two helpers agreeing is the whole game.
ART_ID = art.grid_appid(f'"{DISCORD}"', "Discord")
check("the art helper derives the id the shortcut stores",
      ART_ID, ies.build_entry(DISCORD, "Discord")["appid"])
check("and it is the unsigned form, not the negative Steam logs",
      ART_ID >> 31, 1)
check("the vertical capsule is <id>p.png",
      art.grid_filename(ART_ID, "capsule"), f"{ART_ID}p.png")
check("the horizontal capsule is <id>.png",
      art.grid_filename(ART_ID, "wide"), f"{ART_ID}.png")
check("the hero is <id>_hero.png",
      art.grid_filename(ART_ID, "hero"), f"{ART_ID}_hero.png")
check("the logo is <id>_logo.png",
      art.grid_filename(ART_ID, "logo"), f"{ART_ID}_logo.png")
check("we render the sizes Steam expects",
      {kind: size for kind, (_, size) in art.ART_TYPES.items()},
      {"capsule": (600, 900), "wide": (920, 430),
       "hero": (1920, 620), "logo": (640, 480)})

grid = os.path.join(tempfile.mkdtemp(), "grid")
group = art.paths_for(ART_ID, grid)
check("all four files go to one grid directory", len(group), 1)
check("and no two of them collide", len(set(group[0].values())), 4)

check("a new entry carries no icon unless one is found",
      ies.build_entry(DISCORD, "Discord")["icon"], "")
check("and records the one it was given",
      ies.build_entry(DISCORD, "Discord", "/x/discord.png")["icon"],
      "/x/discord.png")

print()
print("finding an icon to build the artwork from:")
# Biggest wins: a 64px icon stretched over a 600x900 capsule is a blurry mess.
# A made-up program name keeps this off whatever the host has installed.
FAKE = "/usr/bin/zz-not-a-real-program"
root = os.path.join(tempfile.mkdtemp(), "icons")
for size in ("64x64", "256x256", "128x128"):
    os.makedirs(os.path.join(root, "hicolor", size, "apps"))
    open(os.path.join(root, "hicolor", size, "apps",
                      "zz-not-a-real-program.png"), "wb").close()
art.icon_dirs = lambda: [root]
check("the biggest installed icon wins", art.find_icon(FAKE),
      os.path.join(root, "hicolor/256x256/apps/zz-not-a-real-program.png"))

os.makedirs(os.path.join(root, "hicolor", "scalable", "apps"))
open(os.path.join(root, "hicolor/scalable/apps/zz-not-a-real-program.svg"),
     "wb").close()
check("but a scalable icon beats every bitmap", art.find_icon(FAKE),
      os.path.join(root, "hicolor/scalable/apps/zz-not-a-real-program.svg"))
check("the entry name is tried too, for wrapper scripts",
      art.find_icon("/usr/bin/wrapper", "ZZ Not A Real Program"),
      os.path.join(root, "hicolor/scalable/apps/zz-not-a-real-program.svg"))
check("a program with no icon anywhere gets no artwork",
      art.find_icon("/usr/bin/zz-nothing-here"), None)

if art.Image is not None:
    swatch = art.Image.new("RGBA", (64, 64), (255, 255, 255, 255))
    art.ImageDraw.Draw(swatch).rectangle((0, 0, 63, 40), fill=(88, 101, 242, 255))
    # The white half of Discord's icon outnumbers nothing, but averaging it in
    # would give a washed-out lilac instead of the colour it is known by.
    check("the backdrop takes the icon's brand colour, not its average",
          art.dominant_color(swatch), (88, 101, 242))

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
    sys.exit(1)
print("all shortcut tests passed")
