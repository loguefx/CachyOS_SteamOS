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

    def __init__(self, streams=(), owners=None, focus=None, session=True):
        self.streams = list(streams)
        self.owners = dict(owners or {})     # pid -> appid (None = not a game)
        self.focus = focus
        self.session = session
        self.mute_calls = []
        self.logs = []

        pa.sink_inputs = lambda: list(self.streams)
        pa.steam_appid = lambda pid, limit=24: self.owners.get(pid)
        pa.gamescope_displays = lambda: [":2"] if self.session else []
        pa.focused_appid = lambda display: self.focus
        pa.set_mute = self._set_mute
        pa.log = self.logs.append

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


def stream(index, pid, name="game", muted=False):
    return pa.Stream(index, pid, muted, name)


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
check("dry run runs no pactl command", commands, [])

focus = pa.AudioFocus(dry_run=False)
focus.poll()
check("a real run does call pactl",
      [a[:2] for a in commands], [["pactl", "set-sink-input-mute"]])

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
    sys.exit(1)
print("all audio focus tests passed")
