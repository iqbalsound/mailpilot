#!/usr/bin/env bash
# Wrap the PyInstaller binary (dist/mailpilot) into a .deb. Run AFTER: python scripts/build.py
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="$(python3 -c "import sys; sys.path.insert(0,'src'); from mailpilot.meta import APP_VERSION as v; print(v)")"
BIN="dist/mailpilot"
[ -f "$BIN" ] || { echo "dist/mailpilot not found. Run: python scripts/build.py"; exit 1; }
ARCH="$(dpkg --print-architecture)"
PKG="build/deb/mailpilot_${VERSION}_${ARCH}"

rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/512x512/apps" "$PKG/usr/share/doc/mailpilot" dist/release

install -m 0755 "$BIN"                         "$PKG/usr/bin/mailpilot"
install -m 0644 packaging/mailpilot.desktop    "$PKG/usr/share/applications/mailpilot.desktop"
install -m 0644 src/mailpilot/data/icon.png    "$PKG/usr/share/icons/hicolor/512x512/apps/mailpilot.png"
install -m 0644 LICENSE                        "$PKG/usr/share/doc/mailpilot/copyright"

SIZE_KB="$(du -sk "$PKG/usr" | cut -f1)"
cat > "$PKG/DEBIAN/control" <<CTRL
Package: mailpilot
Version: ${VERSION}
Section: mail
Priority: optional
Architecture: ${ARCH}
Maintainer: Iqbal Uddin Khan <iqbalsound@yahoo.com>
Installed-Size: ${SIZE_KB}
Homepage: https://github.com/iqbalsound/mailpilot
Description: A simple assignment email client with AI support
 Mailpilot reads and sends mail over IMAP, POP3 and SMTP, has light and
 dark themes, a rich-text editor with changeable text colour, and optional
 AI draft replies that you review before sending.
CTRL

dpkg-deb --build --root-owner-group "$PKG" "dist/release/mailpilot_${VERSION}_${ARCH}.deb"
echo "Built: dist/release/mailpilot_${VERSION}_${ARCH}.deb"
