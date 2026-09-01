# cachy-console

A console experience for CachyOS. Press the Steam button, land in Big Picture on
your TV at its full refresh rate, play, and drop back to your desktop when you
are done.

CachyOS is a desktop distro, and Steam's Big Picture on a normal desktop is not
the same thing as SteamOS: the compositor is busy driving your other monitors,
the Steam overlay is rendered by a browser process on top of that, and the
result is the sluggish menus and uneven frame pacing that make a Steam Deck feel
like a different product. This runs Big Picture inside **gamescope** on one
display instead, which is the same compositor SteamOS uses, while the rest of
your desktop carries on untouched.

It is a mode you switch into, not a way to boot the machine. Nothing about your
normal desktop changes.

## What you get

- **Big Picture in gamescope**, so menus and the in-game overlay stay responsive
- **Your display's real settings** — whatever resolution and refresh rate that
  screen is set to is what console mode runs at. 1080p60, 1440p165, 4K120: no
  configuration, and nothing to update when you change it
- **Any display you like**, chosen once, including one that is not your primary
- **The Steam button opens it**, the same double-press that already opens Big
  Picture
- **One game's audio at a time** — with two games running, you only hear the one
  you switched to
- **A working way out**, which Big Picture itself does not give you
- **No trackpad permission prompts** from the Steam controller

Your other monitors keep running the desktop the whole time.

## Requirements

- CachyOS, or any Arch-based system
- GNOME or KDE Plasma on Wayland
- Steam, and gamescope

Nothing here talks to a specific compositor: displays come from SDL, windows
from XWayland, audio from PipeWire. It is written for **GNOME** and **KDE
Plasma** on Wayland (CachyOS ships Plasma by default). The same saved TV works
on both: Plasma may list it as `HDMI-A-1` and GNOME as `HDMI-1`, and those are
treated as the same port. Search the app menu for **Cachy Console** (or run
`cachy-console settings`) and pick from that list. That saved display is the
only one console mode will ever use. If you turn it off, the Steam button
leaves Big Picture on the desktop until that same display comes back — it will
not pick another screen by itself.

`cachy-console status` checks the things most likely to differ between
desktops, including whether systemd can see your session.

If you change the display while console mode is already open, the live session
stays where it is. Exit with `cachy-console exit` (or the library shortcut),
then press the Steam button twice to open gamescope on the new display.

## Install

One command. **pacman** installs the packages; the script only clones this repo
and copies files into your home directory.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/loguefx/CachyOS_SteamOS/main/get.sh)
```

That will:

1. `sudo pacman -S --needed git steam gamescope sdl2 libpulse xorg-xprop tk`
2. Clone this repo to `~/CachyOS_SteamOS` (or update it if it is already there)
3. Run `./install.sh`, which copies the commands into `~/.local/bin`, enables
   two user services, and walks you through choosing a display

Root is used for pacman, and once more if you let it grant gamescope realtime
scheduling. If you already have `paru` or `yay`, it will offer **libextest**
from the AUR (trackpad permission prompt). It will not install an AUR helper
or add a third-party repo.

Uninstall with `~/CachyOS_SteamOS/uninstall.sh`. To clone somewhere else:

```bash
CACHY_CONSOLE_SRC=~/src/CachyOS_SteamOS bash <(curl -fsSL https://raw.githubusercontent.com/loguefx/CachyOS_SteamOS/main/get.sh)
```

### Step by step

```bash
sudo pacman -S --needed steam gamescope sdl2 libpulse xorg-xprop tk
# optional, AUR:  paru -S libextest-git
git clone https://github.com/loguefx/CachyOS_SteamOS.git
cd CachyOS_SteamOS
./install.sh
```

## Using it

```bash
cachy-console            # start console mode
cachy-console exit       # back to the desktop
cachy-console status     # check everything, and show what would run
cachy-console displays   # list displays, their modes, and gamescope's indices
cachy-console settings   # pick the display (saved until you change it)
cachy-console setup      # same, from a terminal
```

Or press the Steam button twice on a controller, which is the point.

### Getting out again

**Steam gives you no working exit here, and that is not a bug in this project.**
Steam hides "Exit Steam", "Exit Big Picture Mode" and "Minimize" whenever it
detects gamescope, because SteamOS expects a session manager to handle leaving.
Big Picture's "Switch to Desktop" calls a SteamOS-only method that a normal
Linux client answers with `Method SwitchToDesktop() not implemented`, so
clicking it does nothing at all.

So there are two ways out:

```bash
cachy-console exit          # from a terminal or a keyboard shortcut
cachy-console shortcut      # adds "Exit Console Mode" to your Steam library
```

The library entry is the one you want on a couch: it appears among your games,
so you can launch it with the controller and end up back at your desktop.
Favourite it, or pin it to your home shelf, and it becomes a one-click exit.

Run `cachy-console shortcut` while **Steam is closed** — Steam rewrites its
shortcuts file from memory when it exits and would otherwise discard the entry.
An older "Exit Game Mode" tile that still pointed at `projector-exit` is updated
to `cachy-console-exit` by that same command.

## Configuration

`~/.config/cachy-console/config`, written by `cachy-console settings` and safe to
edit by hand:

| Setting | Default | Meaning |
| --- | --- | --- |
| `DISPLAY` | *(required)* | Connector to use, e.g. `HDMI-1`. Never `auto` and never an index: if this display is off, console mode waits instead of using another screen |
| `RESOLUTION` | `auto` | Follow the display's current setting, or force e.g. `1920x1080` |
| `REFRESH` | `auto` | Follow the display's current setting, or force e.g. `120` |
| `VRR` | `on` | FreeSync / G-Sync inside console mode |
| `HDR` | `off` | Only worth enabling if display and games support it |
| `TRACKPAD_FIX` | `on` | Preload libextest so the trackpad stops asking permission |
| `STEAM_BUTTON` | `on` | Let the Steam button open console mode |
| `AUDIO_FOCUS` | `on` | Mute games you are not looking at |
| `EXTRA_GAMESCOPE_ARGS` | empty | Passed straight through, e.g. `--mangoapp` |

## How it works

**Picking the display.** gamescope's `--display-index` is an SDL index, so SDL
is asked directly rather than any compositor — that is why the same build works
on GNOME and Plasma. SDL is asked twice, because neither backend tells the
whole truth: its **x11** backend names displays by connector and numbers them
the way gamescope expects, but under XWayland it can report 60Hz for a 240Hz
screen, while its **wayland** backend reports the true mode but names displays
by manufacturer. The two views are matched up by screen position, taking names
and indices from one and the mode from the other. Connector names are
normalized so Plasma's `HDMI-A-1` and GNOME's `HDMI-1` stay the same saved
display.

**Session environment.** The Steam-button watcher and per-game audio run as
systemd user services. GNOME usually exports `DISPLAY` and `XAUTHORITY` into
that manager; Plasma often does not. An autostart entry and a small wrapper
fill those in from the sockets your session already created, on both desktops.

**The Steam button.** Pressing it twice does not launch anything — it flips the
*already running* Steam client into Big Picture, so there is no command to
intercept. gamescope also cannot adopt a window owned by another compositor, so
an open Big Picture cannot be moved into it. `cachy-console-watch` therefore
watches for the Big Picture window appearing and relaunches Steam inside
gamescope, then restores the desktop client when the session ends.

**HDMI audio.** GPU HDMI/DP audio exposes one stereo device at a time, so Steam
would otherwise list your primary monitor instead of the TV. Console mode
switches that profile to the saved display on the way in, and puts it back when
you leave.

**Per-game audio.** gamescope publishes which app it has focused; PipeWire can
mute one stream. A stream is treated as a game's only when its process, or one
of its ancestors, was started by Steam with `SteamGameId` set, so browsers,
music and Steam's own interface sounds are never touched. Nothing is muted
unless two or more games are actually producing audio, and every mute is undone
when the games close or the service stops.

**The trackpad prompt.** Steam drives the controller trackpad through XTEST. On
Wayland, XWayland turns that into an xdg-desktop-portal request — the "allow
remote interaction" dialog — and the permission dies with the Steam process, so
it returns on every restart. libextest implements those calls against
`/dev/uinput` instead, so there is nothing to approve.

## Troubleshooting

**It opened on the wrong screen.** Search for **Cachy Console**, save the
display you want, then if gamescope is already running exit and Steam-button
twice so the next session uses it.

**The refresh rate looks wrong.** `cachy-console-display probe` shows both SDL
views separately. If they disagree, set `REFRESH` explicitly.

**Nothing happens on the Steam button.**

```bash
systemctl --user status cachy-console-watch
journalctl --user -u cachy-console-watch -f
```

The watcher stands down when your chosen display is switched off, so Big Picture
stays on the desktop rather than opening somewhere you cannot see.

**It refuses to start.** Starting console mode restarts Steam, which would close
a running game, so it stops and says so. Quit the game, or set
`CACHY_CONSOLE_FORCE=1`.

**A game is silent when it should not be.**

```bash
cachy-console-audio --status    # streams, their games, and the focused app
```

Stopping the service unmutes everything it muted.

## Not supported

- **X11 sessions.** Some of this works, but it is built and tested for Wayland.
- **Turning your other monitors off.** Doing that needs compositor-specific
  code, and gamescope can target a display without it.
- **Replacing your session.** This is not a SteamOS-style boot-to-Steam setup.

## License

MIT. See [LICENSE](LICENSE).
