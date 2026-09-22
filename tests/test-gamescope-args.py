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


HELPER = """#!/bin/bash
case "$1" in
  saved)         echo "HDMI-A-1" ;;
  resolve)       echo "2 1920 1080 240 HDMI-A-1" ;;
  audio-route)   echo "SINK alsa_output.fake" ;;
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


class World:
    """A cachy-console with fake helpers beside it and a config of our own."""

    def __init__(self, config=""):
        self.dir = tempfile.mkdtemp(prefix="cachy-args-")
        self.bin = os.path.join(self.dir, "bin")
        os.makedirs(self.bin)
        shutil.copy(WRAPPER, os.path.join(self.bin, "cachy-console"))
        for name, body in (("cachy-console-display", HELPER),
                           ("gamescope", GAMESCOPE),
                           ("steam", "#!/bin/bash\nexit 0\n"),
                           ("pgrep", "#!/bin/bash\nexit 1\n")):
            path = os.path.join(self.bin, name)
            with open(path, "w") as fh:
                fh.write(body)
            os.chmod(path, 0o755)

        conf_dir = os.path.join(self.dir, "config", "cachy-console")
        os.makedirs(conf_dir)
        with open(os.path.join(conf_dir, "config"), "w") as fh:
            fh.write(config)
        self.config_home = os.path.join(self.dir, "config")

    def argv(self):
        """The gamescope command line `start --dry-run` would run."""
        env = dict(os.environ)
        env["XDG_CONFIG_HOME"] = self.config_home
        env["PATH"] = self.bin + os.pathsep + env.get("PATH", "")
        res = subprocess.run([os.path.join(self.bin, "cachy-console"),
                              "start", "--dry-run"],
                             capture_output=True, text=True, timeout=60, env=env)
        for line in res.stdout.splitlines():
            if "gamescope" in line and "--backend" in line:
                return line.strip().split()
        return []

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
    """Whether Steam is started with an extest preload, and nothing else is."""
    return [a for a in argv if a.startswith("LD_PRELOAD=")]


# Only meaningful where extest exists: the wrapper will not preload a library
# that is not installed, and refusing to is the correct behaviour there.
if os.path.exists("/usr/lib/libextest.so") or os.path.exists("/usr/lib32/libextest.so"):
    w = World("DISPLAY=HDMI-A-1\n")
    check("extest is preloaded into Steam by default, since XTEST alone moves "
          "nothing a client can see",
          preloaded(w.argv()), ["LD_PRELOAD=libextest.so"])
    w.clean()
else:
    print("  SKIP  extest is not installed here")

w = World("DISPLAY=HDMI-A-1\nTRACKPAD_FIX=off\n")
check("and nothing is preloaded when it is turned off",
      preloaded(w.argv()), [])
w.clean()

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
    sys.exit(1)
print("all passed")
