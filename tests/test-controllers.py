#!/usr/bin/env python3
"""A game assigns players by controller slot, so what holds js0 matters.

Keyboards with an analog mode publish a gamepad endpoint as part of their USB
descriptor, so it exists from boot and takes the first slot. Steam Input's
virtual pad can only appear once Steam is up, which leaves the controller as
player two: it cannot reach the menus, and the dead device that can will never
send an event. IGNORE_CONTROLLERS hides such a device from console mode only.
These tests pin the id parsing and the sysfs enumeration behind that setting.
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


print("reading the ids people actually write")

check("a single device parses", cd.ignored_pairs("0x31e3/0x1400"),
      {("31e3", "1400")})
check("so does a list", cd.ignored_pairs("0x31e3/0x1400,0x28de/0x1205"),
      {("31e3", "1400"), ("28de", "1205")})
check("whitespace around entries is not part of the id",
      cd.ignored_pairs(" 0x31e3/0x1400 , 0x28de/0x1205 "),
      {("31e3", "1400"), ("28de", "1205")})
check("the 0x is optional, since sysfs prints ids without it",
      cd.ignored_pairs("31e3/1400"), {("31e3", "1400")})
check("case does not matter", cd.ignored_pairs("0x31E3/0x14A0"),
      {("31e3", "14a0")})

# sysfs reports four hex digits, so a hand-written short id has to widen to
# match or the device it names is silently still player one.
check("short ids are padded to what sysfs reports",
      cd.ignored_pairs("0x3e3/0x400"), {("03e3", "0400")})

check("empty hides nothing", cd.ignored_pairs(""), set())
check("so does None", cd.ignored_pairs(None), set())
check("an entry without a slash is not an id and is dropped",
      cd.ignored_pairs("Wooting 80HE"), set())
check("a good entry survives a bad one beside it",
      cd.ignored_pairs("nonsense,0x31e3/0x1400"), {("31e3", "1400")})
check("semicolons work too, for anyone who reaches for them",
      cd.ignored_pairs("0x31e3/0x1400;0x28de/0x1205"),
      {("31e3", "1400"), ("28de", "1205")})


print()
print("enumerating the gamepads the kernel is presenting")


def fake_sysfs(devices):
    """Build a throwaway sysfs tree and point gamepads() at it.

    Real symlinks and real attribute files, because gamepads() resolves the
    class symlink to find the device directory the ids live in.
    """
    root = tempfile.mkdtemp()
    nodes = []
    for spec in devices:
        base = "devices/virtual/input" if spec.get("virtual") else "devices/usb"
        device = os.path.join(root, base, spec["input"])
        os.makedirs(os.path.join(device, "id"), exist_ok=True)
        with open(os.path.join(device, "name"), "w") as fh:
            fh.write(spec["name"] + "\n")
        for key in ("vendor", "product"):
            if spec.get(key) is not None:
                with open(os.path.join(device, "id", key), "w") as fh:
                    fh.write(spec[key] + "\n")
        target = os.path.join(device, spec["js"])
        os.makedirs(target, exist_ok=True)
        link = os.path.join(root, "class", "input", spec["js"])
        os.makedirs(os.path.dirname(link), exist_ok=True)
        os.symlink(target, link)
        nodes.append(link)
    cd.glob.glob = lambda pattern: list(nodes)
    return root


fake_sysfs([
    # Deliberately out of order, and with a two-digit number, because glob
    # returns names in no useful order and sorts js10 before js2 as text.
    {"js": "js10", "input": "input90", "name": "Extra Pad",
     "vendor": "045e", "product": "028e"},
    {"js": "js2", "input": "input80", "name": "Microsoft X-Box 360 pad 1",
     "vendor": "28de", "product": "11ff", "virtual": True},
    {"js": "js0", "input": "input28", "name": "Generic X-Box pad",
     "vendor": "31e3", "product": "1400"},
])

pads = cd.gamepads()
check("every gamepad is found", len(pads), 3)
check("and they come back in slot order, numerically",
      [pad["js"] for pad in pads], ["js0", "js2", "js10"])
check("the keyboard's analog endpoint is what holds the first slot",
      pads[0]["name"], "Generic X-Box pad")
check("with the ids needed to name it in IGNORE_CONTROLLERS",
      (pads[0]["vendor"], pads[0]["product"]), ("31e3", "1400"))
check("a uinput device is marked virtual, since that is Steam Input's pad "
      "rather than something to hide", pads[1]["virtual"], True)
check("while a real device is not", pads[0]["virtual"], False)

# The setting is written as ids, so the two halves have to meet: what sysfs
# reports must be matchable against what the user put in the config.
ignored = cd.ignored_pairs("0x31e3/0x1400")
check("the ids from sysfs match the ids from the config",
      [(pad["vendor"], pad["product"]) in ignored for pad in pads],
      [True, False, False])

# A device can go missing between boots; listing must not raise.
fake_sysfs([{"js": "js0", "input": "input5", "name": "Nameless",
             "vendor": None, "product": None}])
pads = cd.gamepads()
check("a device with no usb id still lists, rather than breaking the list",
      [(pad["js"], pad["vendor"], pad["product"]) for pad in pads],
      [("js0", "", "")])
check("and it cannot be matched by an id, so nothing hides it by accident",
      ("", "") in cd.ignored_pairs("0x31e3/0x1400"), False)

fake_sysfs([])
check("no controllers at all is an empty list", cd.gamepads(), [])

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
    sys.exit(1)
print("all controller tests passed")
