#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/release_helpers.sh"

if [ "${NETPLANNER_SKIP_BUILD:-0}" != "1" ]; then
  "$ROOT_DIR/scripts/build_linux_dist.sh"
fi

VERSION="${VERSION:-$(project_version)}"
PACKAGE_ARCH="$(normalize_deb_arch "${DEB_ARCH:-$(dpkg --print-architecture 2>/dev/null || uname -m)}")"
OUTPUT_ARCH="$(normalize_arch "$PACKAGE_ARCH")"
PKG_NAME="netplanner"
PKG_DIR="$ROOT_DIR/build/deb/${PKG_NAME}_${VERSION}_${PACKAGE_ARCH}"
DIST_DIR="$ROOT_DIR/dist/NetPlanner_2.0"
OUTPUT_PATH="$ROOT_DIR/build/deb/$(asset_basename "$VERSION" deb "$OUTPUT_ARCH").deb"

rm -rf "$PKG_DIR" "$OUTPUT_PATH"
mkdir -p \
  "$PKG_DIR/DEBIAN" \
  "$PKG_DIR/usr/bin" \
  "$PKG_DIR/usr/lib/netplanner/NetPlanner_2.0" \
  "$PKG_DIR/usr/share/applications" \
  "$PKG_DIR/usr/share/icons/hicolor/256x256/apps" \
  "$PKG_DIR/usr/share/icons/hicolor/96x96/apps"

cp -a "$DIST_DIR/." "$PKG_DIR/usr/lib/netplanner/NetPlanner_2.0/"
chmod 0755 "$PKG_DIR/usr/lib/netplanner/NetPlanner_2.0/NetPlanner_2.0"

cat > "$PKG_DIR/usr/bin/netplanner" <<'EOF'
#!/usr/bin/env bash
# Force X11/XCB only when explicitly requested at runtime.
if [ "${NETPLANNER_FORCE_XCB:-0}" = "1" ]; then
  export QT_QPA_PLATFORM=xcb
  export GDK_BACKEND=x11
fi

# Optional fallback for systems where Qt WebEngine cannot initialize GPU/GLX.
if [ "${NETPLANNER_SOFTWARE_RENDERING:-0}" = "1" ]; then
  export QT_OPENGL=software
  export LIBGL_ALWAYS_SOFTWARE=1
  FLAGS="${QTWEBENGINE_CHROMIUM_FLAGS:-}"
  EXTRA_FLAGS="--disable-gpu --disable-gpu-compositing"
  case " ${FLAGS} " in
    *" --disable-gpu "*) ;;
    *) FLAGS="${FLAGS:+$FLAGS }$EXTRA_FLAGS" ;;
  esac
  export QTWEBENGINE_CHROMIUM_FLAGS="$FLAGS"
fi

exec /usr/lib/netplanner/NetPlanner_2.0/NetPlanner_2.0 "$@"
EOF
chmod 0755 "$PKG_DIR/usr/bin/netplanner"

ICON_SRC="$ROOT_DIR/app/ui/icons/app_icons/app_icon_96_96.png"
ICON_256="$PKG_DIR/usr/share/icons/hicolor/256x256/apps/netplanner_2.0.png"
ICON_96="$PKG_DIR/usr/share/icons/hicolor/96x96/apps/netplanner_2.0.png"

ICON_SRC="$ICON_SRC" ICON_256="$ICON_256" python - <<'PY'
import os
from pathlib import Path

from PIL import Image

src = Path(os.environ["ICON_SRC"])
dst = Path(os.environ["ICON_256"])
with Image.open(src) as img:
    img.convert("RGBA").resize((256, 256)).save(dst)
PY
cp "$ICON_SRC" "$ICON_96"

cat > "$PKG_DIR/usr/share/applications/netplanner_2.0.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=NetPlanner
Comment=Network planning and simulation tool
Exec=netplanner
Icon=netplanner_2.0
Categories=Network;Utility;
Terminal=false
EOF

cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${PACKAGE_ARCH}
Maintainer: NetPlanner <support@example.com>
Description: NetPlanner network planning tool
EOF

dpkg-deb --build "$PKG_DIR" "$OUTPUT_PATH"
echo "DEB ready: $OUTPUT_PATH"
