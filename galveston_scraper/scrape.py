"""Fetch and parse a Tyler Odyssey case-detail page into a structured snapshot.

The parser is deliberately tolerant. Odyssey renders case detail slightly
differently across deployments and case types, so instead of hard-coding one
DOM layout we extract three complementary views of the page:

  * header  -- label/value pairs from the case summary (case #, style, court,
               status, file date, ...)
  * tables  -- every data grid on the page (events / register of actions,
               hearings, charges, dispositions, financials, parties)
  * text    -- a normalised hash of the visible case content

Change detection (see diff.py) works off all three, so even if a particular
section is not recognised structurally, any new content still flips the text
hash and is surfaced.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from playwright.sync_api import BrowserContext

# JavaScript run inside the page to pull structured data out of the DOM.
_EXTRACT_JS = r"""
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();

  // 1) The main content region (fall back to body).
  const main =
    document.querySelector('#caseSummaryContainer') ||
    document.querySelector('.portlet-body') ||
    document.querySelector('#divContent, #content, main') ||
    document.body;

  // 2) Label/value pairs -- Odyssey uses a few different markups.
  const header = {};
  const addPair = (k, v) => {
    k = clean(k).replace(/:$/, '');
    v = clean(v);
    if (k && v && k.length < 60 && !(k in header)) header[k] = v;
  };
  main.querySelectorAll('dl').forEach((dl) => {
    const dts = dl.querySelectorAll('dt');
    const dds = dl.querySelectorAll('dd');
    for (let i = 0; i < Math.min(dts.length, dds.length); i++) {
      addPair(dts[i].innerText, dds[i].innerText);
    }
  });
  // label/value class pairs sitting next to each other
  main.querySelectorAll('[class*="abel"]').forEach((el) => {
    const sib = el.nextElementSibling;
    if (sib && /alue|data|text/i.test(sib.className || '')) {
      addPair(el.innerText, sib.innerText);
    }
  });

  // 3) All tables -> {caption, headers, rows}
  const tables = [];
  main.querySelectorAll('table').forEach((t) => {
    const headers = Array.from(t.querySelectorAll('thead th, thead td')).map(
      (th) => clean(th.innerText)
    );
    const bodyRows = t.querySelectorAll('tbody tr').length
      ? t.querySelectorAll('tbody tr')
      : t.querySelectorAll('tr');
    const rows = [];
    bodyRows.forEach((tr) => {
      if (tr.querySelector('th') && !tr.querySelector('td')) return; // header row
      const cells = Array.from(tr.querySelectorAll('td')).map((td) =>
        clean(td.innerText)
      );
      if (cells.some((c) => c)) rows.push(cells);
    });
    if (rows.length) {
      // nearest preceding heading as a caption
      let cap = '';
      const capEl =
        t.closest('section, .portlet, .panel, .k-widget')?.querySelector(
          'h1,h2,h3,h4,.panel-title,.k-header,legend'
        );
      if (capEl) cap = clean(capEl.innerText);
      tables.push({ caption: cap, headers, rows });
    }
  });

  // 4) The case caption / style, usually the biggest heading.
  let caption = '';
  const h = main.querySelector('h1, h2, .caseStyle, #caseName, .case-title');
  if (h) caption = clean(h.innerText);

  return {
    title: document.title,
    caption,
    header,
    tables,
    text: clean(main.innerText),
  };
}
"""


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def _looks_like_case_page(raw: dict, case_number: str) -> bool:
    """Heuristic: did we actually land on a case page (not an error/search)?"""
    blob = (raw.get("text", "") + " " + raw.get("title", "")).lower()
    if "error" in raw.get("title", "").lower():
        return False
    # Case number present, or any recognisable case section.
    norm_case = re.sub(r"[^a-z0-9]", "", case_number.lower())
    norm_blob = re.sub(r"[^a-z0-9]", "", blob)
    if norm_case and norm_case in norm_blob:
        return True
    return bool(raw.get("tables")) and any(
        w in blob for w in ("register of actions", "events", "hearing", "disposition", "charge")
    )


def fetch_snapshot(context: BrowserContext, case_detail_url: str, case_number: str) -> dict[str, Any]:
    """Navigate to the case detail URL and return a normalised snapshot dict.

    Raises RuntimeError if the page does not look like a valid case page (for
    example, if the captured session/URL has expired and the portal bounced us
    back to a search or error screen).
    """
    page = context.new_page()
    try:
        page.goto(case_detail_url, wait_until="domcontentloaded")
        # Odyssey loads case sections via script after DOMContentLoaded.
        try:
            page.wait_for_load_state("networkidle", timeout=45_000)
        except Exception:
            pass
        page.wait_for_timeout(2500)
        raw = page.evaluate(_EXTRACT_JS)
        final_url = page.url
    finally:
        page.close()

    if not _looks_like_case_page(raw, case_number):
        raise RuntimeError(
            "The case detail page did not render expected content. The saved "
            "session may have expired -- re-run `bootstrap`. (landed on: "
            f"{final_url})"
        )

    snapshot = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "case_number": case_number,
        "url": final_url,
        "page_title": raw.get("title", ""),
        "caption": raw.get("caption", ""),
        "header": raw.get("header", {}),
        "tables": raw.get("tables", []),
        "text_hash": _hash_text(raw.get("text", "")),
        "text_len": len(raw.get("text", "")),
    }
    return snapshot
