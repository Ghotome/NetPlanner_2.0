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

write_linux_launcher() {
  local target="$1"
  local binary_expr="$2"
cat > "$target" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPDIR="${APPDIR:-$BASE_DIR}"
NETPLANNER_BINARY="__NETPLANNER_BINARY__"

netplanner_state_root() {
  if [ -n "${NETPLANNER_CONFIG_DIR:-}" ]; then
    printf '%s\n' "$NETPLANNER_CONFIG_DIR"
  elif [ -n "${XDG_CONFIG_HOME:-}" ]; then
    printf '%s\n' "$XDG_CONFIG_HOME/NetPlanner"
  else
    printf '%s\n' "$HOME/.config/NetPlanner"
  fi
}

netplanner_cache_root() {
  if [ -n "${NETPLANNER_CACHE_DIR:-}" ]; then
    printf '%s\n' "$NETPLANNER_CACHE_DIR"
  elif [ -n "${XDG_CACHE_HOME:-}" ]; then
    printf '%s\n' "$XDG_CACHE_HOME/NetPlanner"
  else
    printf '%s\n' "$HOME/.cache/NetPlanner"
  fi
}

STATE_DIR="$(netplanner_state_root)"
CACHE_DIR="$(netplanner_cache_root)"
STATE_FILE="$STATE_DIR/renderer_mode"
RENDERER_LOG_DIR="$CACHE_DIR/launcher"
mkdir -p "$STATE_DIR" "$CACHE_DIR" "$RENDERER_LOG_DIR"
export NETPLANNER_CACHE_DIR="$CACHE_DIR"

if [ "${NETPLANNER_DISABLE_AUTO_RENDERER:-0}" = "1" ] \
  || [ -n "${NETPLANNER_HARDWARE_RENDERING:-}" ] \
  || [ -n "${NETPLANNER_SOFTWARE_RENDERING:-}" ] \
  || [ -n "${NETPLANNER_RENDERER_MODE:-}" ] \
  || [ -n "${QT_XCB_GL_INTEGRATION:-}" ]; then
  exec "$NETPLANNER_BINARY" "$@"
fi

add_renderer_mode() {
  local mode="$1"
  local existing
  for existing in "${RENDERER_MODES[@]}"; do
    if [ "$existing" = "$mode" ]; then
      return
    fi
  done
  RENDERER_MODES+=("$mode")
}

clear_renderer_env() {
  unset NETPLANNER_SOFTWARE_RENDERING
  unset NETPLANNER_HARDWARE_RENDERING
  unset NETPLANNER_RENDERER_MODE
  unset QT_OPENGL
  unset LIBGL_ALWAYS_SOFTWARE
  unset QT_QUICK_BACKEND
  unset QT_XCB_GL_INTEGRATION
}

apply_renderer_mode() {
  local mode="$1"
  clear_renderer_env
  export NETPLANNER_RENDERER_MODE="$mode"
  case "$mode" in
    hardware)
      export NETPLANNER_HARDWARE_RENDERING=1
      ;;
    xcb_egl)
      export NETPLANNER_HARDWARE_RENDERING=1
      export QT_XCB_GL_INTEGRATION=xcb_egl
      ;;
    software)
      export NETPLANNER_SOFTWARE_RENDERING=1
      ;;
    *)
      return 1
      ;;
  esac
}

persist_renderer_mode() {
  printf '%s\n' "$1" > "$STATE_FILE"
}

run_renderer_mode() {
  local mode="$1"
  shift
  local marker log_path status ready
  marker="$(mktemp "${TMPDIR:-/tmp}/netplanner-startup.XXXXXX")"
  rm -f "$marker"
  log_path="$RENDERER_LOG_DIR/renderer-${mode}.log"
  : > "$log_path"
  export NETPLANNER_STARTUP_MARKER="$marker"
  apply_renderer_mode "$mode"
  set +e
  if [ "${NETPLANNER_DEBUG_RENDERER:-0}" = "1" ]; then
    "$NETPLANNER_BINARY" "$@"
  else
    "$NETPLANNER_BINARY" "$@" 2>"$log_path"
  fi
  status=$?
  set -e
  ready=0
  if [ -f "$marker" ]; then
    ready=1
  fi
  rm -f "$marker"
  unset NETPLANNER_STARTUP_MARKER
  LAST_RENDERER_STATUS=$status
  LAST_RENDERER_READY=$ready
  LAST_RENDERER_LOG="$log_path"
}

saved_mode=""
if [ -f "$STATE_FILE" ]; then
  IFS= read -r saved_mode < "$STATE_FILE" || true
fi

RENDERER_MODES=()
case "$saved_mode" in
  hardware|xcb_egl|software)
    add_renderer_mode "$saved_mode"
    ;;
esac
add_renderer_mode hardware
add_renderer_mode xcb_egl
add_renderer_mode software

for mode in "${RENDERER_MODES[@]}"; do
  run_renderer_mode "$mode" "$@"
  if [ "$LAST_RENDERER_READY" = "1" ] || [ "$LAST_RENDERER_STATUS" = "0" ]; then
    persist_renderer_mode "$mode"
    exit "$LAST_RENDERER_STATUS"
  fi
done

if [ -n "${LAST_RENDERER_LOG:-}" ] && [ -f "$LAST_RENDERER_LOG" ]; then
  cat "$LAST_RENDERER_LOG" >&2
fi
printf '%s\n' "NetPlanner failed to start with hardware, xcb_egl, and software rendering." >&2
exit "${LAST_RENDERER_STATUS:-1}"
EOF
  sed -i "s|__NETPLANNER_BINARY__|$binary_expr|" "$target"
  chmod +x "$target"
}
