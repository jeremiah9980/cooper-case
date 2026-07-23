"""Single poll + continuous poll loop."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from .browser import browser_context
from .config import Config
from .dashboard import build_dashboard
from .diff import diff_snapshots
from .publisher import publish_dashboard
from .report import report_changes
from .scrape import fetch_snapshot


def _load_latest(cfg: Config) -> dict | None:
    if cfg.latest_snapshot_file.exists():
        try:
            return json.loads(cfg.latest_snapshot_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _save_snapshot(cfg: Config, snapshot: dict) -> None:
    cfg.ensure_dirs()
    cfg.latest_snapshot_file.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (cfg.snapshots_dir / f"{stamp}.json").write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False)
    )


def poll_once(cfg: Config) -> list[dict]:
    """Fetch, diff, report, persist, refresh dashboard. Returns the changes."""
    url = cfg.resolved_case_detail_url()
    if not url:
        raise SystemExit(
            "No case_detail_url configured. Run `python -m galveston_scraper bootstrap` "
            "first (or set case_detail_url in config.json / GALV_CASE_DETAIL_URL)."
        )

    with browser_context(cfg, headless=True, use_saved_state=True) as (_p, _b, context):
        snapshot = fetch_snapshot(context, url, cfg.case_number)

    previous = _load_latest(cfg)
    changes = diff_snapshots(previous, snapshot)

    # Only advance the saved baseline when we successfully fetched a page.
    _save_snapshot(cfg, snapshot)
    report_changes(cfg, snapshot, changes)
    build_dashboard(cfg)
    publish_dashboard(cfg)
    return changes


def poll_loop(cfg: Config) -> None:
    """Poll forever on cfg.poll_interval_seconds, surviving transient errors."""
    interval = max(60, int(cfg.poll_interval_seconds))
    print(
        f"Polling {cfg.case_number} every {interval}s "
        f"(~{interval // 60} min). Ctrl-C to stop."
    )
    while True:
        start = time.monotonic()
        try:
            poll_once(cfg)
        except SystemExit:
            raise
        except Exception as exc:  # keep the loop alive on transient failures
            print(f"[{datetime.now(timezone.utc).isoformat()}] poll error: {exc}")
        elapsed = time.monotonic() - start
        time.sleep(max(1.0, interval - elapsed))
