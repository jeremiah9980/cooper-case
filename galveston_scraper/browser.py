"""Playwright browser helpers.

Works both on a normal machine (just `playwright install chromium` once) and
inside sandboxed CI environments that need a preinstalled Chromium and/or a
disabled proxy. All of the sandbox behaviour is opt-in via environment
variables so it is a no-op for ordinary users:

    GALV_CHROME_PATH   -- explicit path to a chromium executable
    GALV_NO_PROXY=1    -- launch chromium with --no-proxy-server
    GALV_IGNORE_HTTPS=1-- accept intercepted/self-signed TLS certificates
"""

from __future__ import annotations

import contextlib
import os
from typing import Iterator

from playwright.sync_api import Browser, BrowserContext, Playwright, sync_playwright

from .config import Config


def _launch_kwargs(headless: bool) -> dict:
    args = ["--disable-gpu"]
    if os.environ.get("GALV_NO_PROXY", "").strip() in ("1", "true", "yes"):
        args += ["--no-proxy-server", "--no-sandbox"]
    kwargs: dict = {"headless": headless, "args": args}
    if path := os.environ.get("GALV_CHROME_PATH"):
        kwargs["executable_path"] = path
    return kwargs


def _context_kwargs(cfg: Config) -> dict:
    kwargs: dict = {"user_agent": cfg.user_agent, "locale": "en-US"}
    if os.environ.get("GALV_IGNORE_HTTPS", "").strip() in ("1", "true", "yes"):
        kwargs["ignore_https_errors"] = True
    return kwargs


@contextlib.contextmanager
def browser_context(
    cfg: Config,
    *,
    headless: bool | None = None,
    use_saved_state: bool = True,
) -> Iterator[tuple[Playwright, Browser, BrowserContext]]:
    """Yield a ready-to-use (playwright, browser, context) triple.

    If a bootstrap session state file exists and `use_saved_state` is True, the
    context is created with those cookies so the portal treats us as the same
    visitor that solved the captcha.
    """
    if headless is None:
        headless = cfg.headless
    ctx_kwargs = _context_kwargs(cfg)
    if use_saved_state and cfg.state_file.exists():
        ctx_kwargs["storage_state"] = str(cfg.state_file)

    with sync_playwright() as p:
        browser = p.chromium.launch(**_launch_kwargs(headless))
        context = browser.new_context(**ctx_kwargs)
        context.set_default_timeout(60_000)
        try:
            yield p, browser, context
        finally:
            with contextlib.suppress(Exception):
                context.close()
            with contextlib.suppress(Exception):
                browser.close()
