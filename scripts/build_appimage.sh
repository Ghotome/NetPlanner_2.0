#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python -m pip install --upgrade pip
python -m pip install pyinstaller

pyinstaller -y pyinstaller.spec

APPDIR="$ROOT_DIR/AppDir"
rm -rf "$APPDIR"
mkdir -p \
  "$APPDIR/usr/bin" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
  "$APPDIR/usr/share/icons/hicolor/96x96/apps"

cp "$ROOT_DIR/dist/NetPlanner_2.0" "$APPDIR/usr/bin/NetPlanner_2.0"

ICON_PNG_SRC="$ROOT_DIR/app/ui/icons/app_icons/app_icon_96_96.png"
ICON_PNG_256="$APPDIR/usr/share/icons/hicolor/256x256/apps/netplanner_2.0.png"
ICON_PNG_96="$APPDIR/usr/share/icons/hicolor/96x96/apps/netplanner_2.0.png"

if command -v convert >/dev/null 2>&1; then
  convert -background none -resize 256x256 "$ICON_PNG_SRC" "$ICON_PNG_256"
else
  cp "$ICON_PNG_SRC" "$ICON_PNG_256"
fi

cp "$ICON_PNG_SRC" "$ICON_PNG_96"
cp "$ICON_PNG_256" "$APPDIR/.DirIcon"

cat > "$APPDIR/usr/share/applications/netplanner_2.0.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=NetPlanner_2.0
Comment=Network planning and simulation tool
Exec=NetPlanner_2.0
Icon=netplanner_2.0
Categories=Network;Utility;
Terminal=false
EOF

if ! command -v appimagetool >/dev/null 2>&1; then
  TOOL_DIR="$ROOT_DIR/tools"
  mkdir -p "$TOOL_DIR"
  APPIMAGE_TOOL="$TOOL_DIR/appimagetool.AppImage"
  if [ ! -f "$APPIMAGE_TOOL" ]; then
    echo "Downloading appimagetool..."
    if command -v curl >/dev/null 2>&1; then
      curl -L -o "$APPIMAGE_TOOL" "https://github.com/AppImage/AppImageKit/releases/latest/download/appimagetool-x86_64.AppImage"
    elif command -v wget >/dev/null 2>&1; then
      wget -O "$APPIMAGE_TOOL" "https://github.com/AppImage/AppImageKit/releases/latest/download/appimagetool-x86_64.AppImage"
    else
      echo "Neither curl nor wget is available. Please install one of them."
      exit 1
    fi
    chmod +x "$APPIMAGE_TOOL"
  fi
  export PATH="$TOOL_DIR:$PATH"
  ln -sf "$APPIMAGE_TOOL" "$TOOL_DIR/appimagetool"
fi

ARCH="$(uname -m)"
appimagetool "$APPDIR" "$ROOT_DIR/NetPlanner-${ARCH}.AppImage"
echo "AppImage ready: NetPlanner-${ARCH}.AppImage"
