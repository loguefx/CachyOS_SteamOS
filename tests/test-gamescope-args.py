#!/usr/bin/env python3
"""What console mode actually asks gamescope for.

Two of these decide whether the session is usable at all, and neither shows up
as an error when it is wrong -- the screen just looks wrong, or nothing can be
clicked.

The screen is chosen by *index*, because the SDL backend has no other way to
name an output, and an index only means anything for one arrangement of
monitors. The cursor is the other one: --force-grab-cursor holds gamescope in
relative mouse mode, so a desktop application in the session never gets a
pointer and a controller cannot click anything in it. It is off unless asked
for, and these pin that down, along with the fact that asking still works.

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
check("the pointer is not grabbed by default, so a cursor can be drawn",
      "--force-grab-cursor" in w.argv(), False)
w.clean()

w = World("DISPLAY=HDMI-A-1\nGRAB_CURSOR=on\n")
check("asking for the grab still gets it",
      "--force-grab-cursor" in w.argv(), True)
w.clean()

w = World("DISPLAY=HDMI-A-1\nGRAB_CURSOR=off\n")
check("and saying off explicitly is the same as not saying it",
      "--force-grab-cursor" in w.argv(), False)
w.clean()

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
    sys.exit(1)
print("all passed")
