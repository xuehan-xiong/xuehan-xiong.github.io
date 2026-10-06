#!/usr/bin/env python3
"""Fetch citation counts from Google Scholar and write citations.json.

Run weekly by .github/workflows/update-citations.yml. Scholar blocks requests from
GitHub's servers, so when SERPAPI_KEY is set (as it is in the workflow) the data
comes from SerpApi's Google Scholar Author API instead. Without it, the script
scrapes the Scholar profile directly, which works from a normal machine.

Exits non-zero (leaving the existing citations.json untouched) if the request is
blocked or the response looks wrong, so a bad fetch never overwrites good numbers.
"""
import datetime
import html
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request

USER = "vM1SktEAAAAJ"
OUT = pathlib.Path(__file__).resolve().parent.parent / "citations.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def norm(title):
    """Lowercase alphanumerics only, so small punctuation/case differences still match."""
    return re.sub(r"[^a-z0-9]", "", html.unescape(title).lower())


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def from_serpapi(key):
    """Returns (citations, h_index, i10_index, [(title, cites), ...])."""
    params = {"engine": "google_scholar_author", "author_id": USER, "hl": "en", "num": 100, "api_key": key}
    data = json.loads(get("https://serpapi.com/search.json?" + urllib.parse.urlencode(params)))
    if "error" in data:
        sys.exit(f"SerpApi error: {data['error'].rstrip('.')}. Keeping old data.")
    # cited_by.table looks like [{"citations": {"all": N, ...}}, {"h_index": {...}}, {"i10_index": {...}}]
    table = {k: v for row in data.get("cited_by", {}).get("table", []) for k, v in row.items()}
    try:
        stats = (table["citations"]["all"], table["h_index"]["all"], table["i10_index"]["all"])
    except KeyError:
        sys.exit(f"Unexpected SerpApi response (keys: {sorted(data)}). Keeping old data.")
    articles = [(a["title"], (a.get("cited_by") or {}).get("value") or 0) for a in data.get("articles", []) if a.get("title")]
    return (*stats, articles)


def from_scholar():
    """Returns (citations, h_index, i10_index, [(title, cites), ...])."""
    page = get(f"https://scholar.google.com/citations?user={USER}&hl=en&cstart=0&pagesize=100")
    # stats table: citations (all, since), h-index (all, since), i10-index (all, since)
    stats = [int(n) for n in re.findall(r'class="gsc_rsb_std">(\d+)<', page)]
    if len(stats) < 6:
        sys.exit(f"Unexpected Scholar response (stats={len(stats)}); possibly blocked. Keeping old data.")
    articles = []
    for row in re.findall(r'<tr class="gsc_a_tr">(.*?)</tr>', page, re.S):
        title = re.search(r'class="gsc_a_at">(.*?)</a>', row, re.S)
        cites = re.search(r'class="gsc_a_ac[^"]*">(\d*)</a>', row)
        if title:
            articles.append((title.group(1), int(cites.group(1)) if cites and cites.group(1) else 0))
    return stats[0], stats[2], stats[4], articles


def main():
    key = os.environ.get("SERPAPI_KEY")
    citations, h_index, i10_index, articles = from_serpapi(key) if key else from_scholar()
    if len(articles) < 10 or not citations:
        sys.exit(f"Too few results (citations={citations}, articles={len(articles)}). Keeping old data.")

    papers = {}
    for title, cites in articles:
        # the same title can appear twice (e.g. arXiv + conference version); keep the larger count
        k = norm(title)
        papers[k] = max(papers.get(k, 0), int(cites))

    data = {
        "updated": datetime.date.today().isoformat(),
        "citations": int(citations),
        "h_index": int(h_index),
        "i10_index": int(i10_index),
        "papers": papers,
    }
    OUT.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    print(f"Wrote {OUT.name} via {'SerpApi' if key else 'Scholar'}: "
          f"{citations} citations, h={h_index}, i10={i10_index}, {len(papers)} papers")


if __name__ == "__main__":
    main()
