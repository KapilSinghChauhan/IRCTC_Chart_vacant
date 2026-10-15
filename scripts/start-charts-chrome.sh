#!/usr/bin/env bash
#
# Start (or reuse) an attachable Chrome for in-page IRCTC chart reads.
# The process is a normal Chrome (not HeadlessChrome — IRCTC fetch fails
# that UA) on a private Xvfb display, so no window appears on the desktop.
# Never signs anyone in and never books.
#
#   ./scripts/start-charts-chrome.sh [--cdp http://127.0.0.1:9222]
#
set -uo pipefail

CDP_URL="${CHROME_CDP:-http://127.0.0.1:9222}"
PROFILE="${CHARTS_CHROME_PROFILE:-$HOME/.vacant-seat-finder-profile}"
LOG_DIR="${CHARTS_LOG_DIR:-/tmp/vacant-seat-finder}"
LOG="$LOG_DIR/launcher.log"
PARK_URL="https://www.irctc.co.in/online-charts/"
XVFB_DISPLAY="${CHARTS_XVFB_DISPLAY:-:99}"
XVFB_SCREEN="${CHARTS_XVFB_SCREEN:-1280x800x24}"
REPLACE_HEADED=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --cdp) CDP_URL="$2"; shift 2 ;;
    --cdp-port) CDP_URL="http://127.0.0.1:$2"; shift 2 ;;
    --binary) BROWSER_BIN="$2"; shift 2 ;;
    --replace-headed) REPLACE_HEADED=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) printf 'unknown argument %s\n' "$1" >&2; exit 2 ;;
  esac
done

CDP_PORT="$(printf '%s' "$CDP_URL" | sed -n 's/.*:\([0-9][0-9]*\)$/\1/p')"
CDP_PORT="${CDP_PORT:-9222}"
ENDPOINT="http://127.0.0.1:${CDP_PORT}"
XVFB_SOCKET="/tmp/.X11-unix/X${XVFB_DISPLAY#:}"

BROWSER_BIN="${BROWSER_BIN:-${CHARTS_CHROME:-}}"
if [ -z "$BROWSER_BIN" ]; then
  BROWSER_BIN="$(command -v google-chrome || command -v chromium || command -v brave-browser || true)"
fi
[ -x "$BROWSER_BIN" ] || BROWSER_BIN=/opt/google/chrome/chrome

mkdir -p "$LOG_DIR"
log() { printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$LOG"; }
note() { log "$*"; printf '%s\n' "$*"; }
up() { curl -sf --max-time 2 "$1" >/dev/null 2>&1; }

wait_for() {
  local url="$1" seconds="$2" i
  for ((i = 0; i < seconds * 2; i++)); do
    up "$url" && return 0
    sleep 0.5
  done
  return 1
}

detach() {
  local logfile="$1"; shift
  if setsid -f true >/dev/null 2>&1; then
    nohup setsid -f "$@" >>"$logfile" 2>&1 </dev/null
  else
    nohup "$@" >>"$logfile" 2>&1 </dev/null &
    disown 2>/dev/null || true
  fi
}

main_chrome_pid() {
  ps -eo pid=,args= | awk -v port="--remote-debugging-port=${CDP_PORT}" '
    index($0, port) && $0 !~ /--type=/ { print $1; exit }
  '
}

chrome_display() {
  local pid="$1" child display
  [ -n "$pid" ] || return 0
  for child in "$pid" $(pgrep -P "$pid" 2>/dev/null); do
    display="$(tr '\0' '\n' <"/proc/$child/environ" 2>/dev/null | sed -n 's/^DISPLAY=//p' | head -n 1)"
    if [ -n "$display" ]; then
      printf '%s\n' "$display"
      return 0
    fi
  done
}

is_hidden_charts_chrome() {
  local pid cmd display
  pid="$(main_chrome_pid)"
  [ -n "$pid" ] || return 1
  cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  printf '%s' "$cmd" | grep -q -- '--headless' && return 1
  display="$(chrome_display "$pid")"
  [ "$display" = "$XVFB_DISPLAY" ] || [ "$display" = "${XVFB_DISPLAY}.0" ]
}

ensure_xvfb() {
  if [ -S "$XVFB_SOCKET" ]; then
    return 0
  fi
  if ! command -v Xvfb >/dev/null 2>&1; then
    note "Xvfb is not installed; cannot hide Chrome off the desktop"
    return 1
  fi
  note "starting Xvfb on $XVFB_DISPLAY"
  detach "$LOG_DIR/xvfb.log" Xvfb "$XVFB_DISPLAY" -screen 0 "$XVFB_SCREEN" -nolisten tcp -ac
  local i
  for ((i = 0; i < 40; i++)); do
    [ -S "$XVFB_SOCKET" ] && return 0
    sleep 0.1
  done
  note "Xvfb did not open $XVFB_SOCKET"
  return 1
}

stop_port_chrome() {
  local pids
  pids="$(ps -eo pid=,args= | awk -v port="--remote-debugging-port=${CDP_PORT}" 'index($0, port) {print $1}')"
  if [ -z "$pids" ]; then
    return 0
  fi
  note "stopping Chrome on $CDP_PORT so a hidden Xvfb Chrome can take the port"
  # shellcheck disable=SC2086
  kill $pids >/dev/null 2>&1 || true
  sleep 0.8
  # shellcheck disable=SC2086
  kill -9 $pids >/dev/null 2>&1 || true
  sleep 0.4
}

if up "$ENDPOINT/json/version"; then
  if is_hidden_charts_chrome; then
    note "hidden charts Chrome is already up on $CDP_PORT ($XVFB_DISPLAY)"
    exit 0
  fi
  if [ "$REPLACE_HEADED" != 1 ]; then
    note "Chrome on $CDP_PORT is visible or HeadlessChrome; pass --replace-headed to hide it on Xvfb"
    exit 2
  fi
  stop_port_chrome
fi

if [ ! -x "$BROWSER_BIN" ]; then
  note "the browser to start is not executable: $BROWSER_BIN"
  exit 1
fi

if ! ensure_xvfb; then
  exit 1
fi

note "starting hidden $(basename "$BROWSER_BIN") on $XVFB_DISPLAY with charts profile on $CDP_PORT"
export DISPLAY="$XVFB_DISPLAY"
detach "$LOG_DIR/chrome.log" env DISPLAY="$XVFB_DISPLAY" "$BROWSER_BIN" \
  --disable-gpu \
  --no-sandbox \
  --disable-dev-shm-usage \
  --hide-scrollbars \
  --mute-audio \
  --noerrdialogs \
  --window-size=1280,800 \
  --window-position=0,0 \
  --user-data-dir="$PROFILE" \
  --remote-debugging-port="$CDP_PORT" \
  --no-first-run --no-default-browser-check \
  --remote-allow-origins=* \
  "$PARK_URL"

if wait_for "$ENDPOINT/json/version" 30; then
  if is_hidden_charts_chrome; then
    note "hidden charts Chrome answered on $CDP_PORT ($XVFB_DISPLAY)"
    exit 0
  fi
  note "Chrome answered on $CDP_PORT but is still on a visible display"
  exit 1
fi
note "hidden Chrome on $CDP_PORT is not up"
exit 1
