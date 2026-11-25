#!/usr/bin/env python3
"""Tell Bing (and every other IndexNow engine) which pages changed, so they crawl them today
instead of whenever they next read the sitemap. Google does not take IndexNow; it reads sitemap.xml.

Usage: python3 scripts/indexnow.py                 today's pages: every sitemap entry dated today, plus the hubs
       python3 scripts/indexnow.py URL_OR_PATH ...  just these (a card fixed from the inbox: /hall-of-fame/<handle>/<slug>/)
       python3 scripts/indexnow.py --all           the whole sitemap, once, after a big change to the template
       python3 scripts/indexnow.py --dry           print what it would send

The daily /spite run calls it after the push, once the day's pages answer 200, because the
engines fetch what they are told about straight away. A page they fetch before GitHub Pages
serves it is a 404 to them.

The key is the file <KEY>.txt at the site root: it is public by design (it proves the ping comes
from whoever controls spiteware.ai), so it is committed, and KEY below must match its name.
A refused or failed ping is a report, never a failure: the sitemap still gets there.
"""
import datetime, json, pathlib, re, sys, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://spiteware.ai"
KEY = "91f2cc1dd2c14e25424dd0f9c600d596"
HUBS = ["/", "/apps.html", "/hall-of-fame/", "/wall-of-shame/", "/free/"]   # change whenever an app is listed


def sitemap():
    """[(url, lastmod or "")] from sitemap.xml."""
    xml = (ROOT / "sitemap.xml").read_text()
    return re.findall(r"<loc>([^<]+)</loc>(?:<lastmod>([^<]+)</lastmod>)?", xml)


def today():
    """Every page dated today in the sitemap (the new apps, and each list or product page they joined),
    plus the hubs, but only on a day that listed something."""
    day = datetime.date.today().isoformat()
    fresh = [u for u, d in sitemap() if d == day]
    return fresh + [SITE + h for h in HUBS] if fresh else []


def ping(urls):
    """POST the list to api.indexnow.org, which shares it with Bing, Yandex, Seznam, Naver and the rest."""
    body = json.dumps({"host": "spiteware.ai", "key": KEY, "keyLocation": f"{SITE}/{KEY}.txt",
                       "urlList": urls}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "spiteware-indexnow"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:200]
    except OSError as e:
        return 0, str(e)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not (ROOT / f"{KEY}.txt").exists():
        sys.exit(f"indexnow: {KEY}.txt is missing from the site root; the engines would refuse the ping")
    if "--all" in sys.argv:
        urls = [u for u, _ in sitemap()]
    elif args:
        urls = [a if a.startswith("http") else SITE + "/" + a.lstrip("/") for a in args]
    else:
        urls = today()
    urls = list(dict.fromkeys(u for u in urls if u.startswith(SITE + "/")))
    if not urls:
        print("indexnow: nothing changed today, nothing sent"); sys.exit(0)
    if "--dry" in sys.argv:
        print("\n".join(urls)); print(f"indexnow: would send {len(urls)}"); sys.exit(0)
    sent = 0
    for i in range(0, len(urls), 10000):   # the protocol's cap per request
        code, why = ping(urls[i:i + 10000])
        if code in (200, 202):
            sent += len(urls[i:i + 10000])
        else:
            print(f"indexnow: refused ({code or 'no answer'}) {why}".rstrip())
    print(f"indexnow: {sent} of {len(urls)} urls sent")
