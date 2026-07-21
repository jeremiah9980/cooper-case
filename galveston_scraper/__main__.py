"""Command-line entry point.

Usage:
    python -m galveston_scraper bootstrap [--case-url URL]
    python -m galveston_scraper poll            # one poll
    python -m galveston_scraper watch           # continuous loop
    python -m galveston_scraper dashboard       # rebuild dashboard.html
    python -m galveston_scraper status          # print current state
"""

from __future__ import annotations

import argparse
import json
import sys

from .bootstrap import bootstrap_from_url, bootstrap_interactive
from .config import load_config
from .dashboard import build_dashboard
from .poll import poll_loop, poll_once


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="galveston_scraper", description=__doc__)
    parser.add_argument("--config", default=None, help="Path to config.json")
    sub = parser.add_subparsers(dest="command", required=True)

    p_boot = sub.add_parser("bootstrap", help="One-time captcha solve / capture case URL")
    p_boot.add_argument(
        "--case-url",
        default=None,
        help="Paste the case-detail URL directly instead of opening a browser",
    )
    p_boot.add_argument(
        "--timeout", type=int, default=600, help="Interactive bootstrap timeout (seconds)"
    )

    sub.add_parser("poll", help="Fetch once, diff, report, refresh dashboard")
    sub.add_parser("watch", help="Poll continuously on the configured interval")
    sub.add_parser("dashboard", help="Rebuild dashboard.html from saved data")
    sub.add_parser("status", help="Show current configuration / state")

    args = parser.parse_args(argv)
    cfg = load_config(args.config)

    if args.command == "bootstrap":
        if args.case_url:
            bootstrap_from_url(cfg, args.case_url)
        else:
            bootstrap_interactive(cfg, timeout_seconds=args.timeout)
        return 0

    if args.command == "poll":
        poll_once(cfg)
        return 0

    if args.command == "watch":
        try:
            poll_loop(cfg)
        except KeyboardInterrupt:
            print("\nStopped.")
        return 0

    if args.command == "dashboard":
        path = build_dashboard(cfg)
        print(f"Wrote {path}")
        return 0

    if args.command == "status":
        url = cfg.resolved_case_detail_url()
        print(
            json.dumps(
                {
                    "case_number": cfg.case_number,
                    "case_detail_url": url or "(not bootstrapped)",
                    "data_dir": str(cfg.data_path),
                    "poll_interval_seconds": cfg.poll_interval_seconds,
                    "has_session": cfg.state_file.exists(),
                    "has_snapshot": cfg.latest_snapshot_file.exists(),
                    "slack_webhook_set": bool(cfg.notify.webhook_url),
                },
                indent=2,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
