#!/usr/bin/env python3
"""Fetch citation counts from Google Scholar and write citations.json.

Run daily by .github/workflows/update-citations.yml. Exits non-zero (leaving the
existing citations.json untouched) if Scholar blocks the request or the page
layout changes, so a bad scrape never overwrites good numbers.
"""
import datetime
import html
import json
import pathlib
import re
import sys
import urllib.request

USER = "vM1SktEAAAAJ"
URL = f"https://scholar.google.com/citations?user={USER}&hl=en&cstart=0&pagesize=100"
OUT = pathlib.Path(__file__).resolve().parent.parent / "citations.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def norm(title):
    """Lowercase alphanumerics only, so small punctuation/case differences still match."""
    return re.sub(r"[^a-z0-9]", "", html.unescape(title).lower())


def main():
    req = urllib.request.Request(URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        page = resp.read().decode("utf-8", "replace")

    # stats table: citations (all, since), h-index (all, since), i10-index (all, since)
    stats = [int(n) for n in re.findall(r'class="gsc_rsb_std">(\d+)<', page)]
    rows = re.findall(r'<tr class="gsc_a_tr">(.*?)</tr>', page, re.S)
    if len(stats) < 6 or len(rows) < 10:
        sys.exit(f"Unexpected Scholar response (stats={len(stats)}, rows={len(rows)}); possibly blocked. Keeping old data.")

    papers = {}
    for row in rows:
        title = re.search(r'class="gsc_a_at">(.*?)</a>', row, re.S)
        cites = re.search(r'class="gsc_a_ac[^"]*">(\d*)</a>', row)
        if title:
            # the same title can appear twice (e.g. arXiv + conference version); keep the larger count
            key = norm(title.group(1))
            papers[key] = max(papers.get(key, 0), int(cites.group(1)) if cites and cites.group(1) else 0)

    data = {
        "updated": datetime.date.today().isoformat(),
        "citations": stats[0],
        "h_index": stats[2],
        "i10_index": stats[4],
        "papers": papers,
    }
    OUT.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    print(f"Wrote {OUT.name}: {stats[0]} citations, h={stats[2]}, i10={stats[4]}, {len(papers)} papers")


if __name__ == "__main__":
    main()
