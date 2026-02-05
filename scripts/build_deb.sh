#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

pyinstaller -y pyinstaller.spec

VERSION="${VERSION:-2.0.0}"
ARCH="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
PKG_NAME="netplanner"
PKG_DIR="$ROOT_DIR/build/deb/${PKG_NAME}_${VERSION}_${ARCH}"

rm -rf "$PKG_DIR"
mkdir -p \
  "$PKG_DIR/DEBIAN" \
  "$PKG_DIR/usr/bin" \
  "$PKG_DIR/usr/share/applications" \
  "$PKG_DIR/usr/share/icons/hicolor/256x256/apps" \
  "$PKG_DIR/usr/share/icons/hicolor/96x96/apps"

cp "$ROOT_DIR/dist/NetPlanner_2.0" "$PKG_DIR/usr/bin/NetPlanner_2.0"
chmod 0755 "$PKG_DIR/usr/bin/NetPlanner_2.0"

ICON_SRC="$ROOT_DIR/app/ui/icons/app_icons/app_icon_96_96.png"
ICON_256="$PKG_DIR/usr/share/icons/hicolor/256x256/apps/netplanner_2.0.png"
ICON_96="$PKG_DIR/usr/share/icons/hicolor/96x96/apps/netplanner_2.0.png"

if command -v convert >/dev/null 2>&1; then
  convert -background none -resize 256x256 "$ICON_SRC" "$ICON_256"
else
  cp "$ICON_SRC" "$ICON_256"
fi
cp "$ICON_SRC" "$ICON_96"

cat > "$PKG_DIR/usr/share/applications/netplanner_2.0.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=NetPlanner
Comment=Network planning and simulation tool
Exec=NetPlanner_2.0
Icon=netplanner_2.0
Categories=Network;Utility;
Terminal=false
EOF

cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: NetPlanner <support@example.com>
Description: NetPlanner network planning tool
EOF

dpkg-deb --build "$PKG_DIR"
echo "DEB ready: ${PKG_DIR}.deb"
