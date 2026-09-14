#!/usr/bin/env python3
"""Daily green-streak commit for the DawnofGenX/devlog repo.

Appends ONE dated entry with up to 3 real arXiv cs.LG papers to devlog.md
and commits + pushes it. Idempotent: if today's entry already exists,
exits 0 without committing (so double-runs or catch-up never duplicate).
Pass --force to overwrite today's entry (useful for upgrading 1-paper days).
Pass --backlog N to pre-stage entries for the next N days in backlog.json;
the daily run consumes today's staged entry (if any) before hitting the
network, so the green square survives WSL being off during the fetch window.

Content source: the 3 most-recently-submitted arXiv papers in cs.LG.
A genuine, verifiable learning log — not padded filler.

Designed to be safe under cron: no network retry storms, bounded timeouts,
clear logging, non-zero exit on hard failure so gaps are visible.
"""
import argparse
import json
import sys
import os
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

REPO = os.path.expanduser("~/gh-polish/devlog")
LOGFILE = os.path.join(REPO, "devlog.md")
BACKLOG = os.path.join(REPO, "backlog.json")
ARXIV_URL = (
    "https://export.arxiv.org/api/query"
    "?search_query=cat:cs.LG&sortBy=submittedDate&sortOrder=descending&max_results=3"
)
RSS_URL = "https://rss.arxiv.org/rss/cs.LG"
IST = timezone(timedelta(hours=5, minutes=30))
NS = {"atom": "http://www.w3.org/2005/Atom"}


def log(msg):
    print(f"[devlog {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}] {msg}", flush=True)


def _fmt_authors(authors):
    if len(authors) > 4:
        return ", ".join(authors[:4]) + f" et al. ({len(authors)} total)"
    return ", ".join(authors)


def fetch_top_papers(n=3, offset=0):
    """Return list of dicts(title, authors, url, abstract) for n newest cs.LG papers.

    Tries the export API first; falls back to the RSS feed on HTTP errors
    (the export API 429s under load, which would otherwise break cron).
    """
    try:
        req = urllib.request.Request(ARXIV_URL + f"&start={offset}", headers={"User-Agent": "devlog-bot/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        root = ET.fromstring(data)
        entries = root.findall("atom:entry", NS)
        if not entries:
            raise RuntimeError("arXiv feed returned no entries")
        out = []
        for e in entries[:n]:
            title = re.sub(r"\s+", " ", e.findtext("atom:title", "", NS)).strip()
            url = e.findtext("atom:id", "", NS).strip()
            summary = re.sub(r"\s+", " ", e.findtext("atom:summary", "", NS)).strip()
            authors = [a.findtext("atom:name", "", NS) for a in e.findall("atom:author", NS)]
            out.append({"title": title, "authors": _fmt_authors(authors), "url": url, "abstract": summary})
        return out
    except Exception as ex:  # noqa: BLE001 - fall through to RSS
        log(f"export API failed ({type(ex).__name__}: {ex}); falling back to RSS feed")
        return fetch_top_papers_rss(n, offset)


def _fetch_authors_from_abs(url):
    """Scrape citation_author meta tags from an arXiv abs page (best effort)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "devlog-bot/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
        return re.findall(r'<meta name="citation_author" content="([^"]+)"', html)
    except Exception:  # noqa: BLE001 - best effort only
        return []


def fetch_top_papers_rss(n=3, offset=0):
    """Fallback: parse the arXiv cs.LG RSS feed (different endpoint, rarely 429s)."""
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": "devlog-bot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    root = ET.fromstring(data)
    items = root.findall(".//item")
    if not items:
        raise RuntimeError("arXiv RSS feed returned no items")
    DC = {"dc": "http://purl.org/dc/elements/1.1/"}
    out = []
    for it in items[offset:offset + n]:
        title = re.sub(r"\s+", " ", it.findtext("title", "")).strip()
        url = it.findtext("link", "").strip()
        desc = re.sub(r"\s+", " ", it.findtext("description", "")).strip()
        m = re.search(r"Abstract:\s*(.*)$", desc)
        summary = m.group(1).strip() if m else desc
        authors = [a.findtext("dc:creator", "", DC) for a in it.findall("author")]
        authors = [a for a in authors if a] or _fetch_authors_from_abs(url)
        out.append({"title": title, "authors": _fmt_authors(authors) or "unknown", "url": url, "abstract": summary})
    return out


def make_entry(date_str, papers):
    """Build a dated section with up to 3 papers."""
    lines = [f"\n## {date_str}\n"]
    for i, paper in enumerate(papers, 1):
        excerpt = paper["abstract"][:400].rstrip()
        if len(paper["abstract"]) > 400:
            excerpt += "..."
        lines.append(
            f"\n### Paper {i} — {paper['title']}\n\n"
            f"- **Authors:** {paper['authors']}\n"
            f"- **Link:** {paper['url']}\n\n"
            f"> {excerpt}\n"
        )
    return "\n".join(lines)


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def load_backlog():
    if os.path.exists(BACKLOG):
        with open(BACKLOG, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_backlog(data):
    with open(BACKLOG, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def commit_and_push(date_str, titles):
    c = git("add", "devlog.md")
    if c.returncode != 0:
        log(f"git add failed: {c.stderr}")
        return 1
    st = git("diff", "--cached", "--quiet")
    if st.returncode == 0:
        log("no staged changes; skipping commit")
        return 0

    msg = f"log: {date_str} — {', '.join(t[:40] for t in titles)}"
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


def main():
    parser = argparse.ArgumentParser(description="Daily devlog entry")
    parser.add_argument("--force", action="store_true", help="Overwrite today's entry")
    parser.add_argument("--backlog", type=int, metavar="N", default=0,
                        help="Pre-stage entries for the next N days in backlog.json")
    args = parser.parse_args()

    now_ist = datetime.now(IST)
    date_str = now_ist.strftime("%Y-%m-%d")

    # Idempotency guard: skip if today's header already present (unless --force).
    existing = ""
    if os.path.exists(LOGFILE):
        with open(LOGFILE, encoding="utf-8") as f:
            existing = f.read()
    has_today = f"\n## {date_str}\n" in existing or existing.startswith(f"## {date_str}\n")
    if has_today and not args.force and args.backlog == 0:
        log(f"entry for {date_str} already present; nothing to do")
        return 0

    # Backlog mode: pre-stage entries for the next N days (no commit/push).
    if args.backlog > 0:
        backlog = load_backlog()
        for i in range(1, args.backlog + 1):
            d = (now_ist + timedelta(days=i)).strftime("%Y-%m-%d")
            if d in backlog:
                log(f"{d}: already staged; skipping")
                continue
            log(f"staging {d}: fetching top 3 cs.LG papers...")
            try:
                # Offset each day's slice so consecutive days get distinct papers
                # (the RSS snapshot is static within a day; the export API also
                # serves the same newest-first list until arXiv announces more).
                papers = fetch_top_papers(3, offset=(i - 1) * 3)
                if not papers:
                    raise RuntimeError("feed slice was empty")
            except Exception as ex:  # noqa: BLE001 - keep going, report at end
                log(f"  ERROR staging {d}: {type(ex).__name__}: {ex}")
                continue
            for p in papers:
                log(f"  - {p['title'][:70]}")
            backlog[d] = {"papers": papers, "staged_at": now_ist.isoformat()}
            save_backlog(backlog)
        remaining = sorted(d for d in backlog if d >= date_str)
        log(f"backlog ready: {remaining}")
        return 0

    # Daily run: consume a staged entry for today if one exists (offline-safe).
    papers = None
    backlog = load_backlog()
    if date_str in backlog:
        papers = backlog[date_str]["papers"]
        del backlog[date_str]
        save_backlog(backlog)
        log(f"using pre-staged entry for {date_str} ({len(papers)} papers)")
    else:
        log("fetching top 3 cs.LG papers from arXiv...")
        papers = fetch_top_papers(3)
        for p in papers:
            log(f"  - {p['title'][:70]}")

    entry = make_entry(date_str, papers)

    if has_today and args.force:
        # Remove today's existing entry before appending the new one.
        # Find the start of today's header and the start of the next header (or EOF).
        lines = existing.split("\n")
        start_idx = None
        end_idx = len(lines)
        for i, line in enumerate(lines):
            if line.strip() == f"## {date_str}":
                start_idx = i
            elif start_idx is not None and line.strip().startswith("## ") and i > start_idx:
                end_idx = i
                break
        new_lines = lines[:start_idx] + lines[end_idx:]
        existing = "\n".join(new_lines)
        log(f"removed existing entry for {date_str} (--force)")

    with open(LOGFILE, "w" if has_today and args.force else "a", encoding="utf-8") as f:
        f.write(existing if has_today and args.force else "")
        f.write(entry)
    log(f"appended entry with {len(papers)} papers to {LOGFILE}")

    return commit_and_push(date_str, [p["title"] for p in papers])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:  # noqa: BLE001 - top-level guard for cron
        log(f"ERROR: {type(ex).__name__}: {ex}")
        sys.exit(2)
