# kitten-watch

Checks Dyrenes Beskyttelse Aarhus roughly every 15 minutes and pushes to
[ntfy.sh](https://ntfy.sh):

- **urgent** when a name resembles **Robina** or **Ally** (difflib, 0.75)
- **normal** when any animal appears that was not on the list last time

The second matters: matching on the name alone is fragile, because the shelter
may list the cat under a different name and then a name-only watcher stays
silent forever.

- `check_kittens.py` — scrape, fuzzy match (`difflib`, threshold 0.75), notify.
- `.github/workflows/check-kittens.yml` — cron + manual trigger.

`seen_ids.json` holds names already notified about, so a standing match does
not re-alert. It lives in the Actions cache rather than the repo.

## Setup

    gh secret set NTFY_TOPIC --body "<your-topic>"

Then subscribe to that topic in the ntfy app.

**The topic name is the only secret.** ntfy has no auth on free topics — anyone
who guesses or sees the name can read your notifications, and send you fake
ones. Use something long and random, not "kittens".

## Run locally

    pip install requests beautifulsoup4
    NTFY_TOPIC=<your-topic> python check_kittens.py

Without `NTFY_TOPIC` it prints matches and skips the push, which is a safe
way to see what it would do.

## Notes

- Verified against the live page 2026-09-04: server-rendered, no JS needed.
- The script exits non-zero if it finds zero listings, so a markup change
  shows up as a failed run instead of silence.
- GitHub disables scheduled workflows after 60 days without repo activity.
