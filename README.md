# Devlog — Daily Engineering & Learning Log

A daily, dated record of what I'm reading and building. One entry per day,
committed automatically each morning (IST).

Each entry highlights up to 3 recent papers on arXiv in **cs.LG** (machine
learning) with their titles, authors, links, and short abstract excerpts — a
genuine, verifiable learning log rather than padded filler.

## What's here
- `devlog.md` — the running log (newest entries appended at the bottom)
- `daily_devlog.py` — the script that appends today's entry and commits/pushes it
- `backlog.json` — pre-staged entries for upcoming days (local only, git-ignored)

## Backlog mode
`python3 daily_devlog.py --backlog N` pre-stages real arXiv entries for the
next N days into `backlog.json`. On each day's cron run, if an entry is staged
for today it is consumed and committed without any network access — so the
green square survives WSL being off or arXiv rate-limiting during the fetch
window. Each day gets its own slice of the feed so papers don't repeat.

## Why this exists
Consistency is the point. A green contribution streak built from real, dated
entries signals steady, disciplined work over time.
