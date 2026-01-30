#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python -m pip install --upgrade pip
python -m pip install pyinstaller

pyinstaller -y pyinstaller.spec

APPDIR="$ROOT_DIR/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp "$ROOT_DIR/dist/NetPlanner" "$APPDIR/usr/bin/NetPlanner"
cp "$ROOT_DIR/app/icon.svg" "$APPDIR/usr/share/icons/hicolor/256x256/apps/netplanner.svg"

cat > "$APPDIR/usr/share/applications/netplanner.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=NetPlanner
Exec=NetPlanner
Icon=netplanner
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
