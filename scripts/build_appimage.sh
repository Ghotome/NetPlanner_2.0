#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/release_helpers.sh"

if [ "${NETPLANNER_SKIP_BUILD:-0}" != "1" ]; then
  "$ROOT_DIR/scripts/build_linux_dist.sh"
fi

APPDIR="$ROOT_DIR/AppDir"
DIST_DIR="$ROOT_DIR/dist/NetPlanner_2.0"
rm -rf "$APPDIR"
mkdir -p \
  "$APPDIR/usr/bin" \
  "$APPDIR/usr/lib/netplanner/NetPlanner_2.0" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
  "$APPDIR/usr/share/icons/hicolor/96x96/apps"

cp -a "$DIST_DIR/." "$APPDIR/usr/lib/netplanner/NetPlanner_2.0/"
ln -sf ../lib/netplanner/NetPlanner_2.0/NetPlanner_2.0 "$APPDIR/usr/bin/NetPlanner_2.0"
cat > "$APPDIR/AppRun" <<'EOF'
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

exec "$APPDIR/usr/lib/netplanner/NetPlanner_2.0/NetPlanner_2.0" "$@"
EOF
chmod +x "$APPDIR/AppRun"

ICON_PNG_SRC="$ROOT_DIR/app/ui/icons/app_icons/app_icon_96_96.png"
ICON_PNG_256="$APPDIR/usr/share/icons/hicolor/256x256/apps/netplanner_2.0.png"
ICON_PNG_96="$APPDIR/usr/share/icons/hicolor/96x96/apps/netplanner_2.0.png"

ICON_SRC="$ICON_PNG_SRC" ICON_256="$ICON_PNG_256" python - <<'PY'
import os
from pathlib import Path

from PIL import Image

src = Path(os.environ["ICON_SRC"])
dst = Path(os.environ["ICON_256"])
with Image.open(src) as img:
    img.convert("RGBA").resize((256, 256)).save(dst)
PY

cp "$ICON_PNG_SRC" "$ICON_PNG_96"
cp "$ICON_PNG_256" "$APPDIR/.DirIcon"
cp "$ICON_PNG_256" "$APPDIR/netplanner_2.0.png"

cat > "$APPDIR/netplanner_2.0.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=NetPlanner_2.0
Comment=Network planning and simulation tool
Exec=NetPlanner_2.0
Icon=netplanner_2.0
Categories=Network;Utility;
Terminal=false
EOF
cp "$APPDIR/netplanner_2.0.desktop" "$APPDIR/usr/share/applications/netplanner_2.0.desktop"

ARCH="$(normalize_arch "${APPIMAGE_ARCH:-$(uname -m)}")"
APPIMAGETOOL_ARCH="$(normalize_arch "${APPIMAGETOOL_ARCH:-$ARCH}")"
VERSION="${VERSION:-$(project_version)}"
OUTPUT_PATH="$ROOT_DIR/$(asset_basename "$VERSION" appimage "$ARCH").AppImage"

APPIMAGETOOL=""
APPIMAGETOOL_SHA256=""
APPIMAGETOOL_CANDIDATES=("$ROOT_DIR/tools/appimagetool-${APPIMAGETOOL_ARCH}.AppImage")
if [ "$APPIMAGETOOL_ARCH" = "x86_64" ]; then
  APPIMAGETOOL_CANDIDATES+=("$ROOT_DIR/tools/appimagetool.AppImage")
fi

for candidate in "${APPIMAGETOOL_CANDIDATES[@]}"; do
  sha_candidate="${candidate}.sha256"
  if [ -f "$candidate" ] && [ -f "$sha_candidate" ]; then
    APPIMAGETOOL="$candidate"
    APPIMAGETOOL_SHA256="$sha_candidate"
    break
  fi
done

if [ -z "$APPIMAGETOOL" ] || [ -z "$APPIMAGETOOL_SHA256" ]; then
  echo "Missing vendored appimagetool for architecture: $APPIMAGETOOL_ARCH"
  echo "Expected one of:"
  echo "  $ROOT_DIR/tools/appimagetool-${APPIMAGETOOL_ARCH}.AppImage"
  if [ "$APPIMAGETOOL_ARCH" = "x86_64" ]; then
    echo "  $ROOT_DIR/tools/appimagetool.AppImage"
  fi
  echo "with a matching .sha256 file."
  exit 1
fi

sha256sum -c "$APPIMAGETOOL_SHA256"
chmod +x "$APPIMAGETOOL"

ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" "$APPDIR" "$OUTPUT_PATH"
echo "AppImage ready: $OUTPUT_PATH"
