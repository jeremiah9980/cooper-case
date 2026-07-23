"""One-time bootstrap: capture the captcha-free case-detail URL + session.

Every anonymous *search* on the Galveston portal is protected by a Google
reCAPTCHA v2 image challenge, which cannot be solved unattended. Case *detail*
data, however, is not captcha-gated. So we ask a human to do the captcha
exactly once; the tool then records the case's detail URL (the request the
portal itself makes, which carries the encrypted `eid` case token) plus the
browser cookies, and every future poll reuses them without any captcha.

This portal renders case detail inside its single-page "WorkspaceMode" rather
than navigating to a distinct `/Cases/CaseDetail` address, so we cannot rely on
the address bar. Instead we watch network traffic: when you open the case, the
page fetches `.../Portal/Cases/CaseDetail?eid=...`, and that URL is exactly what
the poller needs.

Two ways to bootstrap:

  1. Interactive (default): opens a real browser window. You solve the
     "I'm not a robot" checkbox, search the case number, and click into the
     case. The tool captures the underlying case-detail request automatically,
     verifies it reloads, and finishes.

  2. Manual URL (`--case-url`): pass a `.../Portal/Cases/CaseDetail?eid=...`
     URL directly if you already have one.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .browser import browser_context
from .config import Config


def _save_bootstrap(cfg: Config, url: str, context=None) -> None:
    cfg.ensure_dirs()
    cfg.bootstrap_file.write_text(
        json.dumps(
            {
                "case_number": cfg.case_number,
                "case_detail_url": url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
    )
    if context is not None:
        context.storage_state(path=str(cfg.state_file))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _page_shows_case(page, case_number: str) -> bool:
    """True if the rendered page text contains the case number."""
    try:
        txt = page.inner_text("body")
    except Exception:
        return False
    return _norm(case_number) in _norm(txt)


def _is_case_detail_url(url: str) -> bool:
    u = (url or "").lower()
    return "casedetail" in u or ("/cases/" in u and "search" not in u)


def _validate_detail_url(cfg: Config, context, url: str) -> bool:
    """Open the captured URL in the same session; confirm the case renders."""
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        return _page_shows_case(page, cfg.case_number)
    except Exception:
        return False
    finally:
        page.close()


def bootstrap_from_url(cfg: Config, case_url: str) -> str:
    """Record a manually supplied case-detail URL (and grab a fresh session)."""
    cfg.ensure_dirs()
    with browser_context(cfg, headless=True, use_saved_state=False) as (_p, _b, context):
        page = context.new_page()
        try:
            page.goto(cfg.portal_base_url + "/Home/WorkspaceMode?p=0", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
        finally:
            page.close()
        ok = _validate_detail_url(cfg, context, case_url)
        _save_bootstrap(cfg, case_url, context)
    status = "verified" if ok else "saved (could NOT verify it reloads the case -- see README)"
    print(f"Case detail URL {status} for {cfg.case_number}:\n  {case_url}")
    return case_url


def bootstrap_interactive(cfg: Config, timeout_seconds: int = 600) -> str:
    """Open a window, let a human solve the captcha, capture the detail request.

    Requires a display (headless=False), so run this on a desktop machine.
    """
    print(
        "\nA browser window will open.\n"
        "  1. Solve the 'I'm not a robot' captcha.\n"
        f"  2. Search for case number: {cfg.case_number}\n"
        "  3. Click the case in the results to open its details.\n"
        "The tool captures the case-detail request automatically and finishes.\n"
    )

    # Network capture: remember the best CaseDetail request URL we see.
    captured: dict[str, str | None] = {"url": None}

    def on_request(req) -> None:
        u = req.url
        lu = u.lower()
        if "casedetail" not in lu:
            return
        # Prefer a URL that carries the encrypted case token.
        if captured["url"] is None or ("eid=" in lu and "eid=" not in captured["url"].lower()):
            captured["url"] = u

    deadline_ms = timeout_seconds * 1000
    with browser_context(cfg, headless=False, use_saved_state=False) as (_p, _b, context):
        context.on("request", on_request)
        page = context.new_page()
        page.goto(cfg.portal_base_url + "/Home/WorkspaceMode?p=0", wait_until="domcontentloaded")

        waited, step = 0, 1000
        done_url: str | None = None
        while waited < deadline_ms:
            # Best signal: we saw the CaseDetail request AND the case is on screen.
            if captured["url"] and _page_shows_case(page, cfg.case_number):
                done_url = captured["url"]
                break
            # Fallback: the address bar itself became a case-detail URL.
            if _is_case_detail_url(page.url):
                done_url = page.url
                break
            page.wait_for_timeout(step)
            waited += step

        if not done_url:
            if _page_shows_case(page, cfg.case_number):
                raise RuntimeError(
                    "Reached the case page but could not capture its data URL. "
                    "Open the case's 'Documents' or 'Print' view (which triggers a "
                    "CaseDetail request) and re-run, or pass the URL via --case-url."
                )
            raise TimeoutError(
                "Timed out before the case detail loaded. Re-run bootstrap and make "
                "sure you click into the case from the search results."
            )

        page.wait_for_timeout(1000)
        ok = _validate_detail_url(cfg, context, done_url)
        _save_bootstrap(cfg, done_url, context)

    if ok:
        print(f"\n✓ Captured and verified case detail URL:\n  {done_url}")
    else:
        print(
            f"\n⚠ Captured a case detail URL but could not verify it reloads:\n  {done_url}\n"
            "  Polling may still work; run `python -m galveston_scraper poll` to check."
        )
    return done_url
