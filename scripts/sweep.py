#!/usr/bin/env python3
"""Sweep tier-1 sources for spiteware candidates. No keys needed.

Usage: python3 scripts/sweep.py [--hours 48] [--out queue/raw-YYYY-MM-DD.json]
Prints a JSON list of raw hits, deduped against data/apps.json and data/rejected.json.
"""
import json, re, sys, time, collections, urllib.parse, urllib.request, urllib.error, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = "spiteware.ai morning sweep (https://github.com/alkait/spiteware.ai)"
SUBS = ["SideProject", "selfhosted", "opensource", "webdev", "macapps", "vibecoding", "ClaudeAI", "indiehackers"]

# A hint, not a gate. Show HN comes in whole (see hn() below) and this only ranks it;
# on Reddit and GitHub it is still the filter, so it errs wide. Measured against the
# grudge quotes already listed it recognises 40 of 41 — the one it misses ("I wanted a
# version of Nomad List that was free") is the reminder that the agent reading the post
# is the real detector, and everything here exists to get posts in front of it.
GRUDGE_RE = re.compile(r"""
  free\ alternative | open.source\ alternative | self.hosted\ alternative | free\ forever
| tired\ of\ paying | sick\ of\ paying | refus\w+\ to\ pay | (don'?t|didn'?t|won'?t|wouldn'?t|not)\ (want\ to\ )?pay
| instead\ of\ paying | without\ paying | why\ pay | worth\ paying | ask(s|ed)?\ (you\ )?to\ pay
| wanna\ pay | pay(ing)?\ (for|monthly|yearly|a\ (lot|bunch)) | pay\ \$
| subscription | paywall\w* | freemium | free\ (tier|plan|version) | paid\ (tier|plan|version|app)
| pro\ (plan|tier|version) | upgrade\ to\ pro | premium\ (plan|tier|version)
| paid\ (service|tool|product|software|option)
| went\ paid | now\ charges | charge[sd]?\ \$ | price\ (hike|increase) | rais\w+\ (the|their)\ price
| per.(user|seat|month) | seat.based | add.on\ pricing | contact\ sales | pricing\ page
| cost[s]?\ money | costs?\ a\ fortune | expensive | overpriced | prohibitively
| in.app\ purchase | lifetime\ deal | free\ trial | too\ limited | limited\ free
| (with|without|full\ of|no)\ (ads|adverts|advertising)
| enshittifi\w+ | rug\ ?pull
| vibe.?coded | weekend
| \$\d[\d.,]*\s*(/|per\ )\s*(mo|month|yr|year|user|seat)
""", re.I | re.X)

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

def hn(since, pages=8, per=200):
    """Every Show HN in the window, not just the ones that used our words.

    Keyword queries here were costing recall: a Show HN whose grudge reads
    "prohibitively expensive" or "they added paid tiers" matched none of them and was
    never seen. Show HN is small enough to take whole (a few hundred per 48h), so we
    take it whole and let the agent triage. `matched` carries the regex hit when there
    is one, purely so the likely ones sort to the top.
    """
    out = {}
    for page in range(pages):
        url = (f"https://hn.algolia.com/api/v1/search_by_date?tags=show_hn"
               f"&numericFilters=created_at_i%3E{since}&hitsPerPage={per}&page={page}")
        try:
            r = get(url)
        except Exception as e:
            print(f"hn page {page}: {e}", file=sys.stderr); break
        hits = r.get("hits", [])
        for h in hits:
            body = h.get("story_text") or ""
            m = GRUDGE_RE.search(f"{h.get('title') or ''} {body}")
            out[h["objectID"]] = {
                "source": "hn", "id": h["objectID"], "title": h.get("title"), "url": h.get("url"),
                "author": h.get("author"), "points": h.get("points") or 0,
                # untagged posts still get read, but they don't need to cost a page of context
                "text": body[:1500 if m else 400], "posted": h.get("created_at"),
                "discussion": f"https://news.ycombinator.com/item?id={h['objectID']}",
                "matched": m.group(0).strip() if m else None,
            }
        if not hits or page + 1 >= r.get("nbPages", 0): break
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
            # reddit 429s hard and often; a rate-limited sub looks exactly like a quiet
            # one, so back off and retry rather than silently reading nothing all morning
            for attempt in range(3):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": BUA})
                    with urllib.request.urlopen(req, timeout=20) as r: root = ET.fromstring(r.read())
                    break
                except urllib.error.HTTPError as e:
                    if e.code != 429 or attempt == 2: raise
                    time.sleep(12 * (attempt + 1))
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
    # GitHub search needs a term to search for, so this path stays keyword-bound.
    for p in ["free alternative to", "no subscription", "tired of paying", "instead of paying",
              "without paying", "free forever", "expensive", "paid alternative"]:
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
    fresh.sort(key=lambda h: (h.get("matched") is None, -(h.get("points") or 0)))
    payload = {"swept_at": datetime.datetime.now(datetime.UTC).isoformat(), "hours": hours, "count": len(fresh), "hits": fresh}
    text = json.dumps(payload, indent=1, ensure_ascii=False)
    if out:
        pathlib.Path(out).write_text(text)
        by = collections.Counter(h["source"] for h in fresh)
        hint = sum(1 for h in fresh if h.get("matched"))
        print(f"{len(fresh)} hits ({hint} keyword-hinted) -> {out}", file=sys.stderr)
        print("  " + "  ".join(f"{k}={v}" for k, v in by.most_common()), file=sys.stderr)
    else:
        print(text)

if __name__ == "__main__":
    main()
