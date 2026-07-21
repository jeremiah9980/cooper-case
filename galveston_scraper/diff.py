"""Compare two case snapshots and describe what changed."""

from __future__ import annotations

from typing import Any


def _table_key(table: dict) -> str:
    """A stable identity for a table across snapshots."""
    cap = (table.get("caption") or "").strip().lower()
    if cap:
        return cap
    headers = " | ".join(table.get("headers") or []).strip().lower()
    return headers or "table"


def _row_signature(row: list[str]) -> str:
    return " | ".join(c.strip() for c in row)


def diff_snapshots(old: dict[str, Any] | None, new: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of change records describing new vs old.

    Each change record: {type, section, detail}. An empty list means nothing
    changed. A None `old` (first ever run) yields a single "baseline" record.
    """
    if old is None:
        return [
            {
                "type": "baseline",
                "section": "case",
                "detail": f"Started monitoring {new.get('case_number', '')} "
                f"({new.get('caption', '')})".strip(),
            }
        ]

    changes: list[dict[str, Any]] = []

    # --- header field changes ---------------------------------------------
    old_h = old.get("header", {}) or {}
    new_h = new.get("header", {}) or {}
    for key, val in new_h.items():
        if key not in old_h:
            changes.append({"type": "field_added", "section": key, "detail": f"{key}: {val}"})
        elif old_h[key] != val:
            changes.append(
                {
                    "type": "field_changed",
                    "section": key,
                    "detail": f"{key}: '{old_h[key]}' -> '{val}'",
                }
            )
    for key in old_h:
        if key not in new_h:
            changes.append(
                {"type": "field_removed", "section": key, "detail": f"{key} (was '{old_h[key]}')"}
            )

    # --- table row additions (new events / hearings / charges ...) ---------
    old_tables = {_table_key(t): t for t in old.get("tables", [])}
    new_tables = {_table_key(t): t for t in new.get("tables", [])}
    for key, ntable in new_tables.items():
        otable = old_tables.get(key)
        old_rows = {_row_signature(r) for r in (otable.get("rows", []) if otable else [])}
        for row in ntable.get("rows", []):
            sig = _row_signature(row)
            if sig not in old_rows:
                label = ntable.get("caption") or " / ".join(ntable.get("headers") or []) or "record"
                changes.append(
                    {"type": "row_added", "section": label, "detail": sig}
                )

    # --- fallback: content changed but nothing structured caught it --------
    if not changes and old.get("text_hash") != new.get("text_hash"):
        changes.append(
            {
                "type": "content_changed",
                "section": "page",
                "detail": "Case page content changed (no specific field/row isolated).",
            }
        )

    return changes
