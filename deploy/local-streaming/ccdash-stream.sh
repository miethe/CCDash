#!/usr/bin/env bash
# ccdash-stream.sh — management CLI for the local CCDash streaming worker.
#
# Installs/controls two macOS LaunchAgents:
#   com.ccdash.stream-worker     persistent worker-watch process (KeepAlive)
#   com.ccdash.register-projects periodic project auto-registration (every 6h)
#
# Secrets live in ~/.ccdash/stream.env (sourced by the wrappers), never in the
# plists. Idempotent and safe to re-run.
set -euo pipefail

# --- Resolve paths ---------------------------------------------------------
# Source dir = the deploy/local-streaming dir this script ships in.
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CCDASH_HOME="$HOME/.ccdash"
BIN_DIR="$CCDASH_HOME/bin"
LOG_DIR="$CCDASH_HOME/logs"
ENV_FILE="$CCDASH_HOME/stream.env"
ENV_EXAMPLE="$SRC_DIR/stream.env.example"
LA_DIR="$HOME/Library/LaunchAgents"

WORKER_LABEL="com.ccdash.stream-worker"
REGISTER_LABEL="com.ccdash.register-projects"
WORKER_PLIST="$LA_DIR/$WORKER_LABEL.plist"
REGISTER_PLIST="$LA_DIR/$REGISTER_LABEL.plist"

GUI_DOMAIN="gui/$(id -u)"

# Load env (if present) so CCDASH_API etc. are available to status/register.
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi
API_BASE="${CCDASH_API:-http://10.42.10.76:8090}"

usage() {
  cat <<'EOF'
ccdash-stream.sh — manage the local CCDash streaming worker (macOS launchd)

Usage: ccdash-stream.sh <command>

Commands:
  install     Create ~/.ccdash dirs, copy wrappers, render & load both agents.
              On first run (no stream.env) it seeds the example and stops so
              you can fill in credentials before loading.
  uninstall   Bootout & remove both agents (keeps stream.env and logs).
  start       Start the stream-worker agent.
  stop        Stop the stream-worker agent.
  restart     Restart the stream-worker agent (use after a git pull).
  status      Show worker launchd state + a node health/counts check.
  register    Run project auto-registration once now.
  logs        Tail the stream-worker out+err logs (follow).

Files:
  ~/.ccdash/stream.env        credentials + config (gitignored, not committed)
  ~/.ccdash/bin/              installed wrappers
  ~/.ccdash/logs/             agent stdout/stderr
EOF
}

die() { echo "ccdash-stream: $*" >&2; exit 1; }

# launchctl bootstrap with a load -w fallback for older macOS.
_load_agent() {
  local plist="$1"
  if launchctl bootstrap "$GUI_DOMAIN" "$plist" 2>/dev/null; then
    return 0
  fi
  # Already loaded, or older launchctl — fall back to load -w.
  launchctl load -w "$plist" 2>/dev/null || true
}

_boot_out_agent() {
  local plist="$1" label="$2"
  launchctl bootout "$GUI_DOMAIN/$label" 2>/dev/null \
    || launchctl bootout "$GUI_DOMAIN" "$plist" 2>/dev/null \
    || launchctl unload -w "$plist" 2>/dev/null \
    || true
}

# Render a plist template into LaunchAgents with __TOKENS__ substituted.
_render_plist() {
  local src="$1" dest="$2"
  sed -e "s#__INSTALL_BIN__#$BIN_DIR#g" \
      -e "s#__HOME__#$HOME#g" \
      "$src" > "$dest"
}

cmd_install() {
  mkdir -p "$BIN_DIR" "$LOG_DIR" "$LA_DIR"

  # Seed env file on first run, then stop so the operator can fill it in.
  if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "Seeded $ENV_FILE from the example."
    echo
    echo "NEXT: edit $ENV_FILE — set CCDASH_REPO, the DB password in"
    echo "CCDASH_DATABASE_URL, and confirm CCDASH_WORKER_PROJECT_ID."
    echo "Then re-run: ccdash-stream.sh install"
    return 0
  fi

  # Copy wrappers and make them executable (Write can't chmod; do it here).
  cp "$SRC_DIR/bin/ccdash-stream-worker.sh" "$BIN_DIR/ccdash-stream-worker.sh"
  cp "$SRC_DIR/bin/ccdash-register.sh"      "$BIN_DIR/ccdash-register.sh"
  chmod +x "$BIN_DIR/ccdash-stream-worker.sh" "$BIN_DIR/ccdash-register.sh"

  # Render plists into ~/Library/LaunchAgents.
  _render_plist "$SRC_DIR/$WORKER_LABEL.plist"   "$WORKER_PLIST"
  _render_plist "$SRC_DIR/$REGISTER_LABEL.plist" "$REGISTER_PLIST"

  # Reload cleanly: bootout any prior instance, then bootstrap.
  _boot_out_agent "$WORKER_PLIST"   "$WORKER_LABEL"
  _boot_out_agent "$REGISTER_PLIST" "$REGISTER_LABEL"
  _load_agent "$WORKER_PLIST"
  _load_agent "$REGISTER_PLIST"

  echo "Installed and loaded:"
  echo "  $WORKER_LABEL    (persistent worker-watch)"
  echo "  $REGISTER_LABEL  (auto-register every 6h)"
  echo
  echo "Check status: ccdash-stream.sh status"
  echo "Tail logs:    ccdash-stream.sh logs"
}

cmd_uninstall() {
  _boot_out_agent "$WORKER_PLIST"   "$WORKER_LABEL"
  _boot_out_agent "$REGISTER_PLIST" "$REGISTER_LABEL"
  rm -f "$WORKER_PLIST" "$REGISTER_PLIST"
  echo "Removed both LaunchAgents. Kept $ENV_FILE and $LOG_DIR."
}

cmd_start() {
  [[ -f "$WORKER_PLIST" ]] || die "not installed — run: ccdash-stream.sh install"
  launchctl kickstart -k "$GUI_DOMAIN/$WORKER_LABEL" 2>/dev/null \
    || _load_agent "$WORKER_PLIST"
  echo "Started $WORKER_LABEL."
}

cmd_stop() {
  _boot_out_agent "$WORKER_PLIST" "$WORKER_LABEL"
  echo "Stopped $WORKER_LABEL."
}

cmd_restart() {
  [[ -f "$WORKER_PLIST" ]] || die "not installed — run: ccdash-stream.sh install"
  launchctl kickstart -k "$GUI_DOMAIN/$WORKER_LABEL" 2>/dev/null && {
    echo "Restarted $WORKER_LABEL."
    return 0
  }
  _boot_out_agent "$WORKER_PLIST" "$WORKER_LABEL"
  _load_agent "$WORKER_PLIST"
  echo "Restarted $WORKER_LABEL."
}

cmd_status() {
  echo "== launchd: $WORKER_LABEL =="
  if launchctl print "$GUI_DOMAIN/$WORKER_LABEL" 2>/dev/null \
      | grep -E '^[[:space:]]*(state|pid|last exit code|program) =' ; then
    :
  else
    echo "  (not loaded — run: ccdash-stream.sh install)"
  fi

  echo
  echo "== node: $API_BASE =="
  if curl -fsS --max-time 5 "$API_BASE/api/health/ready" >/dev/null 2>&1; then
    echo "  health/ready: OK"
  else
    echo "  health/ready: UNREACHABLE (node down or wrong CCDASH_API?)"
  fi

  # Project count via the projects API; resilient to node being down.
  local projects_json
  if projects_json="$(curl -fsS --max-time 5 "$API_BASE/api/projects" 2>/dev/null)"; then
    local count
    count="$(printf '%s' "$projects_json" | python3 -c \
      'import json,sys; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else "?")' \
      2>/dev/null || echo "?")"
    echo "  registered projects: $count"
  else
    echo "  registered projects: (unavailable)"
  fi
}

cmd_register() {
  [[ -x "$BIN_DIR/ccdash-register.sh" ]] \
    || die "register wrapper not installed — run: ccdash-stream.sh install"
  CCDASH_STREAM_ENV="$ENV_FILE" "$BIN_DIR/ccdash-register.sh"
}

cmd_logs() {
  local out="$LOG_DIR/stream-worker.out.log"
  local err="$LOG_DIR/stream-worker.err.log"
  touch "$out" "$err"
  echo "Tailing $err and $out (Ctrl-C to stop)…"
  tail -n 50 -f "$err" "$out"
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    install)   cmd_install ;;
    uninstall) cmd_uninstall ;;
    start)     cmd_start ;;
    stop)      cmd_stop ;;
    restart)   cmd_restart ;;
    status)    cmd_status ;;
    register)  cmd_register ;;
    logs)      cmd_logs ;;
    -h|--help|help|"") usage ;;
    *) usage; die "unknown command: $cmd" ;;
  esac
}

main "$@"
