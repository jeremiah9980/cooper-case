"""One-time bootstrap: capture the captcha-free case-detail URL + session.

Every anonymous *search* on the Galveston portal is protected by a Google
reCAPTCHA v2 image challenge, which cannot be solved unattended. Case *detail*
pages, however, are not captcha-gated. So we ask a human to do the captcha
exactly once; the tool then records the resulting detail URL and browser
cookies, and every future poll reuses them without any captcha.

Two ways to bootstrap:

  1. Interactive (default): opens a real browser window. You solve the
     "I'm not a robot" checkbox, search the case number, and click into the
     case. As soon as a case-detail page loads, the tool saves everything and
     closes.

  2. Manual URL (`--case-url`): if you would rather do the search in your own
     browser, just copy the case-detail page URL from the address bar and pass
     it in. No automated browser needed.
"""

from __future__ import annotations

import json
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


def bootstrap_from_url(cfg: Config, case_url: str) -> str:
    """Record a manually supplied case-detail URL (and grab a fresh session)."""
    cfg.ensure_dirs()
    # Establish a normal (captcha-free) portal session for later polling.
    with browser_context(cfg, headless=True, use_saved_state=False) as (_p, _b, context):
        page = context.new_page()
        try:
            page.goto(cfg.portal_base_url + "/Home/WorkspaceMode?p=0", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
        finally:
            page.close()
        _save_bootstrap(cfg, case_url, context)
    print(f"Saved case detail URL and session for {cfg.case_number}:\n  {case_url}")
    return case_url


def bootstrap_interactive(cfg: Config, timeout_seconds: int = 600) -> str:
    """Open a window, let a human solve the captcha, capture the detail URL.

    Returns the captured URL. Requires a display (headless=False), so run this
    on a desktop machine, not a headless server.
    """
    print(
        "\nA browser window will open.\n"
        f"  1. Solve the 'I'm not a robot' captcha.\n"
        f"  2. Search for case number: {cfg.case_number}\n"
        "  3. Click the case to open its detail page.\n"
        "The tool will detect the case-detail page automatically and finish.\n"
    )
    deadline_ms = timeout_seconds * 1000
    with browser_context(cfg, headless=False, use_saved_state=False) as (_p, _b, context):
        page = context.new_page()
        page.goto(cfg.portal_base_url + "/Home/WorkspaceMode?p=0", wait_until="domcontentloaded")

        waited = 0
        step = 1000
        captured = ""
        while waited < deadline_ms:
            url = page.url
            if _is_case_detail_url(url):
                captured = url
                break
            page.wait_for_timeout(step)
            waited += step

        if not captured:
            raise TimeoutError(
                "Timed out waiting for a case-detail page. Re-run bootstrap, or "
                "use `--case-url` to paste the URL directly."
            )
        page.wait_for_timeout(2000)  # let the detail page settle before saving cookies
        _save_bootstrap(cfg, captured, context)

    print(f"\nCaptured case detail URL:\n  {captured}")
    return captured


def _is_case_detail_url(url: str) -> bool:
    u = url.lower()
    return "casedetail" in u or ("/cases/" in u and "search" not in u)
