#!/usr/bin/env python3
"""Game fixes: cachy-console-compat against a made-up Steam library.

Nothing here downloads anything or touches a real game: the library, the Wine
prefix, /proc and the download cache are all built in a temporary folder, and
the fix table is swapped for one whose "downloads" are zips made on the spot
and dropped into the cache under their own SHA-256 -- the same way a real
download would be found the second time.
"""

import hashlib
import importlib.machinery
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "bin", "cachy-console-compat")

FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"        got  = {got!r}")
        print(f"        want = {want!r}")
        FAILURES.append(label)


def make_zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


EXE_DX9 = b"pretend dx9 build"
EXE_DX10 = b"pretend dx10 build"
ASI = b"the patch"
INI = b"[Patch]\nKeyboardLayout=0\n"
LOADER = b"the asi loader"

REG = ("WINE REGISTRY Version 2\n"
       ";; All keys relative to REGISTRY\\\\User\\\\S-1-5-21-0-0-0-1000\n\n"
       "#arch=win64\n\n"
       "[Software\\\\Wine\\\\AppDefaults\\\\Other.exe\\\\DllOverrides] 1789159588\n"
       "#time=1dd422e9e493462\n"
       "\"d3d9\"=\"native\"\n")


class World:
    def __init__(self, exes=(EXE_DX9, EXE_DX10), prefix=True, library="extra"):
        self.root = tempfile.mkdtemp(prefix="cachy-compat-test-")
        self.steam = os.path.join(self.root, "Steam")
        self.lib = os.path.join(self.root, library) if library else self.steam
        os.makedirs(os.path.join(self.steam, "steamapps"))
        with open(os.path.join(self.steam, "steamapps", "libraryfolders.vdf"), "w") as fh:
            fh.write('"libraryfolders"\n{\n "0"\n {\n  "path"\t\t"%s"\n }\n'
                     ' "1"\n {\n  "path"\t\t"%s"\n }\n}\n' % (self.steam, self.lib))
        apps = os.path.join(self.lib, "steamapps")
        self.game = os.path.join(apps, "common", "Test Game")
        os.makedirs(self.game)
        with open(os.path.join(apps, "appmanifest_4242.acf"), "w") as fh:
            fh.write('"AppState"\n{\n "appid" "4242"\n "installdir"\t\t"Test Game"\n}\n')
        names = ("Game_Dx9.exe", "Game_Dx10.exe")
        for name, data in zip(names, exes):
            with open(os.path.join(self.game, name), "wb") as fh:
                fh.write(data)
        self.pfx = os.path.join(apps, "compatdata", "4242", "pfx")
        if prefix:
            os.makedirs(self.pfx)
            with open(os.path.join(self.pfx, "user.reg"), "w") as fh:
                fh.write(REG)
        self.proc = os.path.join(self.root, "proc")
        os.makedirs(self.proc)
        self.cache = os.path.join(self.root, "cache")
        os.makedirs(self.cache)
        self.state = os.path.join(self.root, "state")
        self.mod = self.load()
        patch_zip = make_zip({"Patch.asi": ASI, "Patch.ini": INI})
        loader_zip = make_zip({"dinput8.dll": LOADER})
        self.downloads = []
        for data in (patch_zip, loader_zip):
            digest = hashlib.sha256(data).hexdigest()
            with open(os.path.join(self.cache, digest + ".zip"), "wb") as fh:
                fh.write(data)
            self.downloads.append(digest)
        self.mod.FIXES = {"4242": {
            "id": "test-patch",
            "name": "Test Game",
            "patch": "TestPatch 1",
            "why": "test",
            "exes": {"Game_Dx9.exe": hashlib.md5(EXE_DX9).hexdigest(),
                     "Game_Dx10.exe": hashlib.md5(EXE_DX10).hexdigest()},
            "downloads": [
                {"url": "https://invalid.example/patch.zip", "sha256": self.downloads[0],
                 "files": {"Patch.asi": "scripts/Patch.asi", "Patch.ini": "scripts/Patch.ini"}},
                {"url": "https://invalid.example/loader.zip", "sha256": self.downloads[1],
                 "files": {"dinput8.dll": "dinput8.dll"}},
            ],
            "settings": ["scripts/Patch.ini"],
            "dll_overrides": {"dinput8": "native,builtin"},
        }}
        self.fix = self.mod.FIXES["4242"]

    def load(self):
        os.environ["CACHY_CONSOLE_STEAM_ROOT"] = self.steam
        os.environ["XDG_STATE_HOME"] = self.state
        os.environ["CACHY_CONSOLE_COMPAT_CACHE"] = self.cache
        os.environ["CACHY_CONSOLE_PROC"] = self.proc
        name = f"compat{id(self)}"
        loader = importlib.machinery.SourceFileLoader(name, TARGET)
        spec = importlib.util.spec_from_loader(name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod

    def status(self):
        return self.mod.status("4242", self.fix)[0]

    def apply(self):
        return self.mod.main(["apply", "4242"])

    def remove(self):
        return self.mod.main(["remove", "4242"])

    def reg(self):
        with open(os.path.join(self.pfx, "user.reg")) as fh:
            return fh.read()

    def override(self, exe):
        return self.mod.read_override(self.reg(), exe, "dinput8")

    def read(self, rel):
        with open(os.path.join(self.game, rel), "rb") as fh:
            return fh.read()

    def exists(self, rel):
        return os.path.exists(os.path.join(self.game, rel))

    def write(self, rel, data):
        path = os.path.join(self.game, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)

    def fake_process(self, pid, cmdline=b"", environ=b""):
        d = os.path.join(self.proc, str(pid))
        os.makedirs(d)
        with open(os.path.join(d, "cmdline"), "wb") as fh:
            fh.write(cmdline)
        with open(os.path.join(d, "environ"), "wb") as fh:
            fh.write(environ)

    def clean(self):
        shutil.rmtree(self.root, ignore_errors=True)


print("finding the game")
w = World()
check("a game in a second Steam library is found, with its own prefix",
      w.mod.find_game("4242"), (w.game, w.pfx))
check("and a fix for it is available", w.status(), "available")
w.clean()

w = World(library=None)
check("so is one in the main library", w.mod.find_game("4242"), (w.game, w.pfx))
w.clean()

print()
print("applying")
w = World()
before = w.reg()
check("apply succeeds", w.apply(), 0)
check("the loader goes next to the game", w.read("dinput8.dll"), LOADER)
check("the patch goes in scripts/", w.read("scripts/Patch.asi"), ASI)
check("with its ini", w.read("scripts/Patch.ini"), INI)
check("each game exe gets a native dinput8 override",
      (w.override("Game_Dx9.exe"), w.override("Game_Dx10.exe")),
      ('"native,builtin"', '"native,builtin"'))
check("another exe's overrides are left as they were",
      w.mod.read_override(w.reg(), "Other.exe", "d3d9"), '"native"')
check("the prefix's registry is backed up first",
      open(os.path.join(w.pfx, "user.reg.before-cachy-console-compat")).read(), before)
check("and it then reads as applied", w.status(), "applied")
check("applying again is harmless", w.apply(), 0)
check("still applied", w.status(), "applied")
w.clean()

w = World(exes=(EXE_DX9, b"some other dx10 build"))
check("only the exe that is the supported build gets the override",
      (w.apply(), w.override("Game_Dx9.exe"), w.override("Game_Dx10.exe")),
      (0, '"native,builtin"', None))
w.clean()

print()
print("refusing")
w = World(exes=(b"patched dx9", b"patched dx10"))
check("a build the patch was not made for is unsupported", w.status(), "unsupported build")
check("and apply refuses it", w.apply(), 1)
check("without putting anything in the folder", w.exists("dinput8.dll"), False)
w.clean()

w = World()
w.write("dinput8.dll", b"another mod's loader")
check("another mod's dinput8.dll is a conflict", w.status(), "conflict")
check("apply refuses", w.apply(), 1)
check("that file is untouched", w.read("dinput8.dll"), b"another mod's loader")
check("and nothing else was written either", w.exists("scripts/Patch.asi"), False)
check("nor the registry", w.override("Game_Dx9.exe"), None)
w.clean()

w = World()
w.write("dinput8.dll", LOADER)
w.write("scripts/Patch.asi", ASI)
check("the same files put there by hand are adopted, not a conflict",
      (w.status(), w.apply(), w.status()), ("available", 0, "applied"))
w.clean()

w = World(prefix=False)
check("a game never started has no prefix to set the override in",
      w.status(), "run it once first")
check("so apply waits", w.apply(), 1)
check("--all skips it quietly", w.mod.main(["apply", "--all"]), 0)
check("and leaves its folder alone", w.exists("dinput8.dll"), False)
w.clean()

w = World()
w.fake_process(100, b"reaper\0SteamLaunch\0AppId=4242\0--\0x\0")
check("a running game is not patched under it", w.apply(), 1)
check("nothing written", w.exists("dinput8.dll"), False)
w.clean()

w = World()
w.fake_process(100, b"wineserver\0", b"HOME=/x\0WINEPREFIX=" + w.pfx.encode() + b"\0")
check("nor while anything is still running in its prefix", w.apply(), 1)
w.clean()

w = World()
w.fake_process(100, b"reaper\0SteamLaunch\0AppId=42420\0--\0x\0")
check("another game whose id merely starts the same does not count",
      w.mod.game_running("4242", w.pfx), False)
w.clean()

w = World()
w.mod.FIXES["4242"]["downloads"][0]["sha256"] = "0" * 64
w.mod.urllib.request.urlopen = lambda *a, **k: io.BytesIO(b"tampered")
check("a download that is not the checked file is refused", w.apply(), 1)
check("and nothing from it is installed", w.exists("scripts/Patch.asi"), False)
w.clean()

print()
print("removing")
w = World()
before = w.reg()
w.apply()
check("remove succeeds", w.remove(), 0)
check("the loader is gone", w.exists("dinput8.dll"), False)
check("the patch is gone", w.exists("scripts/Patch.asi"), False)
check("the scripts folder it made is gone", w.exists("scripts"), False)
check("the overrides are taken out",
      (w.override("Game_Dx9.exe"), w.override("Game_Dx10.exe")), (None, None))
check("other overrides untouched", w.mod.read_override(w.reg(), "Other.exe", "d3d9"), '"native"')
check("and it reads as available again", w.status(), "available")
w.clean()

w = World()
with open(os.path.join(w.pfx, "user.reg"), "a") as fh:
    fh.write("\n[Software\\\\Wine\\\\AppDefaults\\\\Game_Dx9.exe\\\\DllOverrides] 1\n"
             "\"dinput8\"=\"builtin\"\n")
w.apply()
check("an override the player had is replaced while applied",
      w.override("Game_Dx9.exe"), '"native,builtin"')
w.remove()
check("and put back exactly on remove", w.override("Game_Dx9.exe"), '"builtin"')
w.clean()

w = World()
w.apply()
w.write("scripts/Patch.ini", b"[Patch]\nPS3Controls=1\n")
check("an ini the player edited still counts as applied", w.status(), "applied")
check("re-applying keeps their edit",
      (w.apply(), w.read("scripts/Patch.ini")), (0, b"[Patch]\nPS3Controls=1\n"))
w.remove()
check("and remove keeps it too", w.read("scripts/Patch.ini"), b"[Patch]\nPS3Controls=1\n")
check("while taking out what it did install", w.exists("dinput8.dll"), False)
w.clean()

w = World()
w.apply()
w.write("dinput8.dll", b"replaced by another mod since")
check("a file replaced after applying is a conflict", w.status(), "conflict")
w.remove()
check("and remove leaves that file alone", w.read("dinput8.dll"), b"replaced by another mod since")
w.clean()

w = World()
check("remove of a fix never applied is refused", w.remove(), 1)
w.clean()

print()
print("the registry text")
mod = World().mod
text = REG
text = mod.set_override(text, "New.exe", "dinput8", '"native,builtin"')
check("a new section is added for an exe with none",
      mod.read_override(text, "new.exe", "DINPUT8"), '"native,builtin"')
check("names are matched without case, as Wine does",
      mod.read_override(text, "NEW.EXE", "dinput8"), '"native,builtin"')
again = mod.set_override(text, "New.exe", "dinput8", '"native,builtin"')
check("setting the same value twice changes nothing", again, text)
check("the file keeps its header", text.startswith("WINE REGISTRY Version 2\n"), True)

print()
print("builds known only by the patch's own check")


def make_pe(va, value, base=0x400000):
    """A minimal 32-bit PE image with one section, holding `value` at `va`."""
    import struct
    vaddr, size, rptr = 0x1000, 0x20000, 0x400
    data = bytearray(rptr + size)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x40)
    data[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HH", data, 0x44, 0x14C, 1)          # machine, sections
    struct.pack_into("<H", data, 0x44 + 16, 224)           # optional header size
    opt = 0x58
    struct.pack_into("<H", data, opt, 0x10B)
    struct.pack_into("<I", data, opt + 28, base)
    sec = opt + 224
    struct.pack_into("<IIII", data, sec + 8, size, vaddr, size, rptr)
    struct.pack_into("<I", data, rptr + (va - base - vaddr), value)
    return bytes(data)


def signature_world(files):
    w = World(exes=())
    for name in os.listdir(w.game):
        os.remove(os.path.join(w.game, name))
    for name, data in files.items():
        with open(os.path.join(w.game, name), "wb") as fh:
            fh.write(data)
    fix = w.mod.FIXES["4242"]
    del fix["exes"]
    fix["signatures"] = [(0x414A55, 0x01CA6FC8, "digital build"),
                         (0x4149F5, 0x01CA4FA0, "retail build")]
    return w


w = signature_world({"Launcher.exe": make_pe(0x414A55, 0x12345678),
                     "TheGame.exe": make_pe(0x414A55, 0x01CA6FC8)})
check("the exe carrying the patch's build value is found, whatever its name",
      w.mod.matching_exes(w.fix, w.game), ["TheGame.exe"])
check("only that exe gets the override, not the launcher next to it",
      (w.apply(), w.override("TheGame.exe"), w.override("Launcher.exe")),
      (0, '"native,builtin"', None))
w.clean()

w = signature_world({"TheGame.exe": make_pe(0x4149F5, 0x01CA4FA0)})
check("either of the patch's builds counts", w.status(), "available")
w.clean()

w = signature_world({"TheGame.exe": make_pe(0x414A55, 0x01CA6FC9),
                     "notes.txt": b"x", "Broken.exe": b"MZ not really"})
check("one value off is an unsupported build", w.status(), "unsupported build")
check("and nothing is installed", (w.apply(), w.exists("dinput8.dll")), (1, False))
w.clean()

w = World()
check("a file that is not a PE image reads as nothing",
      w.mod.read_u32_at_va(os.path.join(w.game, "Game_Dx9.exe"), 0x401376), None)
w.clean()

AC1 = os.path.expanduser("~/.local/share/Steam/steamapps/common/Assassins Creed")
if os.path.isfile(os.path.join(AC1, "AssassinsCreed_Dx10.exe")):
    w = World()
    # EaglePatchAC1's DllMain: MEMCMP32(0x00401375 + 1, 0x42d6) for DX9 and
    # MEMCMP32(0x004013DE + 1, 0x428d) for DX10 -- the reader must find those
    # in the real executables, and not each other's.
    rd = w.mod.read_u32_at_va
    check("the reader finds EaglePatch's own check value in the real AC1 exes",
          (rd(os.path.join(AC1, "AssassinsCreed_Dx9.exe"), 0x401376),
           rd(os.path.join(AC1, "AssassinsCreed_Dx10.exe"), 0x4013DF)), (0x42d6, 0x428d))
    check("and not the other build's",
          (rd(os.path.join(AC1, "AssassinsCreed_Dx9.exe"), 0x4013DF) == 0x428d,
           rd(os.path.join(AC1, "AssassinsCreed_Dx10.exe"), 0x401376) == 0x42d6), (False, False))
    w.clean()
else:
    print("  (skipped: Assassin's Creed is not installed here, so the reader is not checked against it)")

print()
print("the real table")
w = World()
real = w.load()
w.clean()
for appid, fix in real.FIXES.items():
    check(f"{appid}: every download is pinned by a full sha256",
          all(len(d["sha256"]) == 64 for d in fix["downloads"]), True)
    check(f"{appid}: gated by full exe md5s or by the patch's own build check",
          bool(fix.get("exes") or fix.get("signatures"))
          and all(len(m) == 32 for m in fix.get("exes", {}).values())
          and all(isinstance(va, int) and isinstance(v, int)
                  for va, v, _ in fix.get("signatures", [])), True)
    check(f"{appid}: downloads only from GitHub releases over https",
          all(d["url"].startswith("https://github.com/") and "/releases/download/" in d["url"]
              for d in fix["downloads"]), True)
    dests = [x for d in fix["downloads"] for x in d["files"].values()]
    check(f"{appid}: files stay inside the game folder",
          all(not os.path.isabs(x) and ".." not in x.split("/") for x in dests), True)

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) failed.")
    sys.exit(1)
print("All checks passed.")
