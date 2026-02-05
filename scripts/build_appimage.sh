#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
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
ln -sf "usr/bin/NetPlanner_2.0" "$APPDIR/AppRun"

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

is_elf() {
  local file="$1"
  if [ ! -f "$file" ]; then
    return 1
  fi
  local magic
  magic="$(head -c 4 "$file" | od -An -t x1 | tr -d ' \n')"
  [ "$magic" = "7f454c46" ]
}

if ! command -v appimagetool >/dev/null 2>&1; then
  TOOL_DIR="$ROOT_DIR/tools"
  mkdir -p "$TOOL_DIR"
  APPIMAGE_TOOL="$TOOL_DIR/appimagetool.AppImage"
  if [ ! -f "$APPIMAGE_TOOL" ] || ! is_elf "$APPIMAGE_TOOL"; then
    echo "Downloading appimagetool..."
    rm -f "$APPIMAGE_TOOL"
    URLS=(
      "https://github.com/AppImage/AppImageKit/releases/latest/download/appimagetool-x86_64.AppImage"
      "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    )
    if command -v curl >/dev/null 2>&1; then
      for url in "${URLS[@]}"; do
        curl -L -o "$APPIMAGE_TOOL" "$url" && is_elf "$APPIMAGE_TOOL" && break
      done
    elif command -v wget >/dev/null 2>&1; then
      for url in "${URLS[@]}"; do
        wget -O "$APPIMAGE_TOOL" "$url" && is_elf "$APPIMAGE_TOOL" && break
      done
    else
      echo "Neither curl nor wget is available. Please install one of them."
      exit 1
    fi
    if ! is_elf "$APPIMAGE_TOOL"; then
      echo "Failed to download a valid appimagetool AppImage."
      echo "Please check network access or install appimagetool manually."
      exit 1
    fi
    chmod +x "$APPIMAGE_TOOL"
  fi
  export PATH="$TOOL_DIR:$PATH"
  ln -sf "$APPIMAGE_TOOL" "$TOOL_DIR/appimagetool"
fi

ARCH="$(uname -m)"
APPIMAGE_EXTRACT_AND_RUN=1 appimagetool "$APPDIR" "$ROOT_DIR/NetPlanner-${ARCH}.AppImage"
echo "AppImage ready: NetPlanner-${ARCH}.AppImage"
