#!/usr/bin/env python3
"""Tests for cachy-console-audio's muting decisions.

This daemon reaches into the user's audio and mutes things, so the interesting
cases are the ones where it must *not* act: a browser playing music, Steam's own
interface sounds, a single game, or focus resting on the library. Getting those
wrong means silence the user cannot explain and cannot easily undo, which is far
worse than the problem being solved. Every mute must also be reversible, so the
restore paths are checked as carefully as the mute paths.

Real games are not needed: streams, focus and pactl are all faked, so the logic
runs exactly as it would live.
"""

import importlib.machinery
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "bin", "cachy-console-audio")
loader = importlib.machinery.SourceFileLoader("pa", TARGET)
spec = importlib.util.spec_from_loader("pa", loader)
pa = importlib.util.module_from_spec(spec)
loader.exec_module(pa)

FAILURES = []

# Kept before any test swaps it out, so the dry-run case can exercise the real
# implementation rather than a stand-in.
real_set_mute = pa.set_mute


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"        got  = {got!r}")
        print(f"        want = {want!r}")
        FAILURES.append(label)


class World:
    """A fake machine: some streams, some games, a focused app."""

    def __init__(self, streams=(), owners=None, focus=None, session=True,
                 never=(), capture=(), devices=(None, None), names=None,
                 pin=True):
        self.streams = list(streams)
        self.owners = dict(owners or {})     # pid -> appid (None = not a game)
        self.focus = focus
        self.session = session
        self.mute_calls = []
        self.logs = []
        self.capture = list(capture)
        self.devices = devices               # (sink, source) console mode wants
        self.names = dict(names or {})       # (kind, index) -> device name
        self.moves = []

        pa.source_outputs = lambda: list(self.capture)
        pa.pin_voice_enabled = lambda: pin
        pa.device_names = lambda: dict(self.names)
        pa.move_stream = self._move
        # Resolving the target shells out to cachy-console-display, which is not
        # what these tests are about: they are about what gets moved where.
        pa.AudioFocus.console_devices = lambda _self: self.devices

        pa.sink_inputs = lambda: list(self.streams)
        pa.steam_appid = lambda pid, limit=24: self.owners.get(pid)
        pa.gamescope_displays = lambda: [":2"] if self.session else []
        pa.focused_appid = lambda display: self.focus
        pa.set_mute = self._set_mute
        pa.log = self.logs.append
        # AUDIO_NEVER_MUTE and /proc are both stated here rather than read from
        # the machine, which would make these tests depend on the config and the
        # process table of whoever runs them.
        names = {str(n).lower() for n in never if not str(n).isdigit()}
        appids = {int(n) for n in never if str(n).isdigit()}
        pa.never_mute = lambda: (names, appids)
        pa.process_names = lambda pid: set()

    def _move(self, kind, index, device, dry_run):
        """pactl move-sink-input / move-source-output, as a fake.

        A stream records the device *index* it sits on while the config names
        devices, so the fake has to keep both sides consistent or a moved stream
        would look unmoved and be moved again forever.
        """
        self.moves.append((kind, index, device))
        if dry_run:
            return True
        target = next((idx for (k, idx), name in self.names.items()
                       if k == kind and name == device), None)
        if target is None:
            target = 1 + max([idx for (k, idx) in self.names if k == kind] or [0])
            self.names[(kind, target)] = device
        for group in (self.streams, self.capture):
            for s in group:
                if s.index == index:
                    s.device = target
        return True

    def _set_mute(self, index, muted, dry_run):
        self.mute_calls.append((index, muted))
        for stream in self.streams:
            if stream.index == index:
                stream.muted = muted
        return True

    def add(self, index, pid, name="game", muted=False):
        self.streams.append(pa.Stream(index, pid, muted, name))

    def drop(self, index):
        self.streams = [s for s in self.streams if s.index != index]

    def muted(self):
        return sorted(s.index for s in self.streams if s.muted)


def stream(index, pid, name="game", muted=False, device=None):
    return pa.Stream(index, pid, muted, name, device)


# Two games and a browser: pids 100 and 200 are games, 900 is Firefox.
GAME_A, GAME_B = 4000, 5000


def two_games(focus=GAME_A, session=True):
    world = World(
        streams=[stream(1, 100, "GameA"), stream(2, 200, "GameB")],
        owners={100: GAME_A, 200: GAME_B},
        focus=focus, session=session)
    return world, pa.AudioFocus()


print("leaving things alone:")

world = World(streams=[stream(1, 900, "Firefox")], owners={900: None}, focus=None)
focus = pa.AudioFocus()
focus.poll()
check("a browser on its own is never muted", world.mute_calls, [])

world = World(streams=[stream(1, 100, "GameA")], owners={100: GAME_A}, focus=GAME_A)
focus = pa.AudioFocus()
focus.poll()
check("a single game is never muted", world.mute_calls, [])

world = World(
    streams=[stream(1, 100, "GameA"), stream(2, 200, "GameB"), stream(3, 900, "Firefox")],
    owners={100: GAME_A, 200: GAME_B, 900: None}, focus=GAME_A)
focus = pa.AudioFocus()
focus.poll()
check("the browser is untouched while games are managed", world.muted(), [2])

world = World(
    streams=[stream(1, 100, "GameA"), stream(2, 200, "GameB"), stream(3, 300, "Steam")],
    owners={100: GAME_A, 200: GAME_B, 300: 769}, focus=GAME_A)
focus = pa.AudioFocus()
focus.poll()
check("Steam's own interface sounds keep playing", world.muted(), [2])

print()
print("focusing a game:")

world, focus = two_games(focus=GAME_A)
focus.poll()
check("the unfocused game is muted", world.muted(), [2])
check("the focused game is left audible", world.streams[0].muted, False)

world.focus = GAME_B
focus.poll()
check("switching focus mutes the other one", world.muted(), [1])
check("and unmutes the one switched to", world.streams[1].muted, False)

before = len(world.mute_calls)
focus.poll()
check("a repeat poll changes nothing", len(world.mute_calls), before)

print()
print("focus that is not a game:")

world, focus = two_games(focus=GAME_A)
focus.poll()
check("starting state: B muted", world.muted(), [2])
world.focus = 769                     # the Big Picture library
focus.poll()
check("opening the library holds the mutes", world.muted(), [2])
world.focus = None                    # gamescope reports nothing focused
focus.poll()
check("unknown focus also holds the mutes", world.muted(), [2])
world.focus = GAME_B
focus.poll()
check("returning to a game applies again", world.muted(), [1])

print()
print("restoring:")

world, focus = two_games(focus=GAME_A)
focus.poll()
check("B is muted to begin with", world.muted(), [2])
world.drop(1)                         # game A quits
focus.poll()
check("when one game is left, its audio comes back", world.muted(), [])
check("and we stop tracking it", focus.muted_appids, set())

world, focus = two_games(focus=GAME_A)
focus.poll()
world.session = False                 # gamescope exits with games still up
focus.poll()
check("losing the session restores everything", world.muted(), [])

world, focus = two_games(focus=GAME_A)
focus.poll()
check("muted before shutdown", world.muted(), [2])
focus.unmute_all()                    # what the daemon does as it exits
check("shutting down unmutes what we muted", world.muted(), [])
check("nothing is left tracked", focus.muted_appids, set())

print()
print("streams appearing later:")

world, focus = two_games(focus=GAME_A)
focus.poll()
world.add(3, 200, "GameB second device")
focus.poll()
check("a new stream from a muted game is muted too", world.muted(), [2, 3])

world.add(4, 100, "GameA second device")
focus.poll()
check("but a new stream from the focused game plays", world.streams[-1].muted, False)

print()
print("never muting voice chat:")

# Discord has to be started inside gamescope to be visible there, which means
# launching it from the library -- so Steam gives it a SteamGameId and it looks
# like a game. This is the case AUDIO_NEVER_MUTE exists for.
DISCORD = 3278583129

world = World(streams=[stream(1, 100, "GameA"), stream(2, 700, "Discord")],
              owners={100: GAME_A, 700: DISCORD}, focus=GAME_A)
focus = pa.AudioFocus()
focus.poll()
check("without an exemption Discord is muted, which is the trap",
      world.muted(), [2])

world = World(streams=[stream(1, 100, "GameA"), stream(2, 700, "Discord")],
              owners={100: GAME_A, 700: DISCORD}, focus=GAME_A, never=("Discord",))
focus = pa.AudioFocus()
focus.poll()
check("naming it leaves it audible while a game is focused", world.muted(), [])
check("and it is not counted as a game at all", focus.muted_appids, set())

world = World(streams=[stream(1, 100, "GameA"), stream(2, 700, "discord")],
              owners={100: GAME_A, 700: DISCORD}, focus=GAME_A, never=("DISCORD",))
focus = pa.AudioFocus()
focus.poll()
check("the name match ignores case", world.muted(), [])

world = World(streams=[stream(1, 100, "GameA"), stream(2, 700, "Discord")],
              owners={100: GAME_A, 700: DISCORD}, focus=GAME_A, never=(DISCORD,))
focus = pa.AudioFocus()
focus.poll()
check("an appid can be exempted instead of a name", world.muted(), [])

world = World(
    streams=[stream(1, 100, "GameA"), stream(2, 200, "GameB"), stream(3, 700, "Discord")],
    owners={100: GAME_A, 200: GAME_B, 700: DISCORD}, focus=GAME_A, never=("Discord",))
focus = pa.AudioFocus()
focus.poll()
check("two real games are still managed around it", world.muted(), [2])
world.focus = GAME_B
focus.poll()
check("switching between them still works", world.muted(), [1])
check("and Discord was never touched", [c for c in world.mute_calls if c[0] == 3], [])

# The stream label is whatever the app reported; an Electron audio process is
# not reliably named after the app, so the process is checked as well.
pa.process_names = lambda pid: {"discord"}
check("a stream labelled 'playStream' is still recognised by its process",
      pa.exempt_stream(stream(1, 700, "playStream"), DISCORD, {"discord"}, set()), True)
pa.process_names = lambda pid: {"firefox"}
check("an unrelated process is not exempt",
      pa.exempt_stream(stream(1, 900, "playStream"), DISCORD, {"discord"}, set()), False)
check("no exemptions configured means no /proc lookups at all",
      pa.exempt_stream(stream(1, 900, "Discord"), DISCORD, set(), set()), False)

print()
print("robustness:")

world, focus = two_games(focus=GAME_A)
pa.set_mute = lambda index, muted, dry_run: False      # pactl refusing
focus.poll()
check("a failed mute is reported, not silently assumed",
      any("could not mute" in m for m in world.logs), True)
check("and the stream really is left playing", world.muted(), [])
check("but it stays tracked, so the next poll retries",
      sorted(focus.muted_appids), [GAME_B])

# Seen in the wild: a game quits between listing its streams and muting them,
# so pactl fails on an index that no longer exists. That is a game closing, not
# a fault, and logging it as one sends people looking for a problem.
world, focus = two_games(focus=GAME_A)
def vanishing(index, muted, dry_run):
    world.drop(index)                                  # the game just quit
    return False
pa.set_mute = vanishing
focus.poll()
check("a stream that vanished mid-poll is not reported as a failure",
      [m for m in world.logs if "could not" in m], [])

print()
print("keeping voice chat on console mode's devices:")

# Discord keeps its own output and input choice, so inheriting PULSE_SINK only
# decides where it starts. Moving the stream is the part it cannot overrule.
DISCORD = 3214031495
TV = "alsa_output.pci-0000_0c_00.1.hdmi-stereo"
MIC = "alsa_input.usb-HyperX_Cloud_III_S.mono-fallback"
DESK = "alsa_output.usb-RODECaster_Duo.analog-stereo"
DESK_MIC = "alsa_input.usb-RODECaster_Duo.analog-stereo"

BOTH = {("sinks", 1): TV, ("sinks", 2): DESK,
        ("sources", 1): MIC, ("sources", 2): DESK_MIC}


def voice_world(**kw):
    kw.setdefault("streams", [stream(10, 500, "Discord", device=2)])
    kw.setdefault("capture", [stream(11, 500, "Discord", device=2)])
    kw.setdefault("owners", {500: DISCORD})
    kw.setdefault("never", ("Discord",))
    kw.setdefault("devices", (TV, MIC))
    kw.setdefault("names", BOTH)
    kw.setdefault("focus", None)
    return World(**kw), pa.AudioFocus()


world, focus = voice_world()
focus.poll()
check("voice chat on the wrong output is moved to console mode's own",
      [m for m in world.moves if m[0] == "sinks"], [("sinks", 10, TV)])
check("and its microphone is moved to the chosen one too",
      [m for m in world.moves if m[0] == "sources"], [("sources", 11, MIC)])

# The whole point of re-checking every poll is that a second poll is quiet.
world.moves.clear()
focus.poll()
check("a stream already on the right device is left alone", world.moves, [])

# Discord changing its own setting mid-call is exactly the case this exists for.
world.streams[0].device = 2
focus.poll()
check("a stream that wanders back is moved again",
      world.moves, [("sinks", 10, TV)])

world, focus = voice_world(streams=[stream(10, 500, "Discord", device=1)],
                           capture=[stream(11, 500, "Discord", device=1)])
focus.poll()
check("nothing is moved when it already started in the right place",
      world.moves, [])

# Pinning must not become a general "move everything" policy: a game's own
# audio setup is not this daemon's business.
world, focus = voice_world(
    streams=[stream(10, 500, "Discord", device=2), stream(1, 100, "GameA", device=2)],
    capture=[], owners={500: DISCORD, 100: GAME_A})
focus.poll()
check("a game on another output is never moved", world.moves, [("sinks", 10, TV)])

# A single game plus voice chat mutes nothing, which is precisely when pinning
# still has to happen.
world, focus = voice_world(
    streams=[stream(10, 500, "Discord", device=2), stream(1, 100, "GameA", device=1)],
    capture=[], owners={500: DISCORD, 100: GAME_A})
focus.poll()
check("pinning happens even though nothing is muted", world.moves,
      [("sinks", 10, TV)])
check("and still nothing is muted", world.mute_calls, [])

world, focus = voice_world(pin=False)
focus.poll()
check("AUDIO_PIN_VOICE=off moves nothing", world.moves, [])

# Console mode's devices are for console mode. Discord at the desk must be left
# wherever the user put it.
world, focus = voice_world(session=False)
focus.poll()
check("with no session running, nothing is pinned", world.moves, [])

# Nothing saved means nothing to pin to; leaving streams alone beats guessing.
world, focus = voice_world(devices=(None, None))
focus.poll()
check("no configured device means no move", world.moves, [])

world, focus = voice_world(devices=(TV, None))
focus.poll()
check("output can be pinned while input is left to the session",
      world.moves, [("sinks", 10, TV)])

# Only exempt streams are pinned, so a game named like nothing special is safe.
world, focus = voice_world(never=())
focus.poll()
check("with nothing exempt, nothing is pinned", world.moves, [])

# Exemption by appid has to pin too, since that is how a shortcut is named when
# its stream label does not match.
world, focus = voice_world(never=(str(DISCORD),),
                           streams=[stream(10, 500, "WEBRTC VoiceEngine", device=2)],
                           capture=[stream(11, 500, "WEBRTC VoiceEngine", device=2)])
focus.poll()
check("an appid exemption pins the stream behind it",
      sorted(world.moves), [("sinks", 10, TV), ("sources", 11, MIC)])

print()
print("dry run:")

# The real set_mute, so the dry_run branch itself is under test rather than a
# stand-in for it.
world, focus = two_games(focus=GAME_A)
pa.set_mute = real_set_mute
commands = []
pa.run = lambda args, timeout=5: commands.append(args) or ""
focus = pa.AudioFocus(dry_run=True)
focus.poll()
check("dry run still picks the game to mute", sorted(focus.muted_appids), [GAME_B])

# Listing is how the daemon looks at the world and changes nothing, so the
# invariant under test is that no *mutating* command runs, not that pactl is
# never spoken to at all.
def mutations(args_list):
    return [a[:2] for a in args_list
            if len(a) > 1 and a[1] not in ("-f", "list") and not a[1].startswith("get-")]


check("dry run runs no command that changes anything", mutations(commands), [])

focus = pa.AudioFocus(dry_run=False)
focus.poll()
check("a real run does call pactl",
      mutations(commands), [["pactl", "set-sink-input-mute"]])

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
    sys.exit(1)
print("all audio focus tests passed")
