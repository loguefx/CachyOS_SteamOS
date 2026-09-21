#!/usr/bin/env bash
# Remove cachy-console.
#
# Your config is left in place unless you ask for it to go, since reinstalling
# and having to choose the display again is a pointless annoyance.
#
#   ./uninstall.sh            remove the commands and services
#   ./uninstall.sh --purge    also remove the config file
set -euo pipefail

BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
UNIT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/systemd/user"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/cachy-console"

PURGE=0
[[ "${1-}" == --purge ]] && PURGE=1

say() { printf '%s\n' "$*"; }

say "== services =="
for unit in cachy-console-watch cachy-console-audio; do
    if [[ -e "$UNIT_DIR/$unit.service" ]]; then
        # Stopping the audio daemon properly matters: it unmutes anything it
        # muted on the way out.
        systemctl --user disable --now "$unit.service" 2>/dev/null || true
        rm -f "$UNIT_DIR/$unit.service"
        say "  removed $unit.service"
    fi
done
systemctl --user daemon-reload 2>/dev/null || true

say "== commands =="
for tool in cachy-console cachy-console-display cachy-console-watch \
            cachy-console-audio cachy-console-exit cachy-console-shortcut \
            cachy-console-app cachy-console-art cachy-console-settings \
            cachy-console-session; do
    if [[ -e "$BIN_DIR/$tool" ]]; then
        rm -f "$BIN_DIR/$tool"
        say "  removed $tool"
    fi
done
rm -f "$BIN_DIR/projector-exit"

rm -f "$APP_DIR/cachy-console.desktop" "$APP_DIR/cachy-console-settings.desktop"
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/cachy-console-session-env.desktop"

if (( PURGE )); then
    rm -rf "$CONFIG_DIR"
    say "  removed $CONFIG_DIR"
else
    say
    say "Config kept at $CONFIG_DIR (use --purge to remove it)."
fi

say
say "Two things this cannot undo for you:"
say "  - the \"Exit Console Mode\" entry in your Steam library."
say "    Remove it before uninstalling with: cachy-console shortcut --revert"
say "  - CAP_SYS_NICE on gamescope, if you granted it. To drop it:"
say "      sudo setcap -r \$(command -v gamescope)"
