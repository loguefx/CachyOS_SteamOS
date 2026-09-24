#!/usr/bin/env python3
"""What console mode actually asks gamescope for.

Two of these decide whether the session is usable at all, and neither shows up
as an error when it is wrong -- the screen just looks wrong, or nothing can be
clicked.

The screen is chosen by *index*, because the SDL backend has no other way to
name an output, and an index only means anything for one arrangement of
monitors. The cursor is the other one: --force-grab-cursor is what makes a nested
gamescope draw a cursor of its own instead of leaving it to the desktop holding
the window, so without it there is nothing in the session to aim with a trackpad.
It is on unless turned off, and these pin that down both ways.

Everything here runs `start --dry-run` against a fake display helper and a fake
gamescope, so no session is started and no display or audio device is touched.
"""

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
        print(f"        got  = {got!r}")
        print(f"        want = {want!r}")
        FAILURES.append(label)


# A display helper that can also behave like screens in motion. Two knobs, both
# written by the test as files in $CACHY_TEST_STATE:
#
#   strict-fails  how many `resolve --strict` calls refuse before answering,
#                 which is what a layout caught mid-change looks like
#   answer2       the answer to give once `flip-after` resolves have been
#                 answered -- a screen waking or sleeping after the index was
#                 first worked out, which renumbers the list with nothing to
#                 notice
HELPER = """#!/bin/bash
state="${CACHY_TEST_STATE:-}"

answer() {
    if [[ -n "$state" && -f "$state/answer2" && -f "$state/flip-after" ]] \
            && (( $(< "$state/resolves") > $(< "$state/flip-after") )); then
        cat "$state/answer2"
    else
        echo "2 1920 1080 240 HDMI-A-1"
    fi
}

case "$1" in
  saved)         echo "HDMI-A-1" ;;
  resolve)
    if [[ -n "$state" ]]; then
        n=0; [[ -f "$state/resolves" ]] && n="$(< "$state/resolves")"
        echo $(( n + 1 )) > "$state/resolves"
    fi
    if [[ "$2" == "--strict" && -n "$state" && -f "$state/strict-fails" ]]; then
        left="$(< "$state/strict-fails")"
        if (( left > 0 )); then
            printf '%s\n' "$(( left - 1 ))" > "$state/strict-fails"
            echo "displays are still arranging themselves (DP-2, HDMI-A-1)" >&2
            exit 1
        fi
    fi
    answer ;;
  audio-route)   echo "SINK alsa_output.fake" ;;
  pad-layouts)
    if [[ -n "$state" ]]; then
        if [[ -f "$state/desktop-steam" ]]; then
            echo "pad-layouts with steam running" >> "$state/sequence"
        else
            echo "pad-layouts" >> "$state/sequence"
        fi
    fi ;;
  audio-input-resolve) echo "alsa_input.fake" ;;
  audio-resolve) echo "alsa_output.fake" ;;
  has)           exit 0 ;;
  *)             exit 0 ;;
esac
"""

# Enough of gamescope for the capability probes, which read --help and the
# dynamic section rather than starting anything.
GAMESCOPE = """#!/bin/bash
echo "  --rt  use realtime scheduling"
echo "  --force-grab-cursor  always use relative mouse mode"
"""


# gamescope writes down what it was asked for, then runs its child the way the
# real one does, so steam-in-session runs too.
def gamescope_recorder(state):
    return GAMESCOPE + f"""printf "%s\\n" "$@" > {state}/gamescope-argv
echo gamescope >> {state}/sequence
while (( $# )) && [[ "$1" != "--" ]]; do shift; done
shift
"$@"
"""


# A desktop client that is running until asked to quit, and a Steam started in
# the session that writes down what it inherited.
STEAM = """#!/bin/bash
state="$CACHY_TEST_STATE"
echo "steam $*" >> "$state/sequence"
case "$1" in
  -shutdown)  rm -f "$state/desktop-steam" ;;
  -gamepadui) env | grep -E '^(PULSE_SINK|PULSE_SOURCE|LD_PRELOAD|CACHY_CONSOLE_PRELOAD)=' \
                  | sort > "$state/steam-env" ;;
esac
exit 0
"""

PGREP = """#!/bin/bash
[[ "$*" == "-x steam" && -f "$CACHY_TEST_STATE/desktop-steam" ]] && exit 0
exit 1
"""


class World:
    """A cachy-console with fake helpers beside it and a config of our own."""

    def __init__(self, config="", strict_fails=0, answer2=None, flip_after=None,
                 desktop_steam=False):
        self.dir = tempfile.mkdtemp(prefix="cachy-args-")
        self.bin = os.path.join(self.dir, "bin")
        os.makedirs(self.bin)
        self.state = os.path.join(self.dir, "state")
        self.run = os.path.join(self.dir, "run")
        os.makedirs(self.state)
        os.makedirs(self.run)
        if strict_fails:
            self.write(os.path.join(self.state, "strict-fails"), str(strict_fails))
        if answer2:
            self.write(os.path.join(self.state, "answer2"), answer2)
        if flip_after is not None:
            self.write(os.path.join(self.state, "flip-after"), str(flip_after))
        if desktop_steam:
            self.write(os.path.join(self.state, "desktop-steam"), "")
        shutil.copy(WRAPPER, os.path.join(self.bin, "cachy-console"))
        for name, body in (("cachy-console-display", HELPER),
                           ("gamescope", gamescope_recorder(self.state)),
                           ("steam", STEAM),
                           ("pgrep", PGREP),
                           ("cachy-console-exit", "#!/bin/bash\nexit 1\n")):
            path = os.path.join(self.bin, name)
            with open(path, "w") as fh:
                fh.write(body)
            os.chmod(path, 0o755)

        conf_dir = os.path.join(self.dir, "config", "cachy-console")
        os.makedirs(conf_dir)
        with open(os.path.join(conf_dir, "config"), "w") as fh:
            fh.write(config)
        self.config_home = os.path.join(self.dir, "config")

    @staticmethod
    def write(path, text):
        with open(path, "w") as fh:
            fh.write(text + "\n")

    def env(self):
        env = dict(os.environ)
        env["XDG_CONFIG_HOME"] = self.config_home
        env["XDG_RUNTIME_DIR"] = self.run
        env["CACHY_TEST_STATE"] = self.state
        env["PATH"] = self.bin + os.pathsep + env.get("PATH", "")
        # Nothing on this desk's real screen is to be taken for Big Picture.
        env["CACHY_CONSOLE_BPM_PATTERN"] = "^cachy-test-never-matches$"
        env["CACHY_CONSOLE_STEAM_TIMEOUT"] = "1"
        return env

    def read(self, name):
        path = os.path.join(self.state, name)
        if not os.path.exists(path):
            return []
        with open(path) as fh:
            return [line.rstrip("\n") for line in fh]

    def argv(self):
        """The gamescope command line `start --dry-run` would run."""
        res = subprocess.run([os.path.join(self.bin, "cachy-console"),
                              "start", "--dry-run"],
                             capture_output=True, text=True, timeout=60,
                             env=self.env())
        self.output = res.stdout + res.stderr
        for line in res.stdout.splitlines():
            if "gamescope" in line and "--backend" in line:
                return line.strip().split()
        return []

    def started(self):
        """The command line a real `start` handed gamescope."""
        res = subprocess.run([os.path.join(self.bin, "cachy-console"), "start"],
                             capture_output=True, text=True, timeout=120,
                             env=self.env())
        self.output = res.stdout + res.stderr
        recorded = os.path.join(self.state, "gamescope-argv")
        if not os.path.exists(recorded):
            return []
        with open(recorded) as fh:
            return [line.rstrip("\n") for line in fh]

    def clean(self):
        shutil.rmtree(self.dir, ignore_errors=True)


print("the screen gamescope is pointed at")
w = World("DISPLAY=HDMI-A-1\n")
argv = w.argv()
check("the resolved index is passed through",
      argv[argv.index("--display-index") + 1] if "--display-index" in argv else None,
      "2")
check("and the connector by name as well, for a backend that can use it",
      argv[argv.index("--prefer-output") + 1] if "--prefer-output" in argv else None,
      "HDMI-A-1")
w.clean()

print()
print("the cursor a controller needs")
w = World("DISPLAY=HDMI-A-1\n")
check("the pointer is grabbed by default, so gamescope draws the cursor itself",
      "--force-grab-cursor" in w.argv(), True)
w.clean()

w = World("DISPLAY=HDMI-A-1\nGRAB_CURSOR=on\n")
check("asking for it explicitly is the same as not saying it",
      "--force-grab-cursor" in w.argv(), True)
w.clean()

w = World("DISPLAY=HDMI-A-1\nGRAB_CURSOR=off\n")
check("and turning it off leaves the cursor to the desktop",
      "--force-grab-cursor" in w.argv(), False)
w.clean()

print()
print("the trackpad Steam drives through XTEST")


def preloaded(argv):
    """The extest preload handed on for Steam. Never as LD_PRELOAD on the
    command line: gamescope's capabilities make glibc strip that."""
    return [a for a in argv if a.startswith(("LD_PRELOAD=", "CACHY_CONSOLE_PRELOAD="))]


# Only meaningful where extest exists: the wrapper will not preload a library
# that is not installed, and refusing to is the correct behaviour there.
if os.path.exists("/usr/lib/libextest.so") or os.path.exists("/usr/lib32/libextest.so"):
    w = World("DISPLAY=HDMI-A-1\n")
    check("extest is preloaded into Steam by default, since XTEST alone moves "
          "nothing a client can see",
          preloaded(w.argv()), ["CACHY_CONSOLE_PRELOAD=libextest.so"])
    w.clean()
else:
    print("  SKIP  extest is not installed here")

w = World("DISPLAY=HDMI-A-1\nTRACKPAD_FIX=off\n")
check("and nothing is preloaded when it is turned off",
      preloaded(w.argv()), [])
w.clean()

print()
print("screens that are still moving when the button is pressed")


def index_of(argv):
    return argv[argv.index("--display-index") + 1] if "--display-index" in argv else None


# Turn the projector on, press the Steam button straight away, and the layout is
# mid-change: resolve refuses until it holds still. The point is that waiting is
# what happens, rather than an index resolved against a list about to change.
w = World("DISPLAY=HDMI-A-1\n", strict_fails=3)
argv = w.argv()
check("an unsettled layout is waited out rather than resolved against",
      index_of(argv), "2")
check("and it says so, because the wait is otherwise unexplained",
      "Waiting for the displays to settle" in w.output, True)
w.clean()

# Nothing refuses here, it just never holds still, which is also what genuinely
# mirrored screens look like. Starting is better than refusing to; saying the
# screen may be wrong is better than not.
w = World("DISPLAY=HDMI-A-1\n", strict_fails=99)
argv = w.argv()
check("screens that never settle still start, on the ordinary answer",
      index_of(argv), "2")
check("with a warning that the screen may not be the right one",
      "never settled" in w.output, True)
w.clean()

print()
print("the index is read again as late as it can be")
# A screen sleeping or waking after the index was first worked out renumbers the
# list. SDL resolves the index when it creates the window: stale, it silently
# uses display 0 -- the monitor being played on. Two resolves settle the first
# answer, so the change lands on the check made just before gamescope starts.
w = World("DISPLAY=HDMI-A-1\n", answer2="1 1920 1080 60 HDMI-A-1", flip_after=2)
argv = w.started()
check("gamescope is given the index resolved last, not the one resolved first",
      index_of(argv), "1")
check("and the mode that came with it",
      argv[argv.index("-r") + 1] if "-r" in argv else None, "60")
check("with the change said out loud, since it explains a slower start",
      "renumbered" in w.output, True)
w.clean()

w = World("DISPLAY=HDMI-A-1\n")
argv = w.started()
check("a layout that held still is not announced as having changed",
      (index_of(argv), "renumbered" in w.output), ("2", False))
w.clean()

print()
print("the screen changes before Steam has finished quitting")
# Quitting the desktop client was 3.3s of a 10s start, all of it with the old
# screen still showing. gamescope now comes up first, and its child starts Big
# Picture once the desktop client is gone.
w = World("DISPLAY=HDMI-A-1\n", desktop_steam=True)
w.started()
order = w.read("sequence")
def at(entry):
    return order.index(entry) if entry in order else None
check("gamescope is started before the desktop client is asked to quit",
      (at("gamescope") is not None and at("steam -shutdown") is not None
       and at("gamescope") < at("steam -shutdown")), True)
check("and Big Picture only once the desktop client has gone",
      (at("steam -gamepadui") is not None
       and at("steam -shutdown") < at("steam -gamepadui")), True)
check("the trackpad mouse layouts are written between the two clients, the "
      "only time Steam will not write over them",
      (at("pad-layouts") is not None
       and at("steam -shutdown") < at("pad-layouts") < at("steam -gamepadui")),
      True)
got = w.read("steam-env")
check("Steam in the session still plays and listens where the settings say",
      [e for e in got if e.startswith("PULSE_")],
      ["PULSE_SINK=alsa_output.fake", "PULSE_SOURCE=alsa_input.fake"])
if os.path.exists("/usr/lib/libextest.so") or os.path.exists("/usr/lib32/libextest.so"):
    check("and has extest preloaded, under its real name and nowhere else",
          [e for e in got if "PRELOAD" in e], ["LD_PRELOAD=libextest.so"])
w.clean()

w = World("DISPLAY=HDMI-A-1\n")
w.started()
check("with no desktop client running, Big Picture starts straight away",
      "steam -gamepadui" in w.read("sequence"), True)
w.clean()

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
    sys.exit(1)
print("all passed")
