#!/usr/bin/env bash
# Simplest scheduler: poll on a fixed interval in the foreground.
# Runs `watch`, which loops internally on poll_interval_seconds from config.
#
#   ./scheduler/run_loop.sh
#
# Stop with Ctrl-C. For a background service, prefer cron or systemd (see the
# other files in this directory).
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m galveston_scraper watch
