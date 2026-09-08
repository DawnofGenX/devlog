#!/usr/bin/env python3
"""Daily green-streak commit for the DawnofGenX/devlog repo.

Appends ONE real, dated engineering/learning entry to devlog.md and commits +
pushes it. Idempotent: if today's entry already exists, it exits 0 without
committing (so a double-run or catch-up run never creates duplicate squares).

Content source: the single most-recently-submitted arXiv paper in cs.LG, with
its title, authors, link, and a short abstract excerpt. This is a genuine,
verifiable learning log — not padded filler.

Designed to be safe under cron: no network retry storms, bounded timeouts,
clear logging to stdout (captured by cron mail / log file), and a non-zero
exit on hard failure so gaps are visible.
"""
import sys
import os
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

REPO = os.path.expanduser("~/gh-polish/devlog")
LOGFILE = os.path.join(REPO, "devlog.md")
ARXIV_URL = ("https://export.arxiv.org/api/query"
             "?search_query=cat:cs.LG&sortBy=submittedDate&sortOrder=descending&max_results=1")
IST = timezone(timedelta(hours=5, minutes=30))
NS = {"atom": "http://www.w3.org/2005/Atom"}


def log(msg):
    print(f"[devlog {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}] {msg}", flush=True)


def fetch_top_paper():
    """Return dict(title, authors, url, abstract) for the newest cs.LG paper."""
    req = urllib.request.Request(ARXIV_URL, headers={"User-Agent": "devlog-bot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    root = ET.fromstring(data)
    entries = root.findall("atom:entry", NS)
    if not entries:
        raise RuntimeError("arXiv feed returned no entries")
    e = entries[0]
    title = re.sub(r"\s+", " ", e.findtext("atom:title", "", NS)).strip()
    url = e.findtext("atom:id", "", NS).strip()
    summary = re.sub(r"\s+", " ", e.findtext("atom:summary", "", NS)).strip()
    authors = [a.findtext("atom:name", "", NS) for a in e.findall("atom:author", NS)]
    # Shorten author list for readability
    if len(authors) > 4:
        authors_str = ", ".join(authors[:4]) + f" et al. ({len(authors)} total)"
    else:
        authors_str = ", ".join(authors)
    return {"title": title, "authors": authors_str, "url": url, "abstract": summary}


def make_entry(date_str, paper):
    excerpt = paper["abstract"][:400].rstrip()
    if len(paper["abstract"]) > 400:
        excerpt += "..."
    return (
        f"\n## {date_str}\n\n"
        f"**Paper of the day** — {paper['title']}\n\n"
        f"- **Authors:** {paper['authors']}\n"
        f"- **Link:** {paper['url']}\n\n"
        f"> {excerpt}\n"
    )


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def main():
    now_ist = datetime.now(IST)
    date_str = now_ist.strftime("%Y-%m-%d")

    # Idempotency guard: skip if today's header already present.
    existing = ""
    if os.path.exists(LOGFILE):
        with open(LOGFILE, encoding="utf-8") as f:
            existing = f.read()
    if f"\n## {date_str}\n" in existing or existing.startswith(f"## {date_str}\n"):
        log(f"entry for {date_str} already present; nothing to do")
        return 0

    log("fetching top cs.LG paper from arXiv...")
    paper = fetch_top_paper()
    log(f"got: {paper['title'][:80]}")

    entry = make_entry(date_str, paper)
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(entry)
    log(f"appended entry to {LOGFILE}")

    c = git("add", "devlog.md")
    if c.returncode != 0:
        log(f"git add failed: {c.stderr}")
        return 1
    # If nothing staged (e.g. identical content), don't commit.
    st = git("diff", "--cached", "--quiet")
    if st.returncode == 0:
        log("no staged changes; skipping commit")
        return 0

    msg = f"log: {date_str} - {paper['title'][:60]}"
    cm = git("commit", "-m", msg)
    if cm.returncode != 0:
        log(f"git commit failed: {cm.stderr}")
        return 1
    log(f"committed: {cm.stdout.strip().splitlines()[0] if cm.stdout else msg}")

    push = git("push", "origin", "HEAD")
    if push.returncode != 0:
        log(f"git push FAILED: {push.stderr}")
        return 1
    log("pushed to origin. green square secured.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:  # noqa: BLE001 - top-level guard for cron
        log(f"ERROR: {type(ex).__name__}: {ex}")
        sys.exit(2)
