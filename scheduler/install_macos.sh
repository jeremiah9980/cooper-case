#!/usr/bin/env bash
# One-command macOS scheduler (launchd) for the Galveston case monitor.
#
# Installs a per-user LaunchAgent that runs a single `poll` every N seconds
# (default from config.json, else 420s = 7 min). launchd fires on wake, so a
# laptop that was asleep simply polls when it comes back — no missed cron ticks
# piling up, no Terminal window to keep open.
#
#   ./scheduler/install_macos.sh          # install + start
#   ./scheduler/install_macos.sh remove   # stop + uninstall
#
# Logs: data/monitor.log   (stdout+stderr from each poll)
set -euo pipefail

LABEL="com.galveston.monitor"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# Repo dir = parent of this script's dir, resolved to an absolute path.
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

uninstall() {
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed $LABEL."
}

if [[ "${1:-}" == "remove" || "${1:-}" == "uninstall" ]]; then
  uninstall
  exit 0
fi

# Pick a python: prefer an active venv, then a sibling .venv, then PATH python3.
if [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
  PYTHON="$VIRTUAL_ENV/bin/python"
elif [[ -x "$REPO_DIR/.venv/bin/python" ]]; then
  PYTHON="$REPO_DIR/.venv/bin/python"
elif [[ -x "$(dirname "$REPO_DIR")/.venv/bin/python" ]]; then
  PYTHON="$(dirname "$REPO_DIR")/.venv/bin/python"
else
  PYTHON="$(command -v python3)"
fi

# Poll interval from config.json if present, else 420s.
INTERVAL="$("$PYTHON" - "$REPO_DIR" <<'PY'
import json, os, sys
repo = sys.argv[1]
p = os.path.join(repo, "config.json")
val = 420
try:
    val = int(json.load(open(p)).get("poll_interval_seconds", 420))
except Exception:
    pass
print(max(60, val))
PY
)"

mkdir -p "$HOME/Library/LaunchAgents" "$REPO_DIR/data"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>WorkingDirectory</key><string>$REPO_DIR</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>-m</string>
        <string>galveston_scraper</string>
        <string>poll</string>
    </array>
    <key>StartInterval</key><integer>$INTERVAL</integer>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>$REPO_DIR/data/monitor.log</string>
    <key>StandardErrorPath</key><string>$REPO_DIR/data/monitor.log</string>
</dict>
</plist>
PLIST

# (Re)load it.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "Installed $LABEL"
echo "  python:   $PYTHON"
echo "  repo:     $REPO_DIR"
echo "  interval: ${INTERVAL}s (~$((INTERVAL/60)) min)"
echo "  logs:     $REPO_DIR/data/monitor.log"
echo
echo "It runs immediately, then every ${INTERVAL}s while you are logged in."
echo "Stop it with:  ./scheduler/install_macos.sh remove"
