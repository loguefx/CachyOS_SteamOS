#!/usr/bin/env bash
# One-command home install for people who do not want the AUR package.
#
# Prefer:  paru -S cachy-console-git && cachy-console first-run
# This script is the fallback: pacman for dependencies, then clone the repo
# and run install.sh into your home directory.
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/loguefx/CachyOS_SteamOS/main/get.sh)
#
# Extra arguments are passed to install.sh (--no-setup, --no-services).
# Override the clone location with CACHY_CONSOLE_SRC=/some/path.
set -euo pipefail

REPO="${CACHY_CONSOLE_REPO:-https://github.com/loguefx/CachyOS_SteamOS.git}"
DEST="${CACHY_CONSOLE_SRC:-$HOME/CachyOS_SteamOS}"
PACMAN_PKGS=(git steam gamescope sdl2 libpulse xorg-xprop tk)

say() { printf '%s\n' "$*"; }
warn() { printf 'get.sh: %s\n' "$*" >&2; }
die() { warn "$*"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

if [[ "${1-}" == -h || "${1-}" == --help ]]; then
    sed -n '2,11p' "$0" | sed 's/^# \?//'
    exit 0
fi

# curl | bash leaves stdin on the pipe, so later prompts would get EOF.
# Reattach the terminal when one exists. `bash <(curl …)` already has a tty.
if [[ ! -t 0 ]]; then
    exec 0</dev/tty || true
fi

have pacman || die "need pacman (CachyOS or Arch). This installer will not use another package manager."

say "== packages (pacman) =="
sudo pacman -S --needed "${PACMAN_PKGS[@]}"

# libextest lives on the AUR. Offer it only when an AUR helper is already here;
# we will not install paru/yay, and we will not add a third-party repo.
if ldconfig -p 2>/dev/null | grep -q 'libextest\.so'; then
    say "  libextest       yes"
elif have paru; then
    say
    say "== optional: libextest (AUR, via paru) =="
    say "  stops the Steam controller trackpad asking for permission"
    read -rp "  Install libextest-git with paru? [Y/n] " reply
    if [[ "${reply,,}" != n* ]]; then
        paru -S --needed libextest-git || warn "paru could not install libextest-git; carrying on without it."
    fi
elif have yay; then
    say
    say "== optional: libextest (AUR, via yay) =="
    say "  stops the Steam controller trackpad asking for permission"
    read -rp "  Install libextest-git with yay? [Y/n] " reply
    if [[ "${reply,,}" != n* ]]; then
        yay -S --needed libextest-git || warn "yay could not install libextest-git; carrying on without it."
    fi
else
    say
    say "  optional later:  paru -S libextest-git"
    say "  (AUR; not installed automatically, because that is not pacman)"
fi

say
say "== source =="
if [[ -d "$DEST/.git" ]]; then
    say "  updating $DEST"
    git -C "$DEST" pull --ff-only
elif [[ -e "$DEST" ]]; then
    die "$DEST already exists and is not a git checkout.
  move it aside, or set CACHY_CONSOLE_SRC to another path."
else
    say "  cloning into $DEST"
    mkdir -p "$(dirname -- "$DEST")"
    git clone "$REPO" "$DEST"
fi

say
exec "$DEST/install.sh" "$@"
