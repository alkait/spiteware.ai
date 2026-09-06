#!/usr/bin/env python3
"""Sweep tier-1 sources for spiteware candidates. No keys needed.

Usage: python3 scripts/sweep.py [--hours 48] [--out queue/raw-YYYY-MM-DD.json]
Prints a JSON list of raw hits, deduped against data/apps.json and data/rejected.json.
"""
import json, re, sys, time, urllib.parse, urllib.request, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = "spiteware.ai morning sweep (https://github.com/alkait/spiteware.ai)"
PHRASES = [
    "free alternative", "open source alternative", "tired of paying", "sick of paying", "refused to pay",
    "no subscription", "paywall", "free tier", "free plan", "went paid", "now charges", "price increase",
    "vibe coded", "built in a weekend", "why pay", "upgrade to pro", "so I built", "so I made",
]
SUBS = ["SideProject", "selfhosted", "opensource", "webdev", "macapps", "vibecoding", "ClaudeAI", "indiehackers"]
GRUDGE_RE = re.compile(r"free alternative|tired of paying|sick of paying|refus\w+ to pay|no subscription|paywall|free tier|free plan|went paid|now charges|vibe.?coded|weekend|why pay|upgrade to pro|subscription|\$\d+/(mo|month|yr|year)", re.I)

def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def known():
    seen = set()
    for f in ("data/apps.json", "data/rejected.json"):
        try:
            for a in json.loads((ROOT / f).read_text()):
                for k in ("slug", "name", "url"):
                    v = a.get(k) if isinstance(a, dict) else a
                    if v: seen.add(str(v).lower().rstrip("/"))
        except Exception: pass
    return seen

def hn(since):
    out = {}
    for p in PHRASES:
        q = urllib.parse.quote(f'"{p}"')
        url = f"https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&query={q}&numericFilters=created_at_i%3E{since}&hitsPerPage=50"
        try:
            for h in get(url).get("hits", []):
                out[h["objectID"]] = {
                    "source": "hn", "id": h["objectID"], "title": h.get("title"), "url": h.get("url"),
                    "author": h.get("author"), "points": h.get("points") or 0,
                    "text": (h.get("story_text") or "")[:1500], "posted": h.get("created_at"),
                    "discussion": f"https://news.ycombinator.com/item?id={h['objectID']}", "matched": p,
                }
        except Exception as e:
            print(f"hn {p!r}: {e}", file=sys.stderr)
        time.sleep(0.3)
    return list(out.values())

def reddit(since):
    import xml.etree.ElementTree as ET, html
    NS = {"a": "http://www.w3.org/2005/Atom"}
    BUA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    out = {}
    for sub in SUBS:
        url = f"https://www.reddit.com/r/{sub}/new.rss?limit=100"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": BUA})
            with urllib.request.urlopen(req, timeout=20) as r: root = ET.fromstring(r.read())
            for e in root.findall("a:entry", NS):
                upd = e.findtext("a:updated", "", NS)
                ts = datetime.datetime.fromisoformat(upd.replace("Z", "+00:00")).timestamp() if upd else 0
                if ts < since: continue
                title = e.findtext("a:title", "", NS)
                content = re.sub(r"<[^>]+>", " ", html.unescape(e.findtext("a:content", "", NS)))
                m = GRUDGE_RE.search(f"{title} {content}")
                if not m: continue
                link = e.find("a:link", NS).get("href")
                ext = re.search(r'href="(https?://(?!www\.reddit\.com|preview\.redd\.it|i\.redd\.it)[^"]+)"', html.unescape(e.findtext("a:content", "", NS)))
                out[link] = {
                    "source": f"r/{sub}", "id": e.findtext("a:id", "", NS), "title": title,
                    "url": ext.group(1) if ext else None, "author": (e.findtext("a:author/a:name", "", NS) or "").lstrip("/u/"),
                    "points": 0, "text": content.strip()[:1500], "posted": upd, "discussion": link, "matched": m.group(0),
                }
        except Exception as e:
            print(f"reddit r/{sub}: {e}", file=sys.stderr)
        time.sleep(4)
    return list(out.values())

def github(since_date):
    out = {}
    for p in ["free alternative to", "no subscription", "tired of paying", "instead of paying", "without paying"]:
        q = urllib.parse.quote(f'"{p}" in:description created:>{since_date}')
        url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=30"
        try:
            for r in get(url).get("items", []):
                if not GRUDGE_RE.search(r.get("description") or ""): continue
                out[r["full_name"]] = {
                    "source": "github", "id": r["full_name"], "title": f"{r['full_name']}: {r.get('description') or ''}",
                    "url": r["html_url"], "author": r["owner"]["login"], "points": r.get("stargazers_count", 0),
                    "text": (r.get("description") or "")[:500], "posted": r.get("created_at"),
                    "discussion": r["html_url"], "matched": p, "license": (r.get("license") or {}).get("spdx_id"),
                }
        except Exception as e:
            print(f"github {p!r}: {e}", file=sys.stderr)
        time.sleep(2)
    return list(out.values())

def main():
    hours = 48; out = None
    a = sys.argv[1:]
    if "--hours" in a: hours = int(a[a.index("--hours") + 1])
    if "--out" in a: out = a[a.index("--out") + 1]
    since = int(time.time()) - hours * 3600
    since_date = datetime.datetime.fromtimestamp(since, datetime.UTC).date().isoformat()
    hits = hn(since) + reddit(since) + github(since_date)
    seen = known()
    fresh = [h for h in hits if not any(k and k in seen for k in [(h.get("url") or "").lower().rstrip("/"), (h.get("title") or "").lower()])]
    fresh.sort(key=lambda h: -(h.get("points") or 0))
    payload = {"swept_at": datetime.datetime.now(datetime.UTC).isoformat(), "hours": hours, "count": len(fresh), "hits": fresh}
    text = json.dumps(payload, indent=1, ensure_ascii=False)
    if out:
        pathlib.Path(out).write_text(text); print(f"{len(fresh)} hits -> {out}", file=sys.stderr)
    else:
        print(text)

if __name__ == "__main__":
    main()
