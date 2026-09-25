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

On CachyOS or Arch, the package is the path that updates with the system:

```bash
paru -S cachy-console-git
cachy-console first-run
```

`first-run` enables the Steam-button and audio services, picks a display, and
queues Exit / Discord / Spotify library tiles. Steam rewrites its shortcut file
from memory when it quits, so those tiles are written the next time Steam is
not running — you do not have to close it first.

The older one-command home install still works. **pacman** installs the
dependencies; the script clones this repo and copies files into your home
directory.

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

If Steam is running, `cachy-console shortcut` queues the entry and writes it
the next time Steam is not — the watcher flushes that queue, and so does
leaving console mode. You can still pass `--force` to write immediately, which
Steam will discard when it exits. An older "Exit Game Mode" tile that still
pointed at `projector-exit` is updated to `cachy-console-exit` by that same
command. `cachy-console shortcut --queue-defaults` queues Exit, Discord and
Spotify together.

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
has to be relaunched as its child. What there *is* a way around is waiting for
the old client to finish quitting before anything appears. gamescope is started
straight away, with a small launcher as its child in place of Steam; the
launcher waits for the desktop client to exit and then starts the new one. So
the chosen screen goes black and belongs to console mode within a couple of
seconds of the press, and Steam's own shutdown (often ten seconds or more)
happens behind it instead of in front of it. Before this, the whole chain was
serial and took about 25 seconds.

The watcher also looks for the Big Picture window five times a second instead of
twice, reading window properties straight from the X server rather than running
`xprop` for each one, which is about thirty times cheaper per look. Scanning
`/proc` for a hand-started session stays at once a second, and while a game runs
it slows to twice a second, since nothing there needs a quick answer.

That was thirty seconds longer until the relaunch lock stopped leaking. The lock
exists so that two things racing to put the desktop client back cannot start two
clients, and it is held on a file descriptor — which a child inherits, so the
Steam client it started carried it for as long as Steam ran. The next start waits
on that lock before touching Steam, and so waited out its whole timeout every
time, in silence, with Big Picture sitting on whichever screen it had opened on
for the duration. It now says when it waits, and the client no longer takes the
lock with it.

**The Discord already open on your desktop cannot be moved into console mode.**
A window belongs to the compositor its client connected to, and gamescope is a
separate nested one — the same reason Big Picture has to be relaunched rather
than moved. So it is one Discord at a time, which follows you in and out:

```bash
cachy-console shortcut --name Discord --exe /usr/bin/discord   # Steam closed
```

Spotify works the same way, with two extra options:

```bash
cachy-console shortcut --name Spotify --exe /usr/bin/spotify-launcher \
    --process spotify --color 121212                           # Steam closed
```

`--process spotify` because the tile runs `spotify-launcher`, which becomes a
program called `spotify`. Nothing about the launcher's name says so, and without
being told the wrapper would not recognise a Spotify already open on the desktop:
the tile's copy would hand off to it and exit. `--color 121212` puts the tile on
Spotify's own near-black instead of the icon's green, which on a green backdrop
is a green circle on green. Spotify also ignores `SIGTERM`, `SIGINT` and `SIGHUP`
alike, so a signal only ever ends it with a kill 15 seconds later; the wrapper
asks any MPRIS media player belonging to the app to quit over D-Bus first, which
Spotify does in about a second. `Spotify` is in `AUDIO_NEVER_MUTE` and
`MOUSE_LAYOUT_APPS` by default, so music keeps playing while a game has focus
and the trackpad is a mouse over it.

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

Expect Discord's own **Voice & Video** screen to keep naming the devices it
saved at your desk while this is happening. It is not reading them back from the
stream, and the stream is what you hear and what is heard: checked on a call
here, Discord showed a desk interface for both while its capture sat on the
console's microphone and its playback on the television. Believe
`cachy-console-audio --status` over that screen — it prints the device each
stream is actually on.

**Mouse, keyboard and calls all work in a tile; screen sharing does not.** The
keyboard is the easy half: Steam types through XTEST against gamescope's own X
server, and that arrives whatever else is set — measured here, Ctrl+K opened
Discord's quick switcher and Escape closed it again.

The trackpad needs three things, and each is silent when it is missing. The
first is a layout that makes it a mouse at all. Steam applies a controller
layout per app to whatever has focus, and Discord is a non-Steam shortcut with
none chosen, so it gets Steam's last-resort *Gamepad FPS* template: the right
trackpad drives the right stick of a virtual gamepad and the left one a d-pad.
Discord ignores gamepads, so the cursor that moved over Big Picture a moment
earlier stops dead the moment Discord has focus. Console mode fills in Steam's
*Web Browser* template for the shortcuts named in `MOUSE_LAYOUT_APPS` (Discord and Spotify by
default) on the Steam Controller:

| Control | In Discord |
| --- | --- |
| Right trackpad | moves the cursor; pressing it clicks |
| Right trigger / left trigger | left click / right click |
| Left trackpad | scrolls |
| A / B / X | Enter / back / Steam keyboard |

It only fills a layout in where you have not picked one, so a layout chosen in
Steam's controller settings wins. It is written in the gap between the desktop
client exiting and the session's starting, because Steam writes these files back
from memory when it exits. They name a non-Steam shortcut by its lowercased name
(`discord`), not its appid; an appid entry is ignored and the fallback template
applies anyway.

The other two are `TRACKPAD_FIX` and `GRAB_CURSOR`:

- **`TRACKPAD_FIX=off`** because this gamescope already turns Steam's trackpad
  XTEST into its own cursor, so Discord and Spotify follow that pointer and the
  desk mouse stays put. `on` preloads extest, which makes the trackpad a real
  mouse on the desktop seat — the two cursors become the same pointer. Only
  needed if gamescope was built without libeis.
- **`GRAB_CURSOR=on`** because a gamescope nested on a desktop does not draw a
  cursor of its own. It hands the image to whatever is hosting its window and
  lets that draw one, which KWin does — at the *desktop's* pointer, and only
  while that is over the session's window. On another screen there is no cursor
  in the session at all. Asking for the grab is what makes gamescope draw its
  own, and it keeps the pointer from sliding out onto the desk's monitor.

One limit to know: under the grab, gamescope takes relative motion and ignores
absolute warps, so a trackpad configured as an *absolute* pad (touch a corner,
the cursor goes to that corner) will not move anything. The default relative
behaviour is what works.

Sharing a screen is the one that cannot be made to work from inside the session,
and the reason is not Discord. Its X11 capture reads the display's root window,
and an Xwayland server does not keep one to read — this is true of the desktop's
Xwayland as much as gamescope's. Individual windows fare no better for the case
that matters: Steam and anything built on Vulkan hand the compositor a buffer
rather than drawing into an X pixmap, so a capture of the window comes back
black. The route that does work is the PipeWire portal, and the portal's source
picker is a window on the *desktop* compositor, which is exactly the thing a
session on the television cannot reach. So: share from the Discord at your desk,
where picking the television as the source captures console mode along with it.

## Configuration

`~/.config/cachy-console/config`, written by `cachy-console settings` and safe to
edit by hand. `cachy-console setup` and `./install.sh` only update the display,
VRR and HDR; they leave `AUDIO_NEVER_MUTE` and the rest as you set them.

| Setting | Default | Meaning |
| --- | --- | --- |
| `DISPLAY` | *(required)* | Connector to use, e.g. `HDMI-1`. Never `auto` and never an index: if this display is off, console mode waits instead of using another screen |
| `RESOLUTION` | `auto` | Follow the display's current setting, or force e.g. `1920x1080` |
| `REFRESH` | `auto` | Follow the display's current setting, or force e.g. `120` |
| `VRR` | `on` | FreeSync / G-Sync inside console mode |
| `HDR` | `off` | Only worth enabling if display and games support it |
| `TRACKPAD_FIX` | `off` | Preload libextest so the trackpad is also a mouse on the desk. Off (the default) keeps the session cursor and the desktop cursor as two pointers. On only for a gamescope built without libeis |
| `MOUSE_LAYOUT_APPS` | `Discord, Spotify` | Non-Steam shortcuts, by name or appid, that get a trackpad mouse layout on the Steam Controller unless you picked one. Empty turns it off |
| `GRAB_CURSOR` | `on` | Hold gamescope in relative mouse mode, which is what makes a nested gamescope draw its own cursor and keeps the pointer in the session. Off hands the cursor back to the desktop, which draws one only while the desktop's pointer is over the session's window |
| `STEAM_BUTTON` | `on` | Let the Steam button open console mode |
| `RESTART_STEAM` | `on` | Start the desktop Steam client again when console mode ends, minimised to the tray, so the Steam button has a client to open Big Picture in next time |
| `AUDIO_FOCUS` | `on` | Mute games you are not looking at |
| `AUDIO_DEVICE` | *(follows display)* | HDMI monitor name (`Optoma UHD`) or device (`RODECaster Duo`). Kept until you change it in **Cachy Console** settings |
| `AUDIO_NEVER_MUTE` | `Discord, Spotify` | Left audible even though Steam started it. Comma-separated names or appids. Read by the audio service, so restart it after editing |
| `AUDIO_PIN_VOICE` | `on` | Hold those streams on `AUDIO_DEVICE` / `AUDIO_INPUT_DEVICE`, moving them back if the app sends them elsewhere. Only while a session is running |
| `AUDIO_INPUT_DEVICE` | *(session default)* | Microphone for console mode, e.g. `HyperX Cloud III S Wireless`. Empty leaves input alone |
| `IGNORE_CONTROLLERS` | empty | Devices console mode should not treat as gamepads, as `0x31e3/0x1400`, comma separated. List them with `cachy-console controllers`. Hides them from Steam only; `cachy-console hide-controllers` hides them from games too |
| `PRIMARY_CONTROLLER` | `steam` | Which controller is player one when several are connected: `steam`, `playstation`, `xbox`, `switch`, or `off` for Steam's own order. Also in Cachy Console |
| `PRIMARY_ONLY` | `on` | Hide every other controller while that one is connected, so Big Picture and games only see player one. Off for local multiplayer. Needs the USB helper `./install.sh` can grant |
| `STEAM_PAD_AS_XBOX` | `on` | Show games Steam's controller as an Xbox 360 pad (`045e:028e`) instead of Steam's own virtual pad (`28de:11ff`), which older games that only accept pads they know refuse — Dead Rising 2 among them. Off only for a game that needs to see the real Steam pad |
| `EXTRA_GAMESCOPE_ARGS` | empty | Passed straight through, e.g. `--mangoapp` |

## How it works

**Picking the display.** gamescope's `--display-index` is an SDL index, so SDL
is asked directly rather than any compositor — that is why the same build works
on GNOME and Plasma. SDL is asked twice, because neither backend tells the
whole truth: its **x11** backend names displays by connector and numbers them
the way gamescope expects, but under XWayland it can report 60Hz for a 240Hz
screen, while its **wayland** backend reports the true mode but names displays
by manufacturer. Names and indices come from the first, everything about the
screen itself from the second. Connector names are normalized so Plasma's
`HDMI-A-1` and GNOME's `HDMI-1` stay the same saved display.

Lining the two views up is not as simple as matching positions, because
**XWayland multiplies the whole desktop by the largest scale any screen uses**.
One screen set to 125% therefore renames every position on the desktop: a
5120x1440 monitor at +1920 is reported as 6400x1800 at +2400, and its 240Hz
comes out as 12Hz. Matching positions for equality merges only whichever screen
sits at the origin, and the rest are left described by numbers belonging to no
screen at all. What the multiplication cannot do is reorder the screens, so they
are paired by rank in position order instead — and only when the two views agree
on how many screens there are, on which of them sit against an axis, on a single
multiplier between their positions, and on each mode fitting inside the box x11
draws around it. If they do not line up, `resolve --strict` refuses rather than
answer with a mode it cannot vouch for.

The index is the only lever there is, and it is a sharp one. `--prefer-output`
is read by gamescope's DRM backend alone; nested, the connector name is passed
and ignored, and the index goes straight to SDL as the display to put the window
on. SDL, handed an index that is not there, does not fail — it resolves it to
display ID 0 and uses the primary screen, which is the monitor you game on. So
every way of getting the index wrong has exactly one symptom: console mode opens
on the wrong screen, with nothing anywhere saying so.

An index is only meaningful for one arrangement of screens, and turning the
television on changes the arrangement while you are reaching for the Steam
button. Two things follow from that, and both used to happen:

- **A layout read mid-change.** A screen that has just woken is placed at 0,0,
  on top of whatever is really there, until the arrangement is applied. Pairing
  the two SDL views while that is true attributes one screen's mode to another —
  how a projector came to be asked for 240Hz — so a view with two screens at one
  position is not paired against at all. Readings taken during
  it also agree with each other perfectly while describing a layout about to
  change, so agreement alone is not enough: a reading with two screens at one
  position is refused, and console mode waits for the arrangement to hold.
- **An index that goes stale before it is used.** SDL resolves it when it
  creates the window, not when we choose it, and leaving Big Picture happens in
  between, which is long enough for a screen to sleep or wake and renumber the
  list. So the display is checked again immediately before gamescope starts
  (and fully re-resolved if anything moved), and the session says which index
  it used:
  `Console mode on HDMI-A-1 (display 2) at 1920x1080@60Hz`. A screen named in
  that line with the session on a different monitor is this fault; the number is
  what tells them apart.

The same wake brings the screen's HDMI audio port up a little after the screen,
so the saved audio device matches nothing and sound stays wherever the desktop
had it — the same fault wearing different clothes, and it looks just as much
like the saved settings being ignored. The audio route is retried for a few
seconds rather than given up on at the first miss. None of this costs anything
noticeable when the screens were already on.

**Session environment.** The Steam-button watcher and per-game audio run as
systemd user services. GNOME usually exports `DISPLAY` and `XAUTHORITY` into
that manager; Plasma often does not. An autostart entry and a small wrapper
fill those in from the sockets your session already created, on both desktops.

**The Steam button.** Pressing it twice does not launch anything — it flips the
*already running* Steam client into Big Picture, so there is no command to
intercept. Steam only does that flip when its own window is focused, so a
double press over a browser used to do nothing. The watcher also reads the
Steam button from the controller itself and starts console mode from that,
whether Steam is focused or sitting in the tray. gamescope still cannot adopt
a window owned by another compositor, so an already-open Big Picture is
relaunched inside gamescope the same way.

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
which is what Steam reads. It is appended to rather than replacing what Steam
puts there, since Steam uses the same list to hide the physical controller it
presents through Steam Input. This applies to console mode only, so the device
is still a gamepad on the desktop:

```bash
cachy-console controllers   # names, USB ids, and which slot each one holds
```

That hides it from Steam, not from the games Steam starts. Steam writes its own
list into every game's environment, replacing this one, and that variable is
the only per-device filter Proton's input layer has — so under Proton the
keyboard is still an Xbox pad, and can still be player one. For a device whose
gamepad is its own Xbox-protocol USB interface, as the Wooting's is (a separate
`xpad` interface beside the keyboard's HID ones), this hides it from everything:

```bash
cachy-console hide-controllers   # asks for your password once
```

It writes a udev rule switching off just that interface for each device in
`IGNORE_CONTROLLERS`, and switches it off now. The keyboard keeps typing; the
pad is gone system-wide, desktop included, which is the point for a keyboard
that is only ever a keyboard. Take the id out of the list and run it again to
get the pad back. A device whose gamepad shares a HID interface with its keys
cannot be split this way, and is left alone.

**Steam Controller first, even with a DualSense connected.** Among real
controllers, Steam gives out player slots in the order the controllers turn up.
A DualSense is there the moment Steam starts, while a Steam Controller still
has to reach its dongle, so the DualSense became player one. In a single-player
game like Dead Rising 2, the Steam Controller then drove nothing at all. On top
of that, in games Steam thinks can read a PlayStation pad themselves, the
DualSense skipped Steam Input entirely and went to the game through Proton,
outside Steam's order.

`PRIMARY_CONTROLLER` (default `steam`, also in Cachy Console under *Player one*)
fixes both for the session. `cachy-console-pads` runs next to the session's
Steam, puts PlayStation controllers through Steam Input in every game so there
is one order to change, and moves the chosen kind into player one with Steam's
own *Rearrange controller order*. It does this again whenever a controller
connects, but a reorder you make by hand in the Quick Access menu afterwards is
left alone. Your PlayStation setting is written down first and put back once
the desktop client is up again.

`PRIMARY_ONLY` (default `on`, the *Hide other controllers* box in Cachy Console)
then switches every other physical pad off at USB, so Big Picture and Proton
games cannot see them either. Steam's own ignore list never reaches a game
Steam starts, which is why a DualSense still stole player one in Dead Rising 2
after the reorder alone. The others come back when player one disconnects, when
the session ends, or when the box is off (local multiplayer). A keyboard that
is also a pad is only switched off at its gamepad interface, so it still types.
This needs the USB helper `./install.sh` grants once.

Steam only offers that reorder through its UI, so the helper reaches it over the
client's DevTools port. That port is turned on by
`~/.local/share/Steam/.cef-enable-remote-debugging`, the same file Decky Loader
uses, and listens on `127.0.0.1` only. `PRIMARY_CONTROLLER=off` never creates
it, but it doesn't remove one that is already there.

**The trackpad, and why `TRACKPAD_FIX` is off.** Steam moves the trackpad cursor
by making XTEST calls against whatever X server it is on. This gamescope hosts
an emulated-input socket and turns those calls into its own pointer, so Discord
and Spotify follow the session cursor and the desk mouse stays where you left
it. `TRACKPAD_FIX=on` intercepts the same calls with extest and writes them to
`/dev/uinput` on the desktop seat instead — one pointer, shared. That is the
fallback for a gamescope built without libeis, not the usual path.

The grab still matters: gamescope draws its cursor only in relative mouse mode.
An absolute pad (touch a corner, the cursor goes to that corner) will not move
anything. The default relative behaviour is what works.

Note where the preload is set: on the `env` that gamescope
execs, never exported. gamescope carries `CAP_SYS_NICE` for realtime scheduling,
and file capabilities put a process into glibc's secure-execution mode, where
`LD_PRELOAD` is only honoured for set-user-ID libraries. glibc does not merely
ignore it there, it *strips* it from the environment so it cannot reach children
— so an exported one reaches neither gamescope nor the Steam it starts, with the
only clue a single `cannot be preloaded` line.

**Why extest has a guard in front of it.** libextest sizes its device from the
Wayland outputs, once, on the first XTEST call — the first time the trackpad
moves. Inside console mode that lookup cannot succeed: Steam gets no
`WAYLAND_DISPLAY` (with gamescope's own socket, games show a Vulkan error), and
gamescope's socket has no `zxdg_output_manager_v1` anyway. libextest panics on
either, the panic aborts Steam, and Steam Input goes with it, so the touch
you'd feel on the pad and the cursor both stop. Whatever Steam had started
(Discord, say) is then left orphaned in a session with nothing to draw it.

`libcachy-extest-init.so`, built by `install.sh` into
`~/.local/lib/cachy-console/{lib,lib32}` and preloaded ahead of libextest, does
that lookup at Steam's start instead. It points it at the desktop compositor,
KWin, and then takes the variable away again, so Steam and its games still see
no `WAYLAND_DISPLAY`. It only acts inside the 32-bit Steam client and only when
the desktop socket answers. If it isn't built, extest is left off and `status`
says so, because a trackpad that does nothing is better than one that crashes
Steam. Separately, when Steam exits inside the session, whatever it left running
is closed, so gamescope ends instead of freezing on the last frame.

**The trackpad prompt.** Steam drives the controller trackpad through XTEST. On
Wayland, XWayland turns that into an xdg-desktop-portal request — the "allow
remote interaction" dialog — and the permission dies with the Steam process, so
it returns on every restart. libextest implements those calls against
`/dev/uinput` instead, so there is nothing to approve.

## Troubleshooting

**It opened on the wrong screen.** Search for **Cachy Console**, save the
display you want, then if gamescope is already running exit and Steam-button
twice so the next session uses it.

If the saved display is already right, check what the session thought it was
doing — the first line names both the screen and the index it used:

```bash
head -1 /run/user/$(id -u)/cachy-console-session.log
```

A screen there that is not where the session opened means the index was read
against a different arrangement of monitors than the one SDL saw a moment later,
and SDL puts a window with an index it cannot place on the primary screen without
complaining. That is resolved as late as it can be now, and a layout still
settling is waited out rather than trusted, so it should not recur — but the
window is never quite zero, and that line is how to tell.

Two other things that look identical from the couch: the display being turned off
*during* a session, after which the desktop moves the window to a screen that is
still there and gamescope neither notices nor minds; and Big Picture opening on
the desktop rather than in console mode at all, which is the next entry.

**The saved screen was off, and Big Picture stayed on the desktop.** This is
deliberate — console mode will not quietly use a different screen — and it is
also the single most convincing impostor of the bug above, because what you see
is full-screen Steam on the wrong monitor. It is not a session: nothing was
started, and the watcher keeps checking, so turning the screen on while Big
Picture is still open starts console mode there with no second press.

The watcher now says so on screen as well as in the journal, once per wait:
*Console mode is waiting for HDMI-A-1*. If you never see notifications from it,
check that your desktop can show them at all before blaming the watcher — on
Plasma, `org.freedesktop.Notifications` is claimed by plasmashell's Notifications
widget, and with that widget missing from the panel the name is never claimed,
activation times out, and every notification from every application is silently
dropped:

```bash
busctl --user list | grep Notifications   # "(activatable)" with no owner means nothing is listening
```

Add the Notifications widget back to the system tray and the messages appear.

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

**Nothing happens on the Steam button.** If Big Picture is already open on the
desktop, close it first. The button does not launch anything — it flips the
running client into Big Picture — so with that window already up the press
changes nothing for the watcher to react to, and after a session has ended the
watcher deliberately ignores a Big Picture it has not seen close, so that a
client restoring itself into one cannot start console mode in a loop.
`journalctl --user -u cachy-console-watch` says so when this is what is
happening.

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
twice. It stays a gamepad on the desktop. If it is still player one inside
games, run `cachy-console hide-controllers`; Steam does not pass the list on to
them.

**The Steam Controller does nothing in a game while a DualSense is on.** The
DualSense has player one. Check that *Player one* in Cachy Console (or
`PRIMARY_CONTROLLER`) is *Steam Controller*, and look at what the helper did:

```bash
cachy-console-pads list     # each controller's player slot (0 is player one)
grep cachy-console-pads "$XDG_RUNTIME_DIR/cachy-console-session.log"
```

**A DLC, store, or overlay page shrinks to a postage stamp in the corner.**
That window is a few hundred pixels across, and without a nested size gamescope
shows it at 1:1 on the television. Console mode sets the nested size to the
display and `--force-windows-fullscreen`, so those windows fill the screen.

**Switching from Discord back to a game leaves the game tiny in the corner.**
Discord and the game used to share one Xwayland. Opening Discord is an X11
focus loss; Proton drops exclusive fullscreen and comes back presenting a
small image in a black 1920×1080 window. `--force-windows-fullscreen` cannot
fix that: it resizes the window, not the game's swapchain. Console mode
gives Steam two Xwaylands (the SteamOS layout): the game stays fullscreen on
`STEAM_GAME_DISPLAY_0` (the second), Discord and Big Picture live on Steam's
own `DISPLAY` (the first), and the switch is only a compositor change. The
library wrapper puts Discord on that first display even when Steam launched
the tile as a game on the second. Needs a new session if this one started
before two Xwaylands were the default.

**An older game ignores the controller that works in Big Picture.** Some games
only accept gamepads whose USB id they know, and Steam's virtual pad (`28de:11ff`)
is not one of them; Dead Rising 2 is one ("Unsupported gamepad"), with its own
*Controller* switch in PC Settings greyed out. Console mode has Proton present
the pad as an Xbox 360 controller instead, for every game, which is what
`STEAM_PAD_AS_XBOX=on` does; check it is not off. Proton itself does this for only
a few titles, so on the desktop, or with it off, the same thing per game is
this as the launch options:

```text
PROTON_SPOOF_STEAMINPUT_VIDPID=1 %command%
```

What a game loses by it is the real pad's identity: an SDL game running under
Proton shows Xbox button prompts rather than PlayStation ones for a DualSense
going through Steam Input.

**The cursor works in Big Picture but stops in Discord.** That is Discord's
controller layout, not the cursor: with none chosen it is a gamepad layout.
The startup output should say `Discord (…): trackpad mouse layout in …` the first
time; if it does not, the shortcut is not named Discord (add its name to
`MOUSE_LAYOUT_APPS`), or you chose a layout for it yourself, which is kept. Steam
logs the one it used in `~/.local/share/Steam/logs/controller_ui.txt`:
`Local Selection Path ... controller_neptune_webbrowser.vdf` is the mouse layout,
`Last Resort Path ... gamepad_fps` the gamepad one.

**No cursor at all from the trackpad.** Check the controller first, because a
Steam Controller switches itself off after a few minutes and nothing on screen
says so: Big Picture is still there, the Steam keyboard still types, and the
trackpad is simply dead.

```bash
cachy-console controllers   # says when a dongle has nothing connected to it
cachy-console status        # the "trackpad" section checks the rest
```

Press the controller's Steam button to wake it. If it is awake, `GRAB_CURSOR`
has to be on so gamescope draws a cursor of its own, and `TRACKPAD_FIX` should
stay off so that cursor is not the desktop's. `status` warns for either one
being the wrong way around. A third cause is a leftover extest preload: if
`TRACKPAD_FIX` is on and you see `cannot be preloaded` in the startup output,
run `sudo ldconfig`, or check that `/dev/uinput` is writable.

| | `TRACKPAD_FIX=off` | `TRACKPAD_FIX=on` |
| --- | --- | --- |
| `GRAB_CURSOR=off` | gamescope cursor, drawn only while the desktop pointer is over the window | one pointer: the desktop's |
| `GRAB_CURSOR=on` | two pointers: trackpad in the session, mouse on the desk | one pointer: the trackpad moves the desk mouse |

## Not supported

- **X11 sessions.** Some of this works, but it is built and tested for Wayland.
- **Turning your other monitors off.** Doing that needs compositor-specific
  code, and gamescope can target a display without it.
- **Replacing your session.** This is not a SteamOS-style boot-to-Steam setup.

## License

MIT. See [LICENSE](LICENSE).
