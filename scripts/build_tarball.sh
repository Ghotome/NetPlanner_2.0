#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/release_helpers.sh"

if [ "${NETPLANNER_SKIP_BUILD:-0}" != "1" ]; then
  "$ROOT_DIR/scripts/build_linux_dist.sh"
fi

ARCH="$(normalize_arch "${PORTABLE_ARCH:-${APPIMAGE_ARCH:-$(uname -m)}}")"
VERSION="${VERSION:-$(project_version)}"
DIST_DIR="$ROOT_DIR/dist/NetPlanner_2.0"
STAGE_ROOT="$ROOT_DIR/build/tar/stage-${ARCH}"
PACKAGE_NAME="$(asset_basename "$VERSION" portable "$ARCH")"
PACKAGE_DIR="$STAGE_ROOT/$PACKAGE_NAME"
ARCHIVE_DIR="$ROOT_DIR/build/tar"
ARCHIVE_PATH="$ARCHIVE_DIR/${PACKAGE_NAME}.tar.gz"

rm -rf "$STAGE_ROOT"
mkdir -p "$PACKAGE_DIR"
cp -a "$DIST_DIR" "$PACKAGE_DIR/"

cat > "$PACKAGE_DIR/netplanner" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

exec "$BASE_DIR/NetPlanner_2.0/NetPlanner_2.0" "$@"
EOF
chmod +x "$PACKAGE_DIR/netplanner"

cat > "$PACKAGE_DIR/README.txt" <<'EOF'
NetPlanner portable Linux bundle

Run:
  ./netplanner

Packaged Linux builds use software rendering by default for compatibility.

If your system has working GPU/GLX support and you want to force hardware rendering:
  NETPLANNER_HARDWARE_RENDERING=1 ./netplanner
EOF

mkdir -p "$ARCHIVE_DIR"
tar -C "$STAGE_ROOT" -czf "$ARCHIVE_PATH" "$PACKAGE_NAME"
echo "Portable tarball ready: $ARCHIVE_PATH"
