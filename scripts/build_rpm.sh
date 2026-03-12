#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/release_helpers.sh"

if [ "${NETPLANNER_SKIP_BUILD:-0}" != "1" ]; then
  "$ROOT_DIR/scripts/build_linux_dist.sh"
fi

VERSION="${VERSION:-$(project_version)}"
RELEASE="${RELEASE:-1}"
ARCH="$(normalize_arch "${RPM_ARCH:-$(uname -m)}")"
PKG_NAME="netplanner"
DIST_DIR="$ROOT_DIR/dist/NetPlanner_2.0"
RPM_ROOT="$ROOT_DIR/build/rpm"
TOPDIR="$RPM_ROOT/rpmbuild"
STAGE_NAME="${PKG_NAME}-${VERSION}"
STAGE_DIR="$RPM_ROOT/stage/${STAGE_NAME}"
SOURCES_DIR="$TOPDIR/SOURCES"
SPECS_DIR="$TOPDIR/SPECS"
RPMS_DIR="$TOPDIR/RPMS"
SPEC_PATH="$SPECS_DIR/${PKG_NAME}.spec"
CHANGELOG_DATE="$(LC_ALL=C date '+%a %b %d %Y')"
OUTPUT_PATH="$RPM_ROOT/$(asset_basename "$VERSION" rpm "$ARCH").rpm"

rm -rf "$TOPDIR" "$RPM_ROOT/stage" "$OUTPUT_PATH"
mkdir -p \
  "$STAGE_DIR/usr/bin" \
  "$STAGE_DIR/usr/lib/netplanner/NetPlanner_2.0" \
  "$STAGE_DIR/usr/share/applications" \
  "$STAGE_DIR/usr/share/icons/hicolor/256x256/apps" \
  "$STAGE_DIR/usr/share/icons/hicolor/96x96/apps" \
  "$STAGE_DIR/usr/share/licenses/${PKG_NAME}" \
  "$SOURCES_DIR" \
  "$SPECS_DIR" \
  "$TOPDIR/BUILD" \
  "$TOPDIR/BUILDROOT" \
  "$RPMS_DIR" \
  "$TOPDIR/SRPMS"

cp -a "$DIST_DIR/." "$STAGE_DIR/usr/lib/netplanner/NetPlanner_2.0/"
chmod 0755 "$STAGE_DIR/usr/lib/netplanner/NetPlanner_2.0/NetPlanner_2.0"
cp "$ROOT_DIR/LICENSE" "$STAGE_DIR/usr/share/licenses/${PKG_NAME}/LICENSE"

write_linux_launcher "$STAGE_DIR/usr/bin/netplanner" '/usr/lib/netplanner/NetPlanner_2.0/NetPlanner_2.0'

ICON_SRC="$ROOT_DIR/app/ui/icons/app_icons/app_icon_96_96.png"
ICON_256="$STAGE_DIR/usr/share/icons/hicolor/256x256/apps/netplanner_2.0.png"
ICON_96="$STAGE_DIR/usr/share/icons/hicolor/96x96/apps/netplanner_2.0.png"

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

cat > "$STAGE_DIR/usr/share/applications/netplanner_2.0.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=NetPlanner
Comment=Network planning and simulation tool
Exec=netplanner
Icon=netplanner_2.0
Categories=Network;Utility;
Terminal=false
EOF

tar -C "$RPM_ROOT/stage" -czf "$SOURCES_DIR/${PKG_NAME}-${VERSION}.tar.gz" "$STAGE_NAME"

cat > "$SPEC_PATH" <<EOF
%global debug_package %{nil}

Name: ${PKG_NAME}
Version: ${VERSION}
Release: ${RELEASE}%{?dist}
Summary: NetPlanner network planning tool
License: MIT
URL: https://github.com/Ghotome/NetPlanner_2.0
BuildArch: ${ARCH}
Source0: %{name}-%{version}.tar.gz
AutoReqProv: no
Requires: bash

%description
NetPlanner is a desktop application for network planning and simulation.

%prep
%setup -q

%build

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}
cp -a usr %{buildroot}/

%files
%dir /usr/lib/netplanner
/usr/bin/netplanner
/usr/lib/netplanner/NetPlanner_2.0
/usr/share/applications/netplanner_2.0.desktop
/usr/share/icons/hicolor/96x96/apps/netplanner_2.0.png
/usr/share/icons/hicolor/256x256/apps/netplanner_2.0.png
%license /usr/share/licenses/netplanner/LICENSE

%changelog
* ${CHANGELOG_DATE} NetPlanner <support@example.com> - ${VERSION}-${RELEASE}
- Automated RPM build
EOF

rpmbuild --define "_topdir $TOPDIR" --target "$ARCH" -bb "$SPEC_PATH"
RPM_FILE="$(find "$RPMS_DIR" -type f -name '*.rpm' | head -n1)"
mv "$RPM_FILE" "$OUTPUT_PATH"
echo "RPM ready: $OUTPUT_PATH"
