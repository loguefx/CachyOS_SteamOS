#!/usr/bin/env python3
"""Leaving console mode has to leave a desktop Steam client behind.

The Steam button does not launch anything: a double press asks the *running*
client to switch to Big Picture. Console mode stops the desktop client so Steam
can be restarted inside gamescope, and leaving kills gamescope, which takes that
Steam with it -- so without putting a client back, the button has nothing to talk
to and the way in is gone until the user notices and starts Steam by hand.

These tests drive `cachy-console restart-steam` with a fake Steam, a fake pgrep
and a fake exit helper, so nothing here starts a client, touches audio or looks
at a real display. What they pin is the behaviour that is easy to get wrong and
invisible when it breaks: that a client is started at all, that it is not started
while a session is running or one is already up, that the environment console
mode arranged for the television does not follow it back to the desk, and that a
launch Steam swallowed is tried again.
"""

import atexit
import fcntl
import itertools
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WRAPPER = os.path.join(HERE, "..", "bin", "cachy-console")

FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        FAILURES.append(label)
        print(f"          got  {got!r}\n          want {want!r}")


# Steam records how it was called and, unless the run is meant to model a launch
# that the dying client swallowed, marks itself running.
STEAM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STATE/steam-argv"
env > "$STATE/steam-env"
[[ -f "$STATE/swallow" ]] || : > "$STATE/running"
"""

# Only `pgrep -x steam` reaches this on the path under test. "dies-after" counts
# polls before the client that console mode was running finally disappears.
PGREP = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STATE/pgrep-argv"
if [[ -f "$STATE/dies-after" ]]; then
    n="$(< "$STATE/dies-after")"
    if (( n > 0 )); then
        printf '%s' "$(( n - 1 ))" > "$STATE/dies-after"
    else
        rm -f "$STATE/running" "$STATE/dies-after"
    fi
fi
[[ -f "$STATE/running" ]]
"""

# Stands in for the user manager. Drops its own options and runs the command,
# unless the run is modelling a manager that refused the scope.
SYSTEMD_RUN = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STATE/systemd-run-argv"
[[ -f "$STATE/systemd-run-fails" ]] && exit 1
while [[ "${1-}" == -* ]]; do
    [[ "$1" == -- ]] && { shift; break; }
    shift
done
exec "$@"
"""

EXIT_HELPER = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STATE/exit-argv"
[[ "${1-}" == --running ]] || exit 0
[[ -f "$STATE/console-running" ]]
"""

DISPLAY_HELPER = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STATE/display-argv"
exit 0
"""

# What console mode exports into Steam's environment, and so what a desktop
# client must not inherit.
CONSOLE_ENV = {
    "PULSE_SINK": "alsa_output.hdmi-tv",
    "PULSE_SOURCE": "alsa_input.mic-by-the-couch",
    "SDL_VIDEODRIVER": "x11",
    "SDL_GAMECONTROLLER_IGNORE_DEVICES": "0x31e3/0x1400",
    "NODEVICE_SELECT": "1",
    "DISABLE_LAYER_MESA_ANTI_LAG": "1",
    "GDK_BACKEND": "x11",
    "QT_QPA_PLATFORM": "xcb",
}


def write_exe(path, body):
    with open(path, "w") as fh:
        fh.write(body)
    os.chmod(path, 0o755)


class Run:
    """One `cachy-console restart-steam` in a tree of fakes."""

    def __init__(self, root, config="", state=(), files=None, hold_lock=False):
        self.root = root
        bindir = os.path.join(root, "bin")
        stubdir = os.path.join(root, "stub")
        self.state = os.path.join(root, "state")
        runtime = os.path.join(root, "run")
        cfgdir = os.path.join(root, "config", "cachy-console")
        for d in (bindir, stubdir, self.state, runtime, cfgdir):
            os.makedirs(d, exist_ok=True)

        # Copied so find_helper picks the stubs beside it rather than the real
        # helpers, which would scan /proc for a live gamescope.
        shutil.copy2(WRAPPER, os.path.join(bindir, "cachy-console"))
        write_exe(os.path.join(bindir, "cachy-console-exit"), EXIT_HELPER)
        write_exe(os.path.join(bindir, "cachy-console-display"), DISPLAY_HELPER)
        write_exe(os.path.join(stubdir, "steam"), STEAM)
        write_exe(os.path.join(stubdir, "pgrep"), PGREP)
        write_exe(os.path.join(stubdir, "systemd-run"), SYSTEMD_RUN)

        with open(os.path.join(cfgdir, "config"), "w") as fh:
            fh.write(config)
        for flag in state:
            open(os.path.join(self.state, flag), "w").close()
        for name, body in (files or {}).items():
            with open(os.path.join(self.state, name), "w") as fh:
                fh.write(body)

        environ = dict(os.environ)
        environ.update(CONSOLE_ENV)
        environ["PATH"] = stubdir + os.pathsep + environ.get("PATH", "")
        environ["STATE"] = self.state
        environ["XDG_CONFIG_HOME"] = os.path.join(root, "config")
        environ["XDG_RUNTIME_DIR"] = runtime
        # 1s of patience instead of 15, so the give-up path is a test and not a
        # wait.
        environ["CACHY_CONSOLE_STEAM_TIMEOUT"] = "1"

        lock = None
        if hold_lock:
            lock = open(os.path.join(runtime, "cachy-console-steam.lock"), "w")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            self.proc = subprocess.run(
                [os.path.join(bindir, "cachy-console"), "restart-steam"],
                env=environ, capture_output=True, text=True, timeout=60)
        finally:
            if lock is not None:
                lock.close()

    def _lines(self, name):
        try:
            with open(os.path.join(self.state, name)) as fh:
                return [l.rstrip("\n") for l in fh if l.strip()]
        except OSError:
            return []

    @property
    def steam_launches(self):
        return self._lines("steam-argv")

    @property
    def scope_attempts(self):
        return self._lines("systemd-run-argv")

    @property
    def display_calls(self):
        return self._lines("display-argv")

    def steam_env(self):
        env = {}
        try:
            with open(os.path.join(self.state, "steam-env")) as fh:
                for line in fh:
                    key, _, value = line.rstrip("\n").partition("=")
                    env[key] = value
        except OSError:
            pass
        return env


BASE = tempfile.mkdtemp(prefix="cachy-console-steam-restart-")
atexit.register(shutil.rmtree, BASE, True)
CASES = itertools.count()


def run(**kwargs):
    """One case, in a tree that outlives it: the fakes' notes are read after."""
    return Run(os.path.join(BASE, f"case{next(CASES)}"), **kwargs)


print("putting the desktop client back:")

ended = run()
check("a session that has ended starts the desktop client",
      len(ended.steam_launches), 1)
check("it comes back minimised to the tray, not over the user's desktop",
      ended.steam_launches, ["-silent"])
check("starting a client is not starting a session",
      [c for c in ended.display_calls if "resolve" in c or "audio-route" in c],
      [])

# The regression this guards: `restart-steam` reached neither the argument parser
# nor the dispatch, so cachy-console-watch asking for a client would have fallen
# through to the default command and started console mode instead.
check("restart-steam is a command, not an unrecognised argument",
      ended.proc.returncode, 0)

check("a client that outlived the session is left alone, not doubled",
      run(state=("running",)).steam_launches, [])

# Steam's second instance hands its arguments to the client that already holds
# the IPC socket and then exits, so a launch that happens before gamescope's
# Steam has finished dying becomes no client at all. It has to be waited out.
late = run(state=("running",), files={"dies-after": "1"})
check("gamescope's Steam still shutting down is waited out, then replaced",
      late.steam_launches, ["-silent"])

print()
print("when not to start one:")

check("RESTART_STEAM=off leaves Steam alone",
      run(config="RESTART_STEAM=off\n").steam_launches, [])

# Going straight back into console mode: a client started now is one stop_steam
# would have to close again, and the run that is starting owns Steam.
check("a console session already running again gets no desktop client",
      run(state=("console-running",)).steam_launches, [])

# Both the wrapper's exit path and cachy-console-watch call this, and either may
# be the only survivor, so both always try. The lock is what stops two clients.
check("a relaunch already in flight is left to finish alone",
      run(hold_lock=True).steam_launches, [])

print()
print("the environment the client comes back with:")

env = ended.steam_env()
check("console mode's audio devices do not follow Steam to the desk",
      [k for k in ("PULSE_SINK", "PULSE_SOURCE") if k in env], [])
check("gamescope's nested-session workarounds are dropped",
      [k for k in ("SDL_VIDEODRIVER", "NODEVICE_SELECT",
                   "DISABLE_LAYER_MESA_ANTI_LAG", "GDK_BACKEND",
                   "QT_QPA_PLATFORM") if k in env], [])
check("controllers hidden from console mode are gamepads again",
      "SDL_GAMECONTROLLER_IGNORE_DEVICES" in env, False)
# The watcher used to preload extest into the desktop client whether or not the
# user had asked for it, which is the one setting this project tells people to
# leave off.
check("no libextest preload the user did not ask for",
      "LD_PRELOAD" in env, False)
check("the session the client has to draw on is kept",
      env.get("XDG_RUNTIME_DIR", "").endswith("/run"), True)

print()
print("launching it so it outlives us:")

check("a transient scope is asked for, so the client is nobody's child",
      [c for c in ended.scope_attempts if "--scope" in c and "--user" in c],
      ended.scope_attempts)
check("exactly one scope for one client", len(ended.scope_attempts), 1)

# A user manager that will not give us a scope must not cost the user their
# client: the second attempt goes without one.
refused = run(state=("systemd-run-fails",))
check("a refused scope still leaves a client running",
      refused.steam_launches, ["-silent"])
check("and it is not asked for twice", len(refused.scope_attempts), 1)

# A launch that the dying client swallowed leaves nothing running, which looks
# exactly like no launch at all, so it is tried again before giving up.
swallowed = run(state=("swallow",))
check("a swallowed launch is retried", len(swallowed.steam_launches), 2)
check("and giving up says so rather than failing silently",
      "did not come back" in swallowed.proc.stderr, True)
check("giving up is not an error the caller has to handle",
      swallowed.proc.returncode, 0)

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s)")
    sys.exit(1)
print("all desktop-Steam restart tests passed")
