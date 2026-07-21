# Galveston County Case Monitor

Watches a single case on the [Galveston County public court portal][portal]
(a Tyler **Odyssey** portal), detects changes, sends a **Slack** notification
when something changes, and keeps a self-contained HTML **dashboard** up to
date.

Default case: **24-CR-1362**.

[portal]: https://portalnav19.galvestoncountytx.gov/Portal/Home/WorkspaceMode?p=0

---

## Important: how this portal is protected (read this first)

Every anonymous **search** on the Galveston portal — both *Smart Search* and
*Hearing Search* — is gated behind a **Google reCAPTCHA v2** "I'm not a robot"
checkbox that escalates to image challenges. That is deliberate anti-bot
protection, and it means a script **cannot search the portal unattended**.
This tool does **not** attempt to solve, bypass, or outsource the captcha.

What *is* automatable: once you are on a **case-detail page**, that page is
**not** captcha-protected — only search is. So the design is
**bootstrap once, poll forever**:

1. **Bootstrap (one time, ~30 seconds, human):** you solve the captcha a single
   time and open the case. The tool records the case-detail URL and your
   browser session.
2. **Poll (unattended, every 5–10 min):** the tool fetches that detail URL
   directly, parses it, compares against the last snapshot, reports changes to
   Slack, and rewrites the dashboard.

If the saved session ever expires, polling tells you to re-run bootstrap.

---

## Install

```sh
pip install -r requirements.txt
python -m playwright install chromium      # one-time browser download
cp config.example.json config.json         # then edit config.json
```

Python 3.10+.

---

## 1. Bootstrap (capture the case URL)

**Option A — interactive** (on a desktop with a screen). A browser window opens;
solve the captcha, search `24-CR-1362`, click into the case:

```sh
python -m galveston_scraper bootstrap
```

The tool auto-detects the case-detail page and saves it.

**Option B — paste the URL** (works anywhere, including headless servers). In
*your own* browser, search the case, open it, copy the URL from the address
bar, then:

```sh
python -m galveston_scraper bootstrap --case-url "https://portalnav19.galvestoncountytx.gov/Portal/Cases/CaseDetail?...."
```

Either way the URL is stored in `data/bootstrap.json`. You can also just paste
it into `case_detail_url` in `config.json` and skip bootstrap entirely.

Check state at any time:

```sh
python -m galveston_scraper status
```

---

## 2. Poll and detect changes

One poll (fetch → diff → report → refresh dashboard):

```sh
python -m galveston_scraper poll
```

The first poll records a baseline. Every later poll reports differences:

- **Case summary fields** changed/added/removed (status, court, next setting, …)
- **New rows** in any grid — new Register-of-Actions events, hearings, charges,
  dispositions, financial entries
- A **content-changed** fallback if the page changed in a way the structured
  parser did not isolate

Detected changes are appended to `data/changelog.jsonl` and pushed to Slack.

---

## 3. Slack notifications

1. Create an **Incoming Webhook** in Slack: <https://api.slack.com/messaging/webhooks>
   (Create app → *Incoming Webhooks* → enable → *Add New Webhook to Workspace* →
   pick a channel → copy the `https://hooks.slack.com/services/…` URL).
2. Put it in `config.json`:

   ```json
   "notify": { "console": true, "webhook_url": "https://hooks.slack.com/services/XXX/YYY/ZZZ", "webhook_format": "slack" }
   ```

   or export it: `export GALV_WEBHOOK_URL="https://hooks.slack.com/services/…"`.

Each change posts a message like:

> `[2026-07-21T17:07:00Z] 24-CR-1362: 2 change(s) detected`
> - Status: 'Pending' -> 'Disposed'
> - Events: 07/20/2026 | Judgment Entered

`webhook_format` also supports `discord` and `generic` (raw JSON) if you would
rather notify elsewhere.

---

## 4. Run every 5–10 minutes

Pick one:

- **Foreground loop:** `./scheduler/run_loop.sh` (uses `poll_interval_seconds`
  from config; default 420 s = 7 min).
- **cron:** see [`scheduler/cron.md`](scheduler/cron.md) — e.g. `*/7 * * * *`.
- **systemd timer:** see [`scheduler/galveston-monitor.service`](scheduler/galveston-monitor.service)
  and `.timer` (fires every 7 min).

The dashboard at **`data/dashboard.html`** is regenerated on every poll — open
it in a browser, or serve `data/` behind any static web server / GitHub Pages.

---

## The dashboard

`data/dashboard.html` is a single self-contained file (no external assets,
light/dark aware) showing:

- Case number, style, and the last-fetched time
- The current case summary fields
- A reverse-chronological **change timeline**
- The current data grids (events, hearings, charges, …)

Rebuild it on demand without polling:

```sh
python -m galveston_scraper dashboard
```

---

## Configuration reference

| Key | Env override | Meaning |
| --- | --- | --- |
| `case_number` | `GALV_CASE_NUMBER` | Case being monitored |
| `case_detail_url` | `GALV_CASE_DETAIL_URL` | Detail URL (else from bootstrap) |
| `data_dir` | `GALV_DATA_DIR` | Where snapshots/logs/dashboard live |
| `poll_interval_seconds` | `GALV_POLL_INTERVAL` | Loop interval (min 60) |
| `headless` | `GALV_HEADLESS` | Headless polling (bootstrap is always headed) |
| `notify.webhook_url` | `GALV_WEBHOOK_URL` | Slack (or other) webhook |

`config.json` and everything under `data/` are git-ignored — your webhook URL
and session cookies stay local.

---

## Files

```
galveston_scraper/
  __main__.py    CLI: bootstrap | poll | watch | dashboard | status
  config.py      config + paths (JSON file + env overrides)
  browser.py     Playwright launch/context helper
  bootstrap.py   one-time captcha solve / URL capture + session save
  scrape.py      fetch + parse case-detail page into a snapshot
  diff.py        snapshot comparison -> change records
  report.py      console + changelog + Slack/Discord/generic webhook
  dashboard.py   render the self-contained HTML dashboard
  poll.py        one poll and the continuous loop
scheduler/       run_loop.sh, cron.md, systemd unit + timer
data/            runtime output (git-ignored)
```

---

## Notes & limitations

- **The captcha is a hard wall for search.** If the case-detail URL structure
  ever requires a fresh search (e.g. the portal rotates the case token), you
  re-run the ~30-second bootstrap. Day-to-day polling stays hands-off.
- Only **publicly visible** case information is read; nothing is submitted and
  no login is required.
- Be a good citizen: a 5–10 minute cadence is gentle. Don't crank it to seconds.
- Parsing is tolerant across Odyssey layouts, but if this county customizes the
  detail page heavily, tune the selectors in `scrape.py`. The text-hash
  fallback still catches any change even when a field isn't individually parsed.
