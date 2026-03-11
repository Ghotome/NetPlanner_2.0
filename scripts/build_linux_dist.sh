#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CONSTRAINTS_FILE="${BUILD_CONSTRAINTS:-constraints/build.txt}"
PIP_ARGS=()
if [ -f "$CONSTRAINTS_FILE" ]; then
  PIP_ARGS=(-c "$CONSTRAINTS_FILE")
fi

python -m pip install --upgrade pip
python -m pip install "${PIP_ARGS[@]}" ".[build,geo]"

pyinstaller -y pyinstaller-linux.spec

echo "Build ready: dist/NetPlanner_2.0/NetPlanner_2.0"
