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
if FAILURES:
    print(f"{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
    sys.exit(1)
print("all shortcut tests passed")
