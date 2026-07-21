"""Report detected changes: console output, changelog, optional webhook."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .config import Config


def _console(cfg: Config, header: str, changes: list[dict[str, Any]]) -> None:
    if not cfg.notify.console:
        return
    print(header)
    for c in changes:
        print(f"  [{c['type']}] {c['section']}: {c['detail']}")


def append_changelog(cfg: Config, entry: dict[str, Any]) -> None:
    cfg.ensure_dirs()
    with cfg.changelog_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _webhook_payload(fmt: str, title: str, lines: list[str]) -> dict[str, Any]:
    body = title + "\n" + "\n".join(f"- {ln}" for ln in lines)
    if fmt == "slack":
        return {"text": body}
    if fmt == "discord":
        return {"content": body[:1900]}
    return {"title": title, "changes": lines}


def _post_webhook(cfg: Config, title: str, changes: list[dict[str, Any]]) -> None:
    url = cfg.notify.webhook_url
    if not url:
        return
    lines = [f"{c['section']}: {c['detail']}" for c in changes]
    payload = _webhook_payload(cfg.notify.webhook_format, title, lines)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except (urllib.error.URLError, TimeoutError) as exc:  # pragma: no cover
        print(f"  ! webhook delivery failed: {exc}")


def report_changes(cfg: Config, snapshot: dict[str, Any], changes: list[dict[str, Any]]) -> None:
    """Emit changes to all configured channels and persist them."""
    ts = datetime.now(timezone.utc).isoformat()
    case = snapshot.get("case_number", "")

    if not changes:
        if cfg.notify.console:
            print(f"[{ts}] {case}: no changes.")
        return

    title = f"[{ts}] {case}: {len(changes)} change(s) detected"
    _console(cfg, title, changes)

    entry = {
        "timestamp": ts,
        "case_number": case,
        "url": snapshot.get("url", ""),
        "changes": changes,
    }
    append_changelog(cfg, entry)

    # Never let notification failure crash the poll loop.
    is_baseline = len(changes) == 1 and changes[0].get("type") == "baseline"
    if not is_baseline:
        _post_webhook(cfg, title, changes)
