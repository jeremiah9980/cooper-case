# Running the monitor on a schedule with cron

`cron`'s finest granularity is one minute, which is plenty for a 5–10 minute
poll. Each invocation runs a **single** poll (`poll`, not `watch`) so runs never
overlap.

Edit your crontab:

```sh
crontab -e
```

Add one of these lines (adjust the path to where you cloned the repo):

```cron
# Every 7 minutes
*/7 * * * * cd /path/to/cooper-case && /usr/bin/python3 -m galveston_scraper poll >> data/cron.log 2>&1

# Every 5 minutes
*/5 * * * * cd /path/to/cooper-case && /usr/bin/python3 -m galveston_scraper poll >> data/cron.log 2>&1
```

Notes:

- Use an absolute python path (`which python3`) — cron has a minimal `PATH`.
- If you use a virtualenv, point at `.venv/bin/python` instead.
- Secrets (Slack webhook) can live in `config.json` or be exported in the
  crontab with `GALV_WEBHOOK_URL=...` on the line before the job.
- The dashboard at `data/dashboard.html` is rewritten on every poll.
