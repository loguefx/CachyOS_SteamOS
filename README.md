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
  you switched to, while voice chat stays audible through all of it
- **Discord on the couch**, launched from your library and using the same
  speakers and microphone console mode does
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

Leaving asks Steam to close itself rather than signalling gamescope. Steam is
gamescope's primary child, so the session follows it out, which takes a couple of
seconds instead of the ten that signalling took — gamescope ignores `SIGTERM`, so
it had to be killed once the grace period ran out, and Steam came back up
convinced it had crashed. Signals are still the fallback for a Steam that will
not answer, which is mostly a Steam with a game still running.

If there is no session to leave, it closes Big Picture instead. That happens when
Big Picture is open on the desktop rather than in gamescope — the Steam button
does not launch anything, it asks the client that is already running to switch to
Big Picture, so with the watcher stopped you get Big Picture on whichever screen
the desktop client chose. The tile is in the same library either way, and
answering "console mode is not running" left you in Big Picture with no way out.

Either way you get your ordinary Steam back with it, minimised to the tray, so
the next double press on the Steam button opens console mode again without your
having to go and start Steam first. Turn that off with `RESTART_STEAM=off`.

Run `cachy-console shortcut` while **Steam is closed** — Steam rewrites its
shortcuts file from memory when it exits and would otherwise discard the entry.
An older "Exit Game Mode" tile that still pointed at `projector-exit` is updated
to `cachy-console-exit` by that same command.

### Voice chat

**Big Picture appears on the desktop for a moment before console mode opens, and
that is the trigger rather than a fault.** The Steam button does not launch
anything: it flips the *already running* desktop client into Big Picture, on
whichever screen that window was on. That window appearing is the only signal
there is, so console mode cannot be started before it exists. What used to happen
next was the annoying part — the window sat on the wrong monitor for as long as
Steam took to quit, which looked like console mode had opened on the wrong screen
and moved over some seconds later. Steam is now asked to leave Big Picture first,
which clears that screen in about a second, and only then asked to quit.

The wait after that is Steam starting up again inside gamescope, and there is no
way around it: gamescope cannot adopt a window from another compositor, so Steam
has to be relaunched as its child. Expect a few seconds to the display switching
over and a few more before Big Picture has drawn.

**The Discord already open on your desktop cannot be moved into console mode.**
A window belongs to the compositor its client connected to, and gamescope is a
separate nested one — the same reason Big Picture has to be relaunched rather
than moved. So it is one Discord at a time, which follows you in and out:

```bash
cachy-console shortcut --name Discord --exe /usr/bin/discord   # Steam closed
```

The tile launches through `cachy-console-app`, which handles the two things a
desktop application needs before it behaves like a library entry.

It quits the copy running on your desktop first. Discord keeps a
single-instance lock, so a second copy hands its arguments to the first one,
prints "Quitting secondary instance" and exits about a second later — Steam
sees the process it started exit almost immediately and puts the tile back to
"Play", while the window it raised is on the desktop, behind console mode. The
tile looks like it failed to start. You do not have to remember to quit Discord
before switching any more; it is quit for you, with the signal it treats as a
clean shutdown.

And it quits Discord for real when you close the window. Discord's close button
does not quit it: unless you turn `MINIMIZE_TO_TRAY` off, which is on by
default, it hides the window and keeps running. Console mode has no tray, so
the window would be gone for good while Steam still showed the tile running
with a Stop button — and the hidden copy would still hold the lock, so the next
launch would fail in the way described above and stay broken until you found a
process with no window and killed it. Instead, the wrapper watches the windows
gamescope reports as focusable, and once Discord has shown one and then has
none left, it quits it. Steam sees the exit, the tile goes back to "Play", and
Big Picture has the screen again.

It also corrects two things in the environment Steam hands a tile. Both stop a
desktop application dead, and both look the same from the couch: you press the
tile and nothing appears.

Steam preloads its in-game overlay into everything it launches, and the library
does not survive Electron starting up. Discord's zygote segfaults inside it while
the dynamic linker is still initialising it, and with no zygote there is never a
renderer, so no window is ever created — Discord is left running with no window
on any display, holding its lock, and the next launch only hands off to that copy
and exits. Turning the overlay off on the shortcut is not enough: `AllowOverlay
= 0` disables the overlay's UI and Steam goes on preloading the library anyway.
So it comes out of `LD_PRELOAD` here. Anything else you have put there is left
alone, and the same applies to the `xprop` calls behind the window watch above,
which died in it on the way out of every call.

And it pins the application to gamescope's X11 display. Console mode unsets
`WAYLAND_DISPLAY`, which reads like a safeguard but is not one: a Wayland client
with no `WAYLAND_DISPLAY` does not settle for X11, it connects to `wayland-0` in
`XDG_RUNTIME_DIR`, which is your desktop's compositor. That is how Discord came
up as a window on the desktop, on whichever screen the desktop chose, while
console mode showed Big Picture with nothing else in it. `XDG_SESSION_TYPE` is
what Chromium reads to choose a platform, and the session it inherits says
wayland, so the wrapper sets it to `x11` alongside Electron's own platform hint.
The window then lands in the session, where gamescope lists it as focusable and
the task switcher can reach it.

This applies to any tile you add this way, not just Discord. Pass `--no-wrap`
to launch a program directly, and `--keep-running` in the launch options for
something that is meant to live in a tray.

Adding the entry also gives the tile its picture. A shortcut Steam has no artwork
for is drawn as a grey placeholder with the name printed across it, which from
a sofa is barely distinguishable from the entry beside it. `cachy-console-art`
finds the program's installed icon under `/usr/share/icons`, takes the
background colour from the icon itself — Discord's own blurple, in its case —
and renders the four files Steam asks for: the 600x900 capsule that fills the
library grid, the 920x430 header used in rows and search, the 1920x620 hero
behind the app's page, and a transparent logo drawn over it. They go into
`userdata/<id>/config/grid`, named after the same appid as the library entry.
Nothing is downloaded, and any shortcut whose program ships an icon gets the
same treatment. This is the one part that wants `python-pillow`; without it
the entry is still added, just without the artwork.

Steam reads that directory when it starts, so the tile appears on its next
launch rather than immediately. Pass `--icon PATH` to build the artwork from
a different image, `--no-art` to leave the tile plain, and `--revert` to take
both the entry and its artwork away again.

Big Picture's task switcher then flips between Discord and your game with the
controller. It plays through whatever `AUDIO_DEVICE` console mode is using,
because it inherits `PULSE_SINK` from the session, and it records from
`AUDIO_INPUT_DEVICE` if you picked one.

Note the entry in `AUDIO_NEVER_MUTE`. A library shortcut is a Steam app like any
other, so without that exemption per-game audio focus counts Discord as a game
and mutes it the moment you look at the one you are playing.

Discord also keeps its own output and input choice, which means inheriting
`PULSE_SINK` and `PULSE_SOURCE` only decides where it *starts*: if its saved
device differs, the next call goes there instead — often a headset at the desk
while you are across the room. `AUDIO_PIN_VOICE` closes that by moving the
stream itself, which is the one thing an application cannot overrule, and
re-checking every poll so a stream that wanders back is moved again. It only
does this while a session is running, so Discord at your desk is left alone.

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
| `TRACKPAD_FIX` | `off` | Preload libextest for the trackpad. Only for a gamescope that cannot emulate input; on a modern one it sends the cursor to the desktop instead |
| `STEAM_BUTTON` | `on` | Let the Steam button open console mode |
| `RESTART_STEAM` | `on` | Start the desktop Steam client again when console mode ends, minimised to the tray, so the Steam button has a client to open Big Picture in next time |
| `AUDIO_FOCUS` | `on` | Mute games you are not looking at |
| `AUDIO_DEVICE` | *(follows display)* | HDMI monitor name (`Optoma UHD`) or device (`RODECaster Duo`). Kept until you change it in **Cachy Console** settings |
| `AUDIO_NEVER_MUTE` | `Discord` | Left audible even though Steam started it. Comma-separated names or appids. Read by the audio service, so restart it after editing |
| `AUDIO_PIN_VOICE` | `on` | Hold those streams on `AUDIO_DEVICE` / `AUDIO_INPUT_DEVICE`, moving them back if the app sends them elsewhere. Only while a session is running |
| `AUDIO_INPUT_DEVICE` | *(session default)* | Microphone for console mode, e.g. `HyperX Cloud III S Wireless`. Empty leaves input alone |
| `IGNORE_CONTROLLERS` | empty | Devices console mode should not treat as gamepads, as `0x31e3/0x1400`, comma separated. List them with `cachy-console controllers` |
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
gamescope.

**Getting a Steam button back.** The same fact runs the other way when you
leave: the button needs a client to talk to, and leaving console mode kills
gamescope, which takes the Steam inside it down too. `RESTART_STEAM` starts the
ordinary desktop client again, `-silent` so it returns to the tray rather than
throwing a window over whatever you went back to, and with none of what console
mode arranged for the television — `PULSE_SINK`, `PULSE_SOURCE`, gamescope's
nested-session workarounds — following it back to the desk. The desktop's HDMI
audio profile is restored first, so the client does not enumerate its devices
while the GPU still points at the TV.

Both `cachy-console` and `cachy-console-watch` do this, because which of them
outlives a session depends on how it ended: clicking the exit tile from inside
Big Picture has gamescope's reaper take the wrapper's process group down with
it, and the watcher is not running at all with `STEAM_BUTTON=off`. A lock
decides which one actually starts the client, and the client is started in its
own transient scope so that restarting the watcher service cannot take it with
it. Steam's second instance hands its arguments to the client that already holds
the IPC socket and exits, so the relaunch waits for gamescope's Steam to finish
dying before starting one, and tries again if what it started never appeared.

**HDMI audio.** GPU HDMI/DP audio exposes one stereo device at a time, and
PipeWire names it after the graphics card (`Navi 31 HDMI/DP Audio`) even when
that port is the TV. Settings save an `AUDIO_DEVICE` (the projector, a headset,
or another HDMI monitor). Console mode switches the GPU profile to that output,
moves already-playing streams onto it, renames the sink to the monitor's ELD
(e.g. Optoma UHD), and points Steam at it with `PULSE_SINK`. The choice is
kept until you pick a different one. Headset and other USB devices stay in the
list. The desktop HDMI device comes back when you leave.

**Per-game audio.** gamescope publishes which app it has focused; PipeWire can
mute one stream. A stream is treated as a game's only when its process, or one
of its ancestors, was started by Steam with `SteamGameId` set, so browsers,
music and Steam's own interface sounds are never touched. Nothing is muted
unless two or more games are actually producing audio, and every mute is undone
when the games close or the service stops. `AUDIO_NEVER_MUTE` exempts anything
that is technically a Steam app but is not a game — voice chat, which is worse
than useless if it goes quiet whenever you look at what you are playing. Names
there are matched against the stream's own label and against the process behind
it, because an Electron app's audio process is not reliably named after the app.

**The microphone.** `AUDIO_INPUT_DEVICE` is exported as `PULSE_SOURCE` to what
console mode starts, and nothing else: the desktop's default input is never
changed, so the mic at your desk keeps working for everything else. Only real
capture devices are offered, never the `.monitor` loopback PipeWire publishes
for every output. Leaving it empty leaves input alone entirely.

**Which controller is player one.** A game assigns players in the order the
kernel numbered the gamepads, so whatever holds `js0` is player one whether or
not it ever sends an event. That is a problem when something is only nominally a
gamepad. Keyboards with an analog mode — Wooting's, for one — publish a gamepad
endpoint as part of their USB descriptor, so it is there from boot, while Steam
Input's virtual pad cannot appear until Steam is up and therefore always lands
behind it. The symptom is a controller that moves nothing in the menus because
it is player two, and a player one that is a keyboard pretending to be a pad.
`IGNORE_CONTROLLERS` hides such a device by USB id, via SDL's own ignore list,
which is what both Steam and Proton's controller layer read. It is appended to
rather than replacing what Steam puts there, since Steam uses the same list to
hide the physical controller it presents through Steam Input. This applies to
console mode only, so the device is still a gamepad on the desktop:

```bash
cachy-console controllers   # names, USB ids, and which slot each one holds
```

**The trackpad, and why `TRACKPAD_FIX` is off.** Steam moves the trackpad cursor
by making XTEST calls against whatever X server it is on, and gamescope's own
XWayland handles them: gamescope is linked against `libeis` and logs
`Successfully initialized libei for input emulation`, so an XTEST call lands on
gamescope's cursor and the trackpad just works. extest intercepts those calls
before they get there and replays them against the *host* seat in host
coordinates — it will happily report your desktop's monitors while doing it —
which leaves gamescope's cursor untouched and nothing to click. So the fix for a
desktop session is the thing that breaks a gamescope one, and it stays off unless
your gamescope is too old to emulate input. `cachy-console status` reads the
`libeis` link and says which case you are in.

If you do turn it on, note where the preload is set: on the `env` that gamescope
execs, never exported. gamescope carries `CAP_SYS_NICE` for realtime scheduling,
and file capabilities put a process into glibc's secure-execution mode, where
`LD_PRELOAD` is only honoured for set-user-ID libraries. glibc does not merely
ignore it there, it *strips* it from the environment so it cannot reach children
— so an exported one reaches neither gamescope nor the Steam it starts, with the
only clue a single `cannot be preloaded` line.

**The trackpad prompt.** Steam drives the controller trackpad through XTEST. On
Wayland, XWayland turns that into an xdg-desktop-portal request — the "allow
remote interaction" dialog — and the permission dies with the Steam process, so
it returns on every restart. libextest implements those calls against
`/dev/uinput` instead, so there is nothing to approve.

## Troubleshooting

**It opened on the wrong screen.** Search for **Cachy Console**, save the
display you want, then if gamescope is already running exit and Steam-button
twice so the next session uses it.

**It opened on the wrong screen and "Exit Console Mode" does nothing.** Those two
together mean it is not console mode at all: it is Big Picture on the desktop,
and there is no session for the tile to end. A double press on the Steam button
does not launch anything — it asks the running client to switch to Big Picture —
so when the watcher is not there to turn that into a session, you get Big Picture
wherever the desktop client put it, usually the primary screen. Check with
`cachy-console status`, which says so in the services section, and start it again
if it has stopped:

```bash
systemctl --user start cachy-console-watch
```

The services come back on their own now, including from a plain kill, so this
should be self-correcting; it was not before, and the symptoms pointed at
displays rather than at a service.

**Audio is on the wrong monitor.** Search for **Cachy Console** and pick the
audio output (the projector, a headset, or another HDMI screen). That choice
is kept until you change it. If console mode is already running, Save switches
audio immediately; a new session also uses it.

**The refresh rate looks wrong.** `cachy-console-display probe` shows both SDL
views separately. If they disagree, set `REFRESH` explicitly.

**Nothing happens on the Steam button.**

```bash
systemctl --user status cachy-console-watch
journalctl --user -u cachy-console-watch -f
```

The watcher stands down when your chosen display is switched off, so Big Picture
stays on the desktop rather than opening somewhere you cannot see.

**Steam did not come back after leaving console mode.** The button has nothing
to open without it, so check `RESTART_STEAM` is not `off`, then:

```bash
cachy-console status                        # says whether the client comes back
journalctl --user -u cachy-console-watch    # "bringing the desktop Steam client back"
```

It comes back minimised to the tray, so an empty taskbar is not a failure — look
for the tray icon, or `pgrep -x steam`. If it really is missing, starting Steam
by hand is enough: from then on the Steam button works as usual.

**A Gamescope WSI Layer Error dialog appears and the controller cannot click
OK.** The game opened a Vulkan window on the desktop instead of inside
gamescope, and the cursor was grabbed by the nested session. Console mode now
starts Steam without the host `WAYLAND_DISPLAY` so that dialog stays on
gamescope's X11, where the trackpad/right-stick mouse can dismiss it. Exit and
Steam-button twice to pick up the change.

**It refuses to start.** Starting console mode restarts Steam, which would close
a running game, so it stops and says so. Quit the game, or set
`CACHY_CONSOLE_FORCE=1`.

**A game is silent when it should not be.**

```bash
cachy-console-audio --status    # streams, their games, and the focused app
```

Stopping the service unmutes everything it muted.

**The controller is player two and cannot move the menus.** Something else is
holding the first controller slot — usually a keyboard with an analog gamepad
mode, which is a gamepad to the kernel from boot:

```bash
cachy-console controllers   # the one on js0 is player one
```

Put that device's USB id in `IGNORE_CONTROLLERS`, then exit and Steam-button
twice. It stays a gamepad on the desktop.

**No cursor at all from the trackpad.** Usually `TRACKPAD_FIX=on` on a gamescope
that emulates input, which sends the trackpad to the desktop instead:

```bash
cachy-console status   # the "trackpad" section says which case you are in
```

Set `TRACKPAD_FIX=off`, then exit and Steam-button twice. If it is already off,
check for `cannot be preloaded` in the startup output — that means the opposite
problem, a preload that was refused rather than one that hijacked the cursor.

| gamescope | `TRACKPAD_FIX=off` | `TRACKPAD_FIX=on` |
| --- | --- | --- |
| linked against `libeis` | cursor works | no cursor |
| not linked | no cursor | cursor works |

## Not supported

- **X11 sessions.** Some of this works, but it is built and tested for Wayland.
- **Turning your other monitors off.** Doing that needs compositor-specific
  code, and gamescope can target a display without it.
- **Replacing your session.** This is not a SteamOS-style boot-to-Steam setup.

## License

MIT. See [LICENSE](LICENSE).
