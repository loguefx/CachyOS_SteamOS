#!/usr/bin/env python3
"""Discord needs a mouse layout on the Steam Controller, or the trackpad is dead.

Steam applies a per-app controller layout to whatever has focus, and a non-Steam
shortcut with none picked gets the last-resort gamepad template: the right
trackpad becomes a joystick on a virtual pad, which Discord ignores, so the
pointer sits still and nothing clicks. pad-layouts fills in the Web Browser
template for the shortcuts in MOUSE_LAYOUT_APPS, in the files Steam reads for
the Steam Controller, and never over a layout the user chose.
"""

import importlib.machinery
import importlib.util
import os
import struct
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


def shortcut(index, appid, name):
    return (b"\x00" + str(index).encode() + b"\x00"
            + b"\x02appid\x00" + struct.pack("<I", appid)
            + b"\x01AppName\x00" + name.encode() + b"\x00"
            + b"\x01Exe\x00\"/usr/bin/x\"\x00"
            + b"\x00tags\x00\x08"
            + b"\x08")


def shortcuts_vdf(*entries):
    body = b"".join(shortcut(i, appid, name) for i, (appid, name) in enumerate(entries))
    return b"\x00shortcuts\x00" + body + b"\x08\x08"


TRITON_PREFS = '"ControllerPersonalization"\n{\n\t"name"\t\t"Steam Controller"\n' \
               '\t"triton_gyro_hw_cal"\t\t"100"\n}\n'
DUALSENSE_PREFS = '"ControllerPersonalization"\n{\n' \
                  '\t"name"\t\t"#SettingsController_SteamController"\n}\n'
GTA_CHOICE = '"controller_config"\n{\n\t"12210"\n\t{\n' \
             '\t\t"workshop"\t\t"2793455456"\n\t}\n}\n'


def steam(tmp, shortcuts=((3214031495, "Discord"), (3278583129, "Exit Console Mode"))):
    root = os.path.join(tmp, "Steam")
    user = os.path.join(root, "userdata", "173729136", "config")
    pads = os.path.join(root, "steamapps", "common", "Steam Controller Configs",
                        "173729136", "config")
    os.makedirs(user)
    os.makedirs(pads)
    with open(os.path.join(user, "shortcuts.vdf"), "wb") as fh:
        fh.write(shortcuts_vdf(*shortcuts))
    files = {
        "preferences_FXA996200467C.vdf": TRITON_PREFS,
        "configset_FXA996200467C.vdf": GTA_CHOICE,
        "preferences_DSe8473ab2e372.vdf": DUALSENSE_PREFS,
        "configset_DSe8473ab2e372.vdf": '"controller_config"\n{\n}\n',
    }
    for name, text in files.items():
        with open(os.path.join(pads, name), "w") as fh:
            fh.write(text)
    return root, pads


def layouts(pads, name):
    with open(os.path.join(pads, name)) as fh:
        return cd.read_text_vdf(fh.read()).get("controller_config", {})


print("reading Steam's own files")

with tempfile.TemporaryDirectory() as tmp:
    root, pads = steam(tmp)
    found = cd.steam_shortcuts(os.path.join(root, "userdata", "173729136",
                                            "config", "shortcuts.vdf"))
    check("shortcut appids come out unsigned, the form Steam logs and keys by",
          found, [(3214031495, "Discord"), (3278583129, "Exit Console Mode")])
check("a missing shortcuts.vdf is no shortcuts, not a crash",
      cd.steam_shortcuts("/nonexistent/shortcuts.vdf"), [])
tree = cd.read_text_vdf(GTA_CHOICE)
check("a text layout file parses", tree,
      {"controller_config": {"12210": {"workshop": "2793455456"}}})
check("and writes back to the same thing", cd.read_text_vdf(cd.write_text_vdf(tree)),
      tree)

print("\ngiving Discord the mouse layout")

with tempfile.TemporaryDirectory() as tmp:
    root, pads = steam(tmp)
    report = cd.set_mouse_layouts(root, ["Discord"])
    check("the Steam Controller's own file gets Discord's layout",
          layouts(pads, "configset_FXA996200467C.vdf").get("discord"),
          {"template": "controller_neptune_webbrowser.vdf"})
    check("keyed by name: Steam looks non-Steam shortcuts up that way and "
          "ignores an appid key",
          "3214031495" in layouts(pads, "configset_FXA996200467C.vdf"), False)
    check("and so does the file for Steam Controllers Steam has not seen yet",
          layouts(pads, "configset_controller_triton.vdf"),
          {"discord": {"template": "controller_neptune_webbrowser.vdf"}})
    check("the layout already chosen for another game is kept",
          layouts(pads, "configset_FXA996200467C.vdf").get("12210"),
          {"workshop": "2793455456"})
    check("a DualSense is left alone: its preferences also say Steam Controller",
          layouts(pads, "configset_DSe8473ab2e372.vdf"), {})
    check("each change is reported", len(report), 2)
    check("a second run changes nothing", cd.set_mouse_layouts(root, ["Discord"]), [])

with tempfile.TemporaryDirectory() as tmp:
    root, pads = steam(tmp)
    with open(os.path.join(pads, "configset_FXA996200467C.vdf"), "w") as fh:
        fh.write('"controller_config"\n{\n\t"discord"\n\t{\n'
                 '\t\t"template"\t\t"controller_neptune_gamepad+mouse.vdf"\n\t}\n}\n')
    cd.set_mouse_layouts(root, ["Discord"])
    check("a layout the user picked for Discord is never replaced",
          layouts(pads, "configset_FXA996200467C.vdf")["discord"],
          {"template": "controller_neptune_gamepad+mouse.vdf"})

with tempfile.TemporaryDirectory() as tmp:
    root, pads = steam(tmp)
    cd.set_mouse_layouts(root, ["discord"])
    check("names match without regard to case",
          "discord" in layouts(pads, "configset_FXA996200467C.vdf"), True)

with tempfile.TemporaryDirectory() as tmp:
    root, pads = steam(tmp)
    cd.set_mouse_layouts(root, ["3278583129"])
    check("an appid works as well as a name",
          "exit console mode" in layouts(pads, "configset_FXA996200467C.vdf"), True)
check("punctuation is dropped from the name, as in Steam's own entries",
      cd.shortcut_layout_key("zShaderCacheKiller.sh"), "zshadercachekillersh")

with tempfile.TemporaryDirectory() as tmp:
    root, pads = steam(tmp, shortcuts=((3278583129, "Exit Console Mode"),))
    check("no Discord shortcut, nothing written",
          (cd.set_mouse_layouts(root, ["Discord"]),
           os.path.exists(os.path.join(pads, "configset_controller_triton.vdf"))),
          ([], False))

with tempfile.TemporaryDirectory() as tmp:
    root, pads = steam(tmp)
    before = layouts(pads, "configset_FXA996200467C.vdf")
    report = cd.set_mouse_layouts(root, ["Discord"], dry_run=True)
    check("a dry run reports without writing",
          (len(report), layouts(pads, "configset_FXA996200467C.vdf")), (2, before))

print("\nthe setting")

with tempfile.TemporaryDirectory() as tmp:
    cd.CONFIG_PATH = os.path.join(tmp, "config")
    check("unset means Discord and Spotify", cd.mouse_apps(), ["Discord", "Spotify"])
    with open(cd.CONFIG_PATH, "w") as fh:
        fh.write("MOUSE_LAYOUT_APPS=\n")
    check("empty turns it off", cd.mouse_apps(), [])
    with open(cd.CONFIG_PATH, "w") as fh:
        fh.write("MOUSE_LAYOUT_APPS=Discord, Vesktop\n")
    check("a list is split on commas", cd.mouse_apps(), ["Discord", "Vesktop"])

if FAILURES:
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1)
print("\nall pad layout tests passed")
