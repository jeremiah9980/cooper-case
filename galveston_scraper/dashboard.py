"""Render a self-contained HTML dashboard from the latest snapshot + changelog."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any

from .config import Config


def _read_changelog(cfg: Config, limit: int = 200) -> list[dict[str, Any]]:
    if not cfg.changelog_file.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in cfg.changelog_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    entries.reverse()  # newest first
    return entries[:limit]


def _read_latest(cfg: Config) -> dict[str, Any] | None:
    if not cfg.latest_snapshot_file.exists():
        return None
    try:
        return json.loads(cfg.latest_snapshot_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def _fmt_ts(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except (ValueError, AttributeError):
        return ts


_CHANGE_LABELS = {
    "baseline": "Monitoring started",
    "field_added": "New field",
    "field_changed": "Field changed",
    "field_removed": "Field removed",
    "row_added": "New entry",
    "content_changed": "Content changed",
}


def _render_header_table(header: dict[str, Any]) -> str:
    if not header:
        return "<p class='muted'>No summary fields captured.</p>"
    rows = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in header.items()
    )
    return f"<table class='kv'>{rows}</table>"


def _render_tables(tables: list[dict[str, Any]]) -> str:
    if not tables:
        return ""
    out = []
    for t in tables:
        cap = t.get("caption") or " / ".join(t.get("headers") or []) or "Records"
        headers = t.get("headers") or []
        thead = ""
        if headers:
            thead = "<tr>" + "".join(f"<th>{_esc(h)}</th>" for h in headers) + "</tr>"
        body = ""
        for row in t.get("rows", []):
            body += "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
        out.append(
            f"<section class='panel'><h3>{_esc(cap)} "
            f"<span class='count'>{len(t.get('rows', []))}</span></h3>"
            f"<div class='scroll'><table class='grid'>{thead}{body}</table></div></section>"
        )
    return "".join(out)


def _render_changes(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "<p class='muted'>No changes recorded yet.</p>"
    items = []
    for e in entries:
        ts = _fmt_ts(e.get("timestamp", ""))
        for c in e.get("changes", []):
            label = _CHANGE_LABELS.get(c.get("type", ""), c.get("type", "change"))
            cls = "baseline" if c.get("type") == "baseline" else "change"
            items.append(
                f"<li class='{cls}'><span class='when'>{_esc(ts)}</span>"
                f"<span class='tag'>{_esc(label)}</span>"
                f"<span class='sec'>{_esc(c.get('section', ''))}</span>"
                f"<span class='det'>{_esc(c.get('detail', ''))}</span></li>"
            )
    return f"<ul class='timeline'>{''.join(items)}</ul>"


def build_dashboard(cfg: Config) -> str:
    """Write dashboard.html and return its path."""
    cfg.ensure_dirs()
    snap = _read_latest(cfg)
    changelog = _read_changelog(cfg)
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    case = snap.get("case_number", cfg.case_number) if snap else cfg.case_number
    caption = snap.get("caption", "") if snap else ""
    fetched = _fmt_ts(snap.get("fetched_at", "")) if snap else "never"
    header_tbl = _render_header_table(snap.get("header", {})) if snap else "<p class='muted'>No snapshot yet. Run a poll.</p>"
    tables_html = _render_tables(snap.get("tables", [])) if snap else ""
    changes_html = _render_changes(changelog)
    n_changes = sum(len(e.get("changes", [])) for e in changelog)
    src_url = snap.get("url", "") if snap else ""

    doc = _TEMPLATE.format(
        case=_esc(case),
        caption=_esc(caption),
        fetched=_esc(fetched),
        generated=_esc(now),
        n_changes=n_changes,
        header_tbl=header_tbl,
        tables_html=tables_html,
        changes_html=changes_html,
        src_url=_esc(src_url),
    )
    cfg.dashboard_file.write_text(doc, encoding="utf-8")
    return str(cfg.dashboard_file)


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Case {case} - Monitor</title>
<style>
  :root {{
    --bg:#0f1420; --card:#1a2130; --line:#2a3547; --text:#e7ecf3;
    --muted:#8b98ad; --accent:#4f8cff; --good:#37b57f; --warn:#f0a742;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{ --bg:#f2f4f8; --card:#fff; --line:#dbe1ea; --text:#1a2230;
      --muted:#5c6a7e; --accent:#2f6bd6; --good:#1f9d63; --warn:#c07d15; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
    font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }}
  header.top {{ background:var(--card); border-bottom:1px solid var(--line);
    padding:20px 24px; }}
  header.top h1 {{ margin:0 0 4px; font-size:22px; }}
  header.top .cap {{ color:var(--muted); font-size:14px; }}
  .meta {{ margin-top:10px; display:flex; gap:20px; flex-wrap:wrap;
    font-size:13px; color:var(--muted); }}
  .meta b {{ color:var(--text); font-weight:600; }}
  main {{ max-width:1100px; margin:0 auto; padding:24px; display:grid;
    grid-template-columns:1fr; gap:20px; }}
  @media (min-width:900px) {{ main {{ grid-template-columns:1.1fr 1.4fr; }}
    .full {{ grid-column:1 / -1; }} }}
  .panel {{ background:var(--card); border:1px solid var(--line);
    border-radius:12px; padding:16px 18px; }}
  .panel h2, .panel h3 {{ margin:0 0 12px; font-size:16px; }}
  .panel h3 {{ font-size:14px; }}
  .count {{ background:var(--line); color:var(--muted); font-size:12px;
    padding:1px 8px; border-radius:20px; margin-left:6px; }}
  table {{ border-collapse:collapse; width:100%; }}
  table.kv th {{ text-align:left; color:var(--muted); font-weight:500;
    padding:6px 12px 6px 0; vertical-align:top; white-space:nowrap; }}
  table.kv td {{ padding:6px 0; }}
  table.kv tr + tr th, table.kv tr + tr td {{ border-top:1px solid var(--line); }}
  .scroll {{ overflow-x:auto; }}
  table.grid {{ font-size:13px; }}
  table.grid th {{ text-align:left; color:var(--muted); font-weight:600;
    padding:8px 10px; border-bottom:2px solid var(--line); white-space:nowrap; }}
  table.grid td {{ padding:7px 10px; border-bottom:1px solid var(--line);
    vertical-align:top; }}
  ul.timeline {{ list-style:none; margin:0; padding:0; }}
  ul.timeline li {{ display:grid; grid-template-columns:150px 120px 1fr;
    gap:8px 14px; padding:10px 0; border-bottom:1px solid var(--line);
    align-items:baseline; }}
  ul.timeline li .when {{ color:var(--muted); font-size:12px; }}
  ul.timeline li .tag {{ font-size:12px; font-weight:600; color:var(--accent); }}
  ul.timeline li.baseline .tag {{ color:var(--good); }}
  ul.timeline li .sec {{ display:none; }}
  ul.timeline li .det {{ grid-column:3; word-break:break-word; }}
  @media (max-width:640px) {{ ul.timeline li {{ grid-template-columns:1fr; }} }}
  .muted {{ color:var(--muted); }}
  a {{ color:var(--accent); }}
  footer {{ text-align:center; color:var(--muted); font-size:12px;
    padding:24px; }}
</style>
</head>
<body>
<header class="top">
  <h1>Case {case}</h1>
  <div class="cap">{caption}</div>
  <div class="meta">
    <span>Last fetched: <b>{fetched}</b></span>
    <span>Total changes logged: <b>{n_changes}</b></span>
    <span>Dashboard generated: <b>{generated}</b></span>
    <span><a href="{src_url}" target="_blank" rel="noopener">Source page</a></span>
  </div>
</header>
<main>
  <section class="panel">
    <h2>Case Summary</h2>
    {header_tbl}
  </section>
  <section class="panel">
    <h2>Change History</h2>
    {changes_html}
  </section>
  <div class="full">{tables_html}</div>
</main>
<footer>Galveston County case monitor &middot; data sourced from the public Tyler Odyssey portal.</footer>
</body>
</html>
"""
