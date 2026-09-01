#!/usr/bin/env bash
# Install cachy-console for the current user.
#
# Everything goes under $HOME: no root, no system files touched, and uninstall
# is a matter of deleting what this created. The one exception is optional and
# asked for explicitly -- granting gamescope CAP_SYS_NICE needs sudo, and
# without it gamescope cannot use realtime scheduling.
#
#   ./install.sh                 install, enable the services, run setup
#   ./install.sh --no-services   install the commands only
#   ./install.sh --no-setup      skip the interactive display picker
set -euo pipefail

SRC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
UNIT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/systemd/user"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

WITH_SERVICES=1
WITH_SETUP=1

say() { printf '%s\n' "$*"; }
warn() { printf 'install: %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

while (( $# )); do
    case "$1" in
        --no-services) WITH_SERVICES=0 ;;
        --no-setup)    WITH_SETUP=0 ;;
        -h|--help)     sed -n '2,10p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *)             warn "unknown option: $1"; exit 1 ;;
    esac
    shift
done

say "== checking what you have =="

missing=()
for cmd in steam gamescope python3 pactl xprop; do
    if have "$cmd"; then
        printf '  %-12s yes\n' "$cmd"
    else
        printf '  %-12s MISSING\n' "$cmd"
        missing+=("$cmd")
    fi
done

# SDL is loaded through ctypes rather than executed, so `have` cannot see it.
if python3 -c 'import ctypes; ctypes.CDLL("libSDL2-2.0.so.0")' 2>/dev/null; then
    printf '  %-12s yes\n' "sdl2"
else
    printf '  %-12s MISSING\n' "sdl2"
    missing+=(sdl2)
fi

if (( ${#missing[@]} )); then
    say
    warn "missing: ${missing[*]}"
    say "  install them with:"
    say "    sudo pacman -S --needed gamescope sdl2 libpulse xorg-xprop"
    say "  Steam comes from the same place if you do not have it:"
    say "    sudo pacman -S steam"
    say
    read -rp "Carry on anyway? [y/N] " reply
    [[ "${reply,,}" == y* ]] || exit 1
fi

say
say "== installing =="
mkdir -p "$BIN_DIR"
for tool in cachy-console cachy-console-display cachy-console-watch \
            cachy-console-audio cachy-console-exit cachy-console-shortcut \
            cachy-console-settings cachy-console-session; do
    install -m755 "$SRC/bin/$tool" "$BIN_DIR/$tool"
    printf '  %s -> %s\n' "$tool" "$BIN_DIR"
done

# Library tiles from the older projector scripts still call this name.
cat > "$BIN_DIR/projector-exit" <<'EOF'
#!/usr/bin/env bash
exec "$(dirname -- "$(readlink -f -- "$0" || echo "$0")")/cachy-console-exit" "$@"
EOF
chmod 755 "$BIN_DIR/projector-exit"
printf '  %s -> %s (compat)\n' "projector-exit" "$BIN_DIR"

mkdir -p "$APP_DIR"
install -m644 "$SRC/share/applications/cachy-console.desktop" "$APP_DIR/"
install -m644 "$SRC/share/applications/cachy-console-settings.desktop" "$APP_DIR/"
printf '  %s -> %s\n' "desktop entries" "$APP_DIR"

# Plasma often does not copy DISPLAY/XAUTHORITY into systemd --user. This
# autostart does it on both GNOME and KDE after the session is up.
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
mkdir -p "$AUTOSTART_DIR"
install -m644 "$SRC/share/autostart/cachy-console-session-env.desktop" \
    "$AUTOSTART_DIR/cachy-console-session-env.desktop"
printf '  %s -> %s\n' "session autostart" "$AUTOSTART_DIR"

# A PATH without ~/.local/bin makes every command here look uninstalled, which
# is a confusing first impression.
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        say
        warn "$BIN_DIR is not on your PATH."
        if [[ "${SHELL##*/}" == fish ]]; then
            say "  add it with:  fish_add_path $BIN_DIR"
        else
            say "  add it with:  echo 'export PATH=\"\$PATH:$BIN_DIR\"' >> ~/.bashrc"
        fi
        ;;
esac

if (( WITH_SERVICES )); then
    say
    say "== services =="
    mkdir -p "$UNIT_DIR"
    for unit in cachy-console-watch cachy-console-audio; do
        install -m644 "$SRC/systemd/$unit.service" "$UNIT_DIR/$unit.service"
        printf '  %s -> %s\n' "$unit.service" "$UNIT_DIR"
    done
    systemctl --user daemon-reload
    systemctl --user enable --now cachy-console-watch.service
    systemctl --user enable --now cachy-console-audio.service
    say "  enabled: the Steam button opens console mode, and only the game you"
    say "           are looking at is audible."
fi

# gamescope's --rt flag is silently ignored without this capability, and the
# difference shows up as stutter under load rather than as an error.
if have gamescope && ! getcap "$(command -v gamescope)" 2>/dev/null | grep -q cap_sys_nice; then
    say
    say "== realtime scheduling =="
    say "  gamescope can hold its frame pacing under load only with CAP_SYS_NICE."
    say "  This needs root, and is the only part of the install that does."
    read -rp "  Grant it now with sudo? [Y/n] " reply
    if [[ "${reply,,}" != n* ]]; then
        sudo setcap CAP_SYS_NICE=eip "$(command -v gamescope)" &&
            say "  granted." || warn "could not set the capability; carrying on without it."
    else
        say "  skipped. Grant it later with:"
        say "    sudo setcap CAP_SYS_NICE=eip $(command -v gamescope)"
    fi
fi

if (( WITH_SETUP )); then
    say
    "$BIN_DIR/cachy-console" setup
fi

say
say "Installed. Useful commands:"
    say "  cachy-console settings    open Cachy Console (pick or change the display)"
say "  cachy-console status     check everything"
say "  cachy-console exit       back to the desktop"
say "  cachy-console shortcut   add a controller-clickable exit to your library"
