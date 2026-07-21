"""Galveston County (Tyler Odyssey) court-case monitor.

A change-detecting scraper for a single case on the Galveston County public
court portal. Because every anonymous *search* on the portal is gated behind a
Google reCAPTCHA v2 image challenge, this tool separates the work into two
phases:

  * bootstrap  -- one-time, human solves the captcha and lands on the case's
                  detail page; the tool captures the (captcha-free) detail URL
                  and browser session.
  * poll       -- unattended, fetches that detail URL directly every few
                  minutes, parses it, diffs against the last snapshot, and
                  reports any changes.

See the README for the full rationale.
"""

__version__ = "1.0.0"
