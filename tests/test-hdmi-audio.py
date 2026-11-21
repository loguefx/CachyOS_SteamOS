#!/usr/bin/env python3
"""HDMI audio must follow the saved output, not the primary monitor.

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
cd.WP_RULE = os.path.join(tmpdir, "51-cachy-console-display.conf")
cd.hdmi_ports = lambda: [dict(p) for p in HDMI_PORTS]
cd.match_hdmi = lambda connector=None, model=None: dict(HDMI_PORTS[3])
cd._default_sink = lambda: "alsa_output.pci-0000_0c_00.1.hdmi-stereo"
commands = []
cd._pactl = lambda *args: commands.append(list(args)) or ""
cd._pw_run = lambda args, timeout=8: commands.append(list(args)) or ""
cd._sinks = lambda: [{
    "name": "alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra3",
    "properties": {"node.nick": "Optoma UHD", "object.id": 40},
}]
cd.time.sleep = lambda _s: None
# Two streams playing when the route runs: Big Picture inside the session, and
# a game at the desk. Only the first is console mode's to move.
cd._sink_inputs = lambda: [
    {"index": 7, "properties": {"application.process.id": "700"}},
    {"index": 8, "properties": {"application.process.id": "800"}},
]
cd.in_session = lambda pid: pid == 700

args = types.SimpleNamespace(dry_run=True)
check("dry-run route does not call pactl",
      (cd.cmd_audio_route(args), commands), (0, []))

args = types.SimpleNamespace(dry_run=False)
check("live route switches to extra3",
      cd.cmd_audio_route(args), 0)
check("pactl switches the profile, then moves the session's stream there",
      commands[:2],
      [["set-card-profile", HDMI_CARD, "output:hdmi-stereo-extra3"],
       ["move-sink-input", "7", "alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra3"]])
check("the desk's default output is left alone",
      [c for c in commands if c[:1] == ["set-default-sink"]
       or "default.configured.audio.sink" in c], [])
check("and so is the game playing at the desk",
      [c for c in commands if c[:2] == ["move-sink-input", "8"]], [])
check("the sink is renamed so Steam shows Optoma, not the GPU card",
      any(c[:1] == ["pw-metadata"] or (c and c[0] == "pw-cli") for c in commands), True)
check("a wireplumber rule is written for this HDMI node",
      os.path.exists(cd.WP_RULE), True)

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
check("already on the projector still points the default at it",
      cd.cmd_audio_route(args), 0)
check("already-on does not switch the card profile again",
      any(c[:1] == ["set-card-profile"] for c in commands), False)
check("already-on still moves the session's stream and renames the sink",
      (["move-sink-input", "7", "alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra3"]
       in commands,
       any(c[:1] == ["pw-metadata"] for c in commands)),
      (True, True))
with open(cd.AUDIO_STATE) as fh:
    state = json.load(fh)
check("crash-retry still restores to Odyssey, not extra3",
      state["previous_profile"], "output:hdmi-stereo")

commands.clear()
check("restore puts the desktop HDMI profile back",
      cd.cmd_audio_restore(types.SimpleNamespace(dry_run=False)), 0)
check("with the desk's default untouched, restore only puts the profile back",
      commands, [["set-card-profile", HDMI_CARD, "output:hdmi-stereo"]])
check("state file is removed after restore",
      os.path.exists(cd.AUDIO_STATE), False)
check("the wireplumber rename rule is removed after restore",
      os.path.exists(cd.WP_RULE), False)

commands.clear()
check("a second restore with no state is a no-op",
      (cd.cmd_audio_restore(types.SimpleNamespace(dry_run=False)), commands),
      (0, []))

# Back to the desktop means back to the output it had before console mode,
# whatever Big Picture's output picker (which sets the desktop-wide default)
# or anything else did in between.
BEFORE = "alsa_output.pci-0000_0c_00.1.hdmi-stereo"
for now, label, want in (
        ("alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra3",
         "a default moved onto the TV is put back on leaving",
         [["set-default-sink", BEFORE]]),
        ("alsa_output.usb-HyperX_Cloud_III.analog-stereo",
         "a default moved anywhere else (a headset) is put back too",
         [["set-default-sink", BEFORE]]),
        (BEFORE, "a default already where it was is left alone", [])):
    cd._save_audio_state({"card": HDMI_CARD, "applied": True,
                          "previous_profile": "output:hdmi-stereo",
                          "previous_sink": "alsa_output.pci-0000_0c_00.1.hdmi-stereo",
                          "console_sink": "alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra3"})
    cd._default_sink = lambda now=now: now
    commands.clear()
    cd.cmd_audio_restore(types.SimpleNamespace(dry_run=False))
    check(label, [c for c in commands if c[:1] == ["set-default-sink"]], want)
# A state file whose "before" is the TV itself (a session that began with the
# TV as the default) must not put the desk back onto the TV.
cd._save_audio_state({"card": HDMI_CARD, "applied": True,
                      "previous_profile": "output:hdmi-stereo",
                      "previous_sink": "alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra3",
                      "console_sink": "alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra3"})
cd._default_sink = lambda: "alsa_output.usb-RODE_RODECaster_Duo.analog-stereo"
commands.clear()
cd.cmd_audio_restore(types.SimpleNamespace(dry_run=False))
check("the TV is never what the desk is put back on",
      [c for c in commands if c[:1] == ["set-default-sink"]], [])
cd._default_sink = lambda: "alsa_output.pci-0000_0c_00.1.hdmi-stereo"

# A session that finds the profile already on the TV still records where the
# desktop was, or leaving it would have nothing to put back.
cd._drop_audio_state()
cd._default_sink = lambda: "alsa_output.usb-RODE_RODECaster_Duo.analog-stereo"
cd.cmd_audio_route(args)
cd._default_sink = lambda: "alsa_output.usb-HyperX_Cloud_III.analog-stereo"
cd.cmd_audio_route(args)          # routed again later in the same session
with open(cd.AUDIO_STATE) as fh:
    state = json.load(fh)
check("already on the TV, the desk's output is still remembered, and the "
      "first one recorded wins",
      state.get("previous_sink"), "alsa_output.usb-RODE_RODECaster_Duo.analog-stereo")
cd._drop_audio_state()
cd._default_sink = lambda: "alsa_output.pci-0000_0c_00.1.hdmi-stereo"

print()
print("which streams belong to the session:")
with tempfile.TemporaryDirectory() as proc:
    def fake(pid, ppid, exe):
        d = os.path.join(proc, str(pid))
        os.makedirs(d)
        with open(os.path.join(d, "stat"), "w") as fh:
            fh.write(f"{pid} (x y) S {ppid} 0 0\n")
        os.symlink(exe, os.path.join(d, "exe"))
    fake(10, 1, "/usr/bin/plasmashell")
    fake(20, 1, "/usr/bin/gamescope")
    fake(21, 20, "/usr/bin/bash")
    fake(22, 21, "/home/u/.local/share/Steam/ubuntu12_32/steam")
    fake(23, 22, "/usr/bin/wine64-preloader")
    fake(30, 10, "/usr/bin/firefox")
    fresh_mod = importlib.util.module_from_spec(spec)
    loader.exec_module(fresh_mod)
    check("a game under the session's Steam is in the session",
          fresh_mod.in_session(23, proc_root=proc), True)
    check("Firefox at the desk is not",
          fresh_mod.in_session(30, proc_root=proc), False)
    fake(50, 1, "/usr/bin/some-launcher")
    with open(os.path.join(proc, "50", "environ"), "wb") as fh:
        fh.write(b"HOME=/h\0GAMESCOPE_WAYLAND_DISPLAY=gamescope-0\0")
    check("a session process re-parented away from gamescope is still found "
          "by the environment gamescope gave it",
          fresh_mod.in_session(50, proc_root=proc), True)

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
print("saved AUDIO_DEVICE:")

cd.hdmi_ports = lambda: [dict(p) for p in HDMI_PORTS]
cd._sinks = lambda: [{
    "name": "alsa_output.usb-RODE_RODECaster_Duo.analog-stereo",
    "properties": {"node.nick": "RODECaster Duo",
                   "node.description": "RODECaster Duo"},
}]
cd.read_config = lambda: {
    "AUDIO_DEVICE": "Optoma UHD", "DISPLAY": "HDMI-1",
    "DISPLAY_MODEL": "Optoma Corporation",
}
hit = cd.match_audio()
check("saved Optoma UHD is used",
      (hit.get("port"), hit.get("kind")) if hit else None,
      ("hdmi-output-3", "hdmi"))

cd.read_config = lambda: {
    "AUDIO_DEVICE": "Odyssey G93SC", "DISPLAY": "HDMI-1",
    "DISPLAY_MODEL": "Optoma Corporation",
}
hit = cd.match_audio()
check("saved Samsung is used even though the display is the Optoma",
      (hit.get("port"), hit.get("eld")) if hit else None,
      ("hdmi-output-0", "Odyssey G93SC"))

cd.read_config = lambda: {"AUDIO_DEVICE": "RODECaster Duo"}
hit = cd.match_audio()
check("a USB device is a sink, not an HDMI profile",
      (hit.get("kind"), hit.get("sink")) if hit else None,
      ("sink", "alsa_output.usb-RODE_RODECaster_Duo.analog-stereo"))

cd.match_hdmi = lambda connector=None, model=None: dict(HDMI_PORTS[3])
cd.read_config = lambda: {}
hit = cd.match_audio()
check("empty AUDIO_DEVICE follows the display",
      hit.get("eld") if hit else None, "Optoma UHD")

choices = cd.audio_choices()
check("choices include the three available HDMI monitors",
      [c["id"] for c in choices if c["kind"] == "hdmi"],
      ["Odyssey G93SC", "ZOWIE XL LCD", "Optoma UHD"])
check("choices include the USB device and not a duplicate GPU HDMI sink",
      [c["id"] for c in choices if c["kind"] == "sink"],
      ["RODECaster Duo"])

cd.read_config = lambda: {"AUDIO_DEVICE": "RODECaster Duo"}
commands.clear()
cd._default_sink = lambda: "alsa_output.pci-0000_0c_00.1.hdmi-stereo"
check("USB route does not switch the HDMI card profile",
      cd.cmd_audio_route(types.SimpleNamespace(dry_run=False)), 0)
check("USB route does not touch the HDMI card",
      [c for c in commands if c[:1] == ["set-card-profile"]], [])
check("USB route moves the session's stream to the headset, not the default",
      (["move-sink-input", "7", "alsa_output.usb-RODE_RODECaster_Duo.analog-stereo"]
       in commands, [c for c in commands if c[:1] == ["set-default-sink"]]),
      (True, []))


print()
print("the microphone:")

# PipeWire publishes a .monitor source for every sink. Offering those as
# microphones would be a list of loopbacks, most of them named after outputs.
SOURCES = [
    {"name": "alsa_output.usb-RODE_RODECaster_Duo.analog-stereo.monitor",
     "properties": {"device.class": "monitor", "node.nick": "RODECaster Duo"}},
    {"name": "alsa_input.usb-RODE_RODECaster_Duo.analog-stereo",
     "properties": {"device.class": "sound", "node.nick": "RODECaster Duo"}},
    {"name": "alsa_output.pci-0000_0c_00.1.hdmi-stereo.monitor",
     "properties": {"device.class": "monitor", "node.nick": "Odyssey G93SC"}},
    {"name": "alsa_input.usb-HyperX_Cloud_III_S.mono-fallback",
     "properties": {"device.class": "sound",
                    "node.nick": "HyperX Cloud III S Wireless"}},
]
cd._sources_raw = lambda: [dict(s) for s in SOURCES]

check("monitor sources are not offered as microphones",
      [s["name"] for s in cd._sources()],
      ["alsa_input.usb-RODE_RODECaster_Duo.analog-stereo",
       "alsa_input.usb-HyperX_Cloud_III_S.mono-fallback"])
check("the choices are labelled by nick",
      [c["id"] for c in cd.audio_input_choices()],
      ["RODECaster Duo", "HyperX Cloud III S Wireless"])

cd.read_config = lambda: {}
check("no saved microphone leaves input alone", cd.match_audio_input(), None)
check("and nothing is saved to report", cd.saved_audio_input_device(), None)

cd.read_config = lambda: {"AUDIO_INPUT_DEVICE": "HyperX Cloud III S Wireless"}
check("a saved headset resolves to its capture source, not its monitor",
      cd.match_audio_input(), "alsa_input.usb-HyperX_Cloud_III_S.mono-fallback")

cd.read_config = lambda: {"AUDIO_INPUT_DEVICE": "RODECaster Duo"}
check("the RODE resolves to its input even though a monitor shares the name",
      cd.match_audio_input(), "alsa_input.usb-RODE_RODECaster_Duo.analog-stereo")

cd.read_config = lambda: {"AUDIO_INPUT_DEVICE": "Some Unplugged Mic"}
check("an absent microphone falls back to the session default rather than "
      "picking another one", cd.match_audio_input(), None)

# Output and input are independent: saving a headset mic must not drag console
# mode's speakers off the projector.
cd.read_config = lambda: {"AUDIO_DEVICE": "Optoma UHD",
                          "AUDIO_INPUT_DEVICE": "HyperX Cloud III S Wireless",
                          "DISPLAY": "HDMI-1",
                          "DISPLAY_MODEL": "Optoma Corporation"}
hit = cd.match_audio()
check("the saved output is still the projector",
      hit.get("eld") if hit else None, "Optoma UHD")
check("while input is the headset",
      cd.match_audio_input(), "alsa_input.usb-HyperX_Cloud_III_S.mono-fallback")

print()
print("naming the sink a target plays through:")

# A TV resolves to an HDMI port, which is what routing wants -- it sets a card
# profile -- but pinning a single stream has to name a sink. Without this the
# resolve printed nothing and voice chat was never pinned to the console's output.
HDMI_SINKS = [
    {"name": "alsa_output.usb-RODE_RODECaster_Duo.analog-stereo",
     "properties": {"node.nick": "RODECaster Duo"}},
    {"name": "alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra3",
     "properties": {"node.nick": "Optoma UHD",
                    "node.description": "Navi 31 HDMI/DP Audio"}},
]
cd._sinks = lambda: [dict(s) for s in HDMI_SINKS]

optoma = {"kind": "hdmi", "card": HDMI_CARD, "port": "hdmi-output-3",
          "eld": "Optoma UHD", "profile": "output:hdmi-stereo-extra3"}
check("an HDMI port finds its card's sink for that profile",
      cd.sink_for(optoma),
      "alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra3")

# Another display on the same card, whose sink the current profile has not
# created. Pinning voice chat to the Optoma's sink because it is the only one
# there would put the sound on the wrong screen, so nothing is the right answer.
check("a display whose sink does not exist resolves to nothing",
      cd.sink_for({"kind": "hdmi", "card": HDMI_CARD, "port": "hdmi-output-1",
                   "eld": "ZOWIE XL LCD",
                   "profile": "output:hdmi-stereo-extra1"}), None)

check("a target that already names a sink is taken at its word",
      cd.sink_for({"kind": "sink", "sink": "alsa_output.some.thing"}),
      "alsa_output.some.thing")
check("nothing resolved means no sink", cd.sink_for(None), None)

# A card that does not name its sinks after its profiles: the ELD is what the
# user picked in the settings window, so it is the remaining way in.
cd._sinks = lambda: [{"name": "alsa_output.weird-name",
                      "properties": {"node.nick": "Optoma UHD"}}]
check("otherwise the ELD is matched against the sinks",
      cd.sink_for(optoma), "alsa_output.weird-name")

cd._sinks = lambda: [dict(s) for s in HDMI_SINKS]
check("and an ELD that matches nothing stays unresolved",
      cd.sink_for({"kind": "hdmi", "eld": "No Such Display"}), None)

print()
print("every screen at once (pro-audio):")

# The stereo profiles open one port at a time, so Steam's list only ever held
# the screen console mode had switched to: with the Odyssey saved, the projector
# could not be picked from the couch. Pro-audio opens all of them.
real_glob, real_open = cd.glob.glob, open
PCM_INFO = {
    "/proc/asound/card0/pcm3p/info": "device: 3\nname: HDMI 0\n",
    "/proc/asound/card0/pcm7p/info": "device: 7\nname: HDMI 1\n",
    "/proc/asound/card0/pcm8p/info": "device: 8\nname: HDMI 2\n",
    "/proc/asound/card0/pcm9p/info": "device: 9\nname: HDMI 3\n",
}
cd.glob.glob = lambda pattern: sorted(PCM_INFO) if "asound" in pattern else real_glob(pattern)
cd.open = lambda path, *a, **kw: (
    __import__("io").StringIO(PCM_INFO[path]) if path in PCM_INFO
    else real_open(path, *a, **kw))
check("HDMI N is mapped to its PCM device, not to N",
      cd._hdmi_pcms("0"), {0: 3, 1: 7, 2: 8, 3: 9})

# Earlier sections replaced hdmi_ports and friends; this needs the real ones.
fresh = importlib.util.module_from_spec(spec)
loader.exec_module(fresh)
fresh.glob.glob, fresh.open = cd.glob.glob, cd.open
fresh._pactl_json = lambda what: [{
    "name": HDMI_CARD, "active_profile": "output:hdmi-stereo",
    "properties": {"alsa.card": "0"},
    "profiles": {"output:hdmi-stereo": {}, "pro-audio": {}},
    "ports": {
        "hdmi-output-0": {"type": "HDMI", "availability": "available",
                          "properties": {"device.product.name": "Odyssey G93SC"},
                          "profiles": ["output:hdmi-stereo"]},
        "hdmi-output-2": {"type": "HDMI", "availability": "not available",
                          "properties": {},
                          "profiles": ["output:hdmi-stereo-extra2"]},
        "hdmi-output-3": {"type": "HDMI", "availability": "available",
                          "properties": {"device.product.name": "Optoma UHD"},
                          "profiles": ["output:hdmi-stereo-extra3"]},
    },
}] if what == "cards" else []
check("each port names its pro-audio sink by PCM device",
      [p["pro_sink"] for p in fresh.hdmi_ports()],
      ["alsa_output.pci-0000_0c_00.1.pro-output-3",
       "alsa_output.pci-0000_0c_00.1.pro-output-8",
       "alsa_output.pci-0000_0c_00.1.pro-output-9"])

rule = fresh._pro_rule_body(fresh.hdmi_ports())
check("the rule names each connected screen after its ELD, in stereo",
      ('node.description = "Optoma UHD"' in rule,
       'node.description = "Odyssey G93SC"' in rule,
       rule.count("audio.position = [ FL FR ]")),
      (True, True, 2))
check("a port with no screen is switched off rather than listed",
      rule.count("node.disabled = true"), 1)

fresh.PRO_RULE = os.path.join(tmpdir, "52-cachy-console-hdmi-outputs.conf")
fresh.AUDIO_STATE = os.path.join(tmpdir, "pro-route.json")
fresh.time.sleep = lambda _s: None
fresh._default_sink = lambda: "alsa_output.pci-0000_0c_00.1.hdmi-stereo"
pro_commands = []
profile = {"now": "output:hdmi-stereo"}


def pro_pactl(*args):
    pro_commands.append(list(args))
    if args[:1] == ("set-card-profile",):
        profile["now"] = args[2]
    return ""


fresh._pactl = pro_pactl
fresh._sink_inputs = lambda: [
    {"index": 7, "properties": {"application.process.id": "700"}},
    {"index": 8, "properties": {"application.process.id": "800"}}]
fresh.in_session = lambda pid: pid == 700
fresh._pw_run = lambda args, timeout=8: pro_commands.append(list(args)) or ""
fresh._card_profile = lambda card: profile["now"]
fresh._sinks = lambda: ([{"name": "alsa_output.pci-0000_0c_00.1.pro-output-3"},
                         {"name": "alsa_output.pci-0000_0c_00.1.pro-output-9"}]
                        if profile["now"] == "pro-audio" else [])
fresh.read_config = lambda: {"AUDIO_DEVICE": "Optoma UHD"}
real_ports = fresh.hdmi_ports
fresh.hdmi_ports = lambda: [{**p, "card_profile": profile["now"]} for p in real_ports()]

check("routing opens every screen and defaults to the saved one",
      fresh.cmd_audio_route(types.SimpleNamespace(dry_run=False)), 0)
check("WirePlumber is restarted for a new rule, then the card switched",
      [c for c in pro_commands if c[0] in ("systemctl", "set-card-profile")],
      [["systemctl", "--user", "restart", "wireplumber"],
       ["set-card-profile", HDMI_CARD, "pro-audio"]])
check("the session plays on the projector's own pro-output",
      ["move-sink-input", "7", "alsa_output.pci-0000_0c_00.1.pro-output-9"]
      in pro_commands, True)
check("while the desk keeps its default and its own stream",
      [c for c in pro_commands if c[:1] == ["set-default-sink"]
       or c[:2] == ["move-sink-input", "8"]], [])
check("voice chat pins to the same sink",
      fresh.sink_for(fresh.match_audio()),
      "alsa_output.pci-0000_0c_00.1.pro-output-9")

pro_commands.clear()
fresh.read_config = lambda: {"AUDIO_DEVICE": "Odyssey G93SC"}
fresh.cmd_audio_route(types.SimpleNamespace(dry_run=False))
check("a second route with the same screens neither restarts nor switches",
      [c for c in pro_commands if c[0] in ("systemctl", "set-card-profile")], [])
check("but does move the session to the newly saved screen",
      ["move-sink-input", "7", "alsa_output.pci-0000_0c_00.1.pro-output-3"]
      in pro_commands, True)

pro_commands.clear()
fresh.cmd_audio_restore(types.SimpleNamespace(dry_run=False))
check("leaving puts the desktop's stereo profile back",
      pro_commands[0], ["set-card-profile", HDMI_CARD, "output:hdmi-stereo"])
check("the naming rule stays, so the next session needs no restart",
      os.path.exists(fresh.PRO_RULE), True)

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
    sys.exit(1)
print("all HDMI audio tests passed")
