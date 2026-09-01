#!/usr/bin/env python3
"""HDMI audio must follow the saved gamescope display, not the primary monitor.

AMD (and most GPU) HDMI audio exposes one stereo profile at a time. Steam's
output list is that profile plus USB devices, so the projector never appears
until the card is switched to the port whose ELD matches the saved display.
These tests pin that matching and the route/restore pactl sequence without
touching the live sound server.
"""

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import types

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


HDMI_CARD = "alsa_card.pci-0000_0c_00.1"

HDMI_PORTS = [
    {"card": HDMI_CARD, "card_profile": "output:hdmi-stereo",
     "port": "hdmi-output-0", "eld": "Odyssey G93SC",
     "available": True, "profile": "output:hdmi-stereo"},
    {"card": HDMI_CARD, "card_profile": "output:hdmi-stereo",
     "port": "hdmi-output-1", "eld": "ZOWIE XL LCD",
     "available": True, "profile": "output:hdmi-stereo-extra1"},
    {"card": HDMI_CARD, "card_profile": "output:hdmi-stereo",
     "port": "hdmi-output-2", "eld": "",
     "available": False, "profile": "output:hdmi-stereo-extra2"},
    {"card": HDMI_CARD, "card_profile": "output:hdmi-stereo",
     "port": "hdmi-output-3", "eld": "Optoma UHD",
     "available": True, "profile": "output:hdmi-stereo-extra3"},
]


print("parsing Pulse/PipeWire card JSON:")

cd._pactl_json = lambda what: [{
    "name": HDMI_CARD,
    "active_profile": "output:hdmi-stereo",
    "ports": {
        "hdmi-output-0": {
            "type": "HDMI", "availability": "available",
            "properties": {"device.product.name": "Odyssey G93SC"},
            "profiles": ["output:hdmi-stereo"],
        },
        "hdmi-output-3": {
            "type": "HDMI", "availability": "available",
            "properties": {"device.product.name": "Optoma UHD"},
            "profiles": ["output:hdmi-stereo-extra3"],
        },
        "analog-output-speaker": {
            "type": "Speaker", "availability": "unknown",
            "properties": {},
            "profiles": ["output:analog-stereo"],
        },
    },
}] if what == "cards" else []

parsed = cd.hdmi_ports()
check("analog ports are ignored",
      [p["port"] for p in parsed], ["hdmi-output-0", "hdmi-output-3"])
check("ELD names come from device.product.name",
      [p["eld"] for p in parsed], ["Odyssey G93SC", "Optoma UHD"])
check("the stereo profile listed on the port is the one we would set",
      [p["profile"] for p in parsed],
      ["output:hdmi-stereo", "output:hdmi-stereo-extra3"])


print()
print("matching the saved display to an HDMI port:")

cd.hdmi_ports = lambda: [dict(p) for p in HDMI_PORTS]
cd.displays = lambda: []
cd.saved_connector = lambda: "HDMI-1"
cd.read_config = lambda: {"DISPLAY": "HDMI-1",
                          "DISPLAY_MODEL": "Optoma Corporation"}

hit = cd.match_hdmi("HDMI-1", "Optoma Corporation")
check("Optoma matches hdmi-output-3 extra3, not the Odyssey primary",
      (hit["port"], hit["profile"]) if hit else None,
      ("hdmi-output-3", "output:hdmi-stereo-extra3"))

cd.hdmi_ports = lambda: [
    {**HDMI_PORTS[3], "available": False},
    HDMI_PORTS[0], HDMI_PORTS[1],
]
check("an unavailable projector port is not used",
      cd.match_hdmi("HDMI-1", "Optoma Corporation"), None)

cd.hdmi_ports = lambda: [dict(p) for p in HDMI_PORTS]
cd.read_config = lambda: {"DISPLAY": "HDMI-1"}
check("HDMI-1 with no model cannot guess which extraN port to use",
      cd.match_hdmi("HDMI-1", None), None)

check("a Samsung ELD is not picked for an Optoma save",
      cd.score_port(HDMI_PORTS[0], "Optoma Corporation", "HDMI-1"), 0)
check("token overlap scores Optoma UHD against Optoma Corporation",
      cd.score_port(HDMI_PORTS[3], "Optoma Corporation", "HDMI-1") > 0, True)

cd.saved_connector = lambda: None
cd.read_config = lambda: {}
check("no saved display means no match",
      cd.match_hdmi(None, None), None)


print()
print("routing and restoring:")

tmpdir = tempfile.mkdtemp()
cd.AUDIO_STATE = os.path.join(tmpdir, "cachy-console-audio-route.json")
cd.hdmi_ports = lambda: [dict(p) for p in HDMI_PORTS]
cd.match_hdmi = lambda connector=None, model=None: dict(HDMI_PORTS[3])
cd._default_sink = lambda: "alsa_output.pci-0000_0c_00.1.hdmi-stereo"
commands = []
cd._pactl = lambda *args: commands.append(list(args)) or ""
cd._sinks = lambda: [{
    "name": "alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra3",
    "properties": {"node.nick": "Optoma UHD"},
}]
cd.time.sleep = lambda _s: None

args = types.SimpleNamespace(dry_run=True)
check("dry-run route does not call pactl",
      (cd.cmd_audio_route(args), commands), (0, []))

args = types.SimpleNamespace(dry_run=False)
check("live route switches to extra3 and sets that sink as default",
      cd.cmd_audio_route(args), 0)
check("pactl order is profile then default sink",
      commands,
      [["set-card-profile", HDMI_CARD, "output:hdmi-stereo-extra3"],
       ["set-default-sink", "alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra3"]])

with open(cd.AUDIO_STATE) as fh:
    state = json.load(fh)
check("state remembers the desktop HDMI profile",
      (state["previous_profile"], state["previous_sink"], state["applied"]),
      ("output:hdmi-stereo", "alsa_output.pci-0000_0c_00.1.hdmi-stereo", True))

# A second start while already switched must not forget the original desktop
# device: otherwise restore would "restore" extra3.
HDMI_PORTS_SWITCHED = [{**p, "card_profile": "output:hdmi-stereo-extra3"}
                       for p in HDMI_PORTS]
cd.hdmi_ports = lambda: [dict(p) for p in HDMI_PORTS_SWITCHED]
cd.match_hdmi = lambda connector=None, model=None: {
    **HDMI_PORTS[3], "card_profile": "output:hdmi-stereo-extra3"}
commands.clear()
check("already on the projector is a no-op",
      cd.cmd_audio_route(args), 0)
check("already-on does not rewrite pactl", commands, [])
with open(cd.AUDIO_STATE) as fh:
    state = json.load(fh)
check("crash-retry still restores to Odyssey, not extra3",
      state["previous_profile"], "output:hdmi-stereo")

commands.clear()
check("restore puts the desktop HDMI profile back",
      cd.cmd_audio_restore(types.SimpleNamespace(dry_run=False)), 0)
check("restore pactl order is profile then original sink",
      commands,
      [["set-card-profile", HDMI_CARD, "output:hdmi-stereo"],
       ["set-default-sink", "alsa_output.pci-0000_0c_00.1.hdmi-stereo"]])
check("state file is removed after restore",
      os.path.exists(cd.AUDIO_STATE), False)

check("a second restore with no state is a no-op",
      (cd.cmd_audio_restore(types.SimpleNamespace(dry_run=False)), commands[2:]),
      (0, []))

print()
print("sink matching:")
target = {"card": HDMI_CARD, "profile": "output:hdmi-stereo-extra3",
          "eld": "Optoma UHD"}
check("sink on this card matches by name prefix",
      cd._sink_matches({"name": "alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra3",
                        "properties": {}}, target), True)
check("a USB headset does not match the GPU card",
      cd._sink_matches({"name": "alsa_output.usb-RODE_RODECaster_Duo.analog-stereo",
                        "properties": {"node.nick": "RODECaster Duo"}}, target),
      False)


print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
    sys.exit(1)
print("all HDMI audio tests passed")
