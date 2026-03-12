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

write_linux_launcher "$PACKAGE_DIR/netplanner" '$BASE_DIR/NetPlanner_2.0/NetPlanner_2.0'

cat > "$PACKAGE_DIR/README.txt" <<'EOF'
NetPlanner portable Linux bundle

Run:
  ./netplanner

Renderer mode is detected automatically on first launch and saved for this machine.

If you want to force hardware rendering:
  NETPLANNER_HARDWARE_RENDERING=1 ./netplanner

If you want to force software rendering:
  NETPLANNER_SOFTWARE_RENDERING=1 ./netplanner
EOF

mkdir -p "$ARCHIVE_DIR"
tar -C "$STAGE_ROOT" -czf "$ARCHIVE_PATH" "$PACKAGE_NAME"
echo "Portable tarball ready: $ARCHIVE_PATH"
