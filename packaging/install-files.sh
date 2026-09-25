#!/usr/bin/env bash
# Install console mode into a prefix, for the AUR package.
#
#   DESTDIR=/tmp/pkg PREFIX=/usr ./packaging/install-files.sh
#
# User installs still use ./install.sh, which copies into $HOME.
set -euo pipefail

SRC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${PREFIX:-/usr}"
DESTDIR="${DESTDIR:-}"
ROOT="$DESTDIR$PREFIX"

install_bin() {
    install -Dm755 "$SRC/bin/$1" "$ROOT/bin/$1"
}

for tool in cachy-console cachy-console-display cachy-console-watch \
            cachy-console-audio cachy-console-exit cachy-console-shortcut \
            cachy-console-app cachy-console-art cachy-console-settings \
            cachy-console-session cachy-console-pads; do
    install_bin "$tool"
done

cat > "$ROOT/bin/projector-exit" <<'EOF'
#!/usr/bin/env bash
exec "$(dirname -- "$(readlink -f -- "$0" || echo "$0")")/cachy-console-exit" "$@"
EOF
chmod 755 "$ROOT/bin/projector-exit"

for unit in cachy-console-watch cachy-console-audio; do
    install -Dm644 "$SRC/systemd/$unit.service" \
        "$DESTDIR/usr/lib/systemd/user/$unit.service"
    sed -i 's|%h/.local/bin|/usr/bin|g' \
        "$DESTDIR/usr/lib/systemd/user/$unit.service"
done

install -Dm644 "$SRC/share/applications/cachy-console.desktop" \
    "$DESTDIR/usr/share/applications/cachy-console.desktop"
install -Dm644 "$SRC/share/applications/cachy-console-settings.desktop" \
    "$DESTDIR/usr/share/applications/cachy-console-settings.desktop"
install -Dm644 "$SRC/share/autostart/cachy-console-session-env.desktop" \
    "$DESTDIR/etc/xdg/autostart/cachy-console-session-env.desktop"

install -Dm755 "$SRC/share/root/cachy-console-usb" \
    "$ROOT/lib/cachy-console/cachy-console-usb"
install -Dm644 "$SRC/share/root/org.cachyconsole.usb.policy" \
    "$DESTDIR/usr/share/polkit-1/actions/org.cachyconsole.usb.policy"
sed -i 's|/usr/local/libexec/cachy-console-usb|/usr/lib/cachy-console/cachy-console-usb|' \
    "$DESTDIR/usr/share/polkit-1/actions/org.cachyconsole.usb.policy"
install -Dm644 "$SRC/share/root/50-cachy-console-usb-system.rules" \
    "$DESTDIR/usr/share/polkit-1/rules.d/50-cachy-console-usb.rules"

install -Dm644 "$SRC/share/extest-init/cachy-extest-init.c" \
    "$ROOT/share/cachy-console/cachy-extest-init.c"
install -Dm644 "$SRC/LICENSE" "$DESTDIR/usr/share/licenses/cachy-console-git/LICENSE"

# Same $LIB layout install.sh uses, so Steam's 32-bit client and 64-bit
# children each pick the matching guard.
EXTEST_SRC="$SRC/share/extest-init/cachy-extest-init.c"
for arch in lib:-m64 lib32:-m32; do
    dir="$ROOT/lib/cachy-console/${arch%%:*}"
    mkdir -p "$dir"
    if cc "${arch#*:}" -O2 -shared -fPIC -o "$dir/libcachy-extest-init.so" \
            "$EXTEST_SRC" -ldl 2>/dev/null; then
        chmod 755 "$dir/libcachy-extest-init.so"
    else
        rm -f "$dir/libcachy-extest-init.so"
    fi
done
