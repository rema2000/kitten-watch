# kitten-watch

Checks Dyrenes Beskyttelse Aarhus roughly every 15 minutes for a cat whose name
resembles **Robina** or **Ally**, and pushes to [ntfy.sh](https://ntfy.sh) on a
new match.

- `check_kittens.py` — scrape, fuzzy match (`difflib`, threshold 0.75), notify.
- `.github/workflows/check-kittens.yml` — cron + manual trigger.

`seen_names.json` holds names already notified about, so a standing match does
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
