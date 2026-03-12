#!/usr/bin/env bash

project_version() {
  python3 "$ROOT_DIR/scripts/get_project_version.py"
}

normalize_arch() {
  case "$1" in
    x86_64|amd64)
      echo "x86_64"
      ;;
    aarch64|arm64)
      echo "aarch64"
      ;;
    *)
      echo "$1"
      ;;
  esac
}

normalize_deb_arch() {
  case "$1" in
    x86_64|amd64)
      echo "amd64"
      ;;
    aarch64|arm64)
      echo "arm64"
      ;;
    *)
      echo "$1"
      ;;
  esac
}

asset_basename() {
  local version="$1"
  local type="$2"
  local arch="$3"
  echo "NetPlanner-${version}-${type}-${arch}"
}
