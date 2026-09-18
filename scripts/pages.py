#!/usr/bin/env python3
"""Generate the hall of fame from data/apps.json. No deps.

Usage: python3 scripts/pages.py

Writes hall-of-fame/<author>/<app>/index.html for every app, a page per author, the
index of inductees, sitemap.xml and robots.txt. These are real files rather than
something site.js renders, because link previews and most crawlers don't run JS.

hall-of-fame/ is wiped and rebuilt on every run, so never edit anything in it by hand.
scripts/merge.py runs this after an approve; run it yourself after hand-editing
data/apps.json.
"""
import json, re, html, shutil, pathlib, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "hall-of-fame"
SITE = "https://spiteware.ai"
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
HUES = ["var(--pink)", "var(--yellow)", "var(--blue)", "var(--green)", "var(--orange)", "var(--purple)"]
SAFE = re.compile(r"[a-z0-9][a-z0-9._-]*")
# schema.org wants one of its own category names; the first tag that maps wins.
CATEGORY = {"games": "GameApplication", "finance": "FinanceApplication", "dev-tools": "DeveloperApplication",
            "health": "HealthApplication", "learning": "EducationalApplication", "images": "MultimediaApplication",
            "video": "MultimediaApplication", "productivity": "BusinessApplication", "marketing": "BusinessApplication",
            "travel": "TravelApplication"}
OS = {"macos": "macOS", "ios": "iOS", "windows": "Windows", "web": "Web", "browser-extension": "Web"}


def esc(s): return html.escape(str(s or ""), quote=True)

def month(d): return f"{MON[int(d[5:7]) - 1]} {d[:4]}" if re.match(r"\d{4}-\d{2}-\d{2}", d or "") else ""

def author(a):
    """URL segment for the builder. The handle, not the repo owner: a repo often lives
    under an org, and the page is for the person."""
    s = a["builder"]["handle"].lower()
    if not SAFE.fullmatch(s): raise SystemExit(f"{a['slug']}: builder.handle {s!r} is not URL-safe")
    return s

def fame(a):
    if not SAFE.fullmatch(a["slug"]): raise SystemExit(f"slug {a['slug']!r} is not URL-safe")
    return f"/hall-of-fame/{author(a)}/{a['slug']}/"

def gh(a):
    """GitHub account to take the avatar from. Mirrors SW.gh in site.js: the builder's
    own profile when we have it, else whoever owns the repo."""
    m = re.fullmatch(r"https://github\.com/([^/]+)/?", a["builder"].get("url") or "")
    return m.group(1) if m else (a.get("repo") or "").split("/")[0]

def victim(a):
    """Mirrors SW.victim in site.js."""
    r = a.get("replaces") or {}
    n, p = (r.get("name") or "").strip(), (r.get("price") or "").strip()
    return f"{n} · {p}" if n and p else n if n else f"a paywall · {p}" if p else "a paywall"

def order(apps):
    """Pettiest first, then newest, then a to z. Three stable sorts, least important first."""
    apps = sorted(apps, key=lambda a: a["name"].lower())
    apps.sort(key=lambda a: a["added"], reverse=True)
    return sorted(apps, key=lambda a: -a["spite_score"])

def avatar(a, px):
    """The builder's face, or an initial tile when there is no GitHub account to ask.
    site.js swaps a broken image for the same tile (img[data-who])."""
    who = gh(a)
    if who:
        # only the index is a wall of faces; everywhere else the avatar is above the fold
        lazy = ' loading="lazy"' if px < 100 else ""
        return (f'<img class="gcard__av" src="https://github.com/{esc(who)}.png?size={px * 2}" alt="" '
                f'width="{px}" height="{px}"{lazy} data-who="{esc(who)}">')
    name = a["builder"]["name"] or a["builder"]["handle"]
    return f'<div class="gcard__fb" style="background:{HUES[len(name) % len(HUES)]}">{esc(name[0].upper())}</div>'

def chips(a):
    return ("".join(f'<span class="chip">{esc(t)}</span>' for t in a.get("tags") or [])
            + ('<span class="chip">open-source</span>' if a["open_source"] else "")
            + ('<span class="chip chip--vibe">vibe coded</span>' if a["vibe_coded"] else ""))

def card(a):
    """Mirrors SW.card in site.js. Change one, change the other."""
    return f'''<a class="card" href="{fame(a)}">
    <time class="card__date" datetime="{esc(a["added"])}" title="added to the catalog">{month(a["added"])}</time>
    <div class="card__top"><div class="card__icon">{esc(a.get("icon") or "🔧")}</div>
      <div class="kills">replaces<s>{esc(victim(a))}</s></div></div>
    <h3>{esc(a["name"])}</h3><p>{esc(a["tagline"])}</p>
    <blockquote class="card__grudge">“{esc(a["grudge"]["quote"])}”</blockquote>
    <div class="chips">{chips(a)}</div>
    <div class="card__meta"><span>by {esc(a["builder"]["name"])}</span><span title="spite score">🔥 {a["spite_score"]}/10</span></div></a>'''

def related(a, apps):
    """Three more grudges: same victim first, then the most tags in common."""
    v = (a["replaces"].get("name") or "").strip().lower()
    def score(b):
        same = v and (b["replaces"].get("name") or "").strip().lower() == v
        return (-int(bool(same)), -len(set(a["tags"]) & set(b["tags"])), -b["spite_score"], b["name"])
    return sorted((b for b in apps if b is not a), key=score)[:3]


def shell(*, title, desc, path, body, n, og_title=None, og_desc=None, ld=()):
    url = SITE + path
    # "</" inside JSON would let a tagline close the script tag early
    lds = "".join('<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False).replace("</", "<\\/") + "</script>\n" for x in ld)
    return f'''<!doctype html>
<!-- generated by scripts/pages.py from data/apps.json. Edit the script, not this file. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="spiteware.ai">
<meta property="og:url" content="{esc(url)}">
<meta property="og:title" content="{esc(og_title or title)}">
<meta property="og:description" content="{esc(og_desc or desc)}">
<meta property="og:image" content="{SITE}/og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#FFE600">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="stylesheet" href="/style.css">
{lds}</head>
<body>

<div class="ticker" aria-hidden="true">
  <div class="ticker__track" id="ticker">
    <span>★ <b data-apps>{n}</b> apps listed. all free.</span><span>★ spiteware.ai has made <b>$0.00</b> so far</span><span>★ built by people who read the pricing page and said "no"</span><span>★ cancel your subscriptions. someone already rebuilt the app.</span><span>★ "upgrade to Pro" is not a feature</span><span>★ "seat-based pricing" is a hate crime</span><span>★ vibe coded. spite powered.</span>
  </div>
</div>

<header>
  <div class="wrap nav">
    <a class="logo" href="/" aria-label="spiteware.ai home">
      <span class="logo__stack" aria-hidden="true"><span>SPITE</span><span>WARE</span></span>
      <em aria-hidden="true">.ai</em>
    </a>
    <button class="menu__btn" type="button" id="menubtn" aria-expanded="false" aria-controls="mainnav"><span class="menu__bars" aria-hidden="true"></span>Menu</button>
    <nav aria-label="Main" id="mainnav">
      <ul>
        <li><a href="/">Home</a></li>
        <li><a href="/apps.html">Apps <span class="nav__n" data-apps>{n}</span></a></li>
        <li><a href="/hall-of-fame/" aria-current="page">Hall of fame</a></li>
        <li><a href="/manifesto.html">Manifesto</a></li>
        <li><a href="/rules.html">Rules</a></li>
        <li><a href="/#submit">Submit</a></li>
      </ul>
    </nav>
  </div>
</header>

<main>
{body}
  <section class="sec sec--ink">
    <div class="wrap submit">
      <div>
        <h2>Got a grudge?<br>Ship it.</h2>
        <p>Built something because a company wanted your credit card for a feature that fits in a single file? That's spiteware. Submit it and join the hall of fame.</p>
        <p style="margin-top:20px"><a class="btn" href="/#submit">Submit your spiteware →</a> &nbsp; <a class="btn btn--pink" href="/apps.html">See all {n} grudges</a></p>
      </div>
    </div>
  </section>
</main>

<footer>
  <div class="wrap foot">
    <div class="counter" title="You are visitor number…">
      <div class="odo" id="odo" aria-live="polite" aria-label="visitor counter"></div>
      <div class="counter__l">this counter<br>is fake<br>but it looks great</div>
    </div>
    <div class="foot__meta">
      this site was shamelessly vibe coded by <a href="https://github.com/alkait" target="_blank" rel="noopener">@alkait</a><br>
      no cookies · no tracking · no pricing page · <a href="https://github.com/alkait/spiteware.ai" target="_blank" rel="noopener">source on github</a>
    </div>
    <div class="badges">
      <span class="badge">Best viewed in any browser</span>
      <span class="badge badge--blue">0 bytes of fonts</span>
      <span class="badge badge--pink">Made with rage</span>
      <span class="badge badge--green">Y2K compliant</span>
    </div>
  </div>
</footer>

<script src="/site.js"></script>
</body>
</html>
'''


def app_page(a, apps, nxt):
    b, r, n = a["builder"], a["replaces"], len(apps)
    vname, price = (r.get("name") or "").strip(), (r.get("price") or "").strip().split(" (")[0]
    path, who = fame(a), gh(a)
    title = (f"{a['name']}: free alternative to {vname}" + (f" ({price})" if price else "") if vname
             else f"{a['name']}: built out of spite, free forever") + " · spiteware.ai"
    desc = f"{a['tagline']} Built by {b['name']} out of spite" + (f", instead of paying {vname}." if vname else ".")
    quote = re.sub(r"([$€£]\d[\d,]*(?:\.\d+)?(?:\s*/\s*\w+)?)", r"<em>\1</em>", esc(a["grudge"]["quote"]), count=1)
    qsize = "s" if len(a["grudge"]["quote"]) > 210 else "m" if len(a["grudge"]["quote"]) > 100 else "l"
    src = urllib.parse.urlparse(a["grudge"]["source"]).netloc.removeprefix("www.")

    # The face links to GitHub when that's where it came from, else wherever the builder lives.
    href = f"https://github.com/{who}" if who else b.get("url") if (b.get("url") or "").startswith("http") else ""
    at = f'<span class="gcard__at">@{esc(who or b["handle"])}</span>'
    pic = (f'<a class="gcard__pic" href="{esc(href)}" target="_blank" rel="noopener">{avatar(a, 200)}{at}</a>' if href
           else f'<span class="gcard__pic">{avatar(a, 200)}{at}</span>')

    share = urllib.parse.urlencode({"text": f"{a['name']} by {b['name']} made the spiteware.ai hall of fame."
                                            + (f" Replaces {vname}." if vname else ""), "url": SITE + path})
    repo = (f'<a class="btn btn--ghost" href="https://github.com/{esc(a["repo"])}" target="_blank" rel="noopener">Source on GitHub</a>'
            if a.get("repo") else "")
    more = "".join(card(x) for x in related(a, apps))

    body = f'''  <section class="fame">
    <div class="wrap">
      <article class="fcard">
        <a class="deck__label" href="/hall-of-fame/">Hall of fame</a>
        <div class="fcard__who">
          {pic}
          <div class="fcard__name">{esc(b["name"])}</div>
          <dl class="fcard__facts">
            <div><dt>inducted</dt><dd>{month(a["added"])} · for spite</dd></div>
            <div><dt>spite score</dt><dd>🔥 {a["spite_score"]}/10</dd></div>
          </dl>
        </div>
        <div class="fcard__main">
          <blockquote class="fcard__q fcard__q--{qsize}">
            <p>“{quote}”</p>
            <cite>{esc(b["name"])}, <a href="{esc(a["grudge"]["source"])}" target="_blank" rel="noopener">on {esc(src)} ↗</a></cite>
          </blockquote>
          <div class="fcard__app">
            <div class="card__icon">{esc(a.get("icon") or "🔧")}</div>
            <div class="fcard__what"><h1>{esc(a["name"])}</h1><p>{esc(a["tagline"])}</p></div>
            <div class="kills kills--xl">replaces<s>{esc(victim(a))}</s></div>
          </div>
          <div class="chips">{chips(a)}</div>
          <div class="cta">
            <a class="btn btn--pink" href="{esc(a["url"])}" target="_blank" rel="noopener">Get {esc(a["name"])} →</a>
            {repo}
          </div>
        </div>
      </article>
      <div class="fame__bar">
        <span class="fame__share"><span class="deck__n">show it off</span>
          <button class="deck__next" type="button" data-copy="{esc(SITE + path)}">copy link</button>
          <a class="deck__next" href="https://x.com/intent/post?{esc(share)}" target="_blank" rel="noopener">post on X</a></span>
        <a class="deck__next" href="{fame(nxt)}">next inductee: {esc(nxt["builder"]["name"])} →</a>
      </div>
    </div>
  </section>

  <section class="sec sec--alt">
    <div class="wrap">
      <div class="sec__head">
        <h2>More grudges <span class="tag">same energy</span></h2>
        <div class="sec__sub"><a href="/hall-of-fame/">all {n} inductees →</a></div>
      </div>
      <div class="grid">{more}</div>
    </div>
  </section>
'''
    tags = a.get("tags") or []
    app_ld = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": a["name"],
              "description": a["tagline"], "url": a["url"], "isAccessibleForFree": True,
              "applicationCategory": next((CATEGORY[t] for t in tags if t in CATEGORY), "UtilitiesApplication"),
              "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
              "author": {"@type": "Person", "name": b["name"], **({"url": href} if href else {})}}
    if any(t in OS for t in tags): app_ld["operatingSystem"] = ", ".join(dict.fromkeys(OS[t] for t in tags if t in OS))
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "spiteware.ai", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": "Hall of fame", "item": SITE + "/hall-of-fame/"},
        {"@type": "ListItem", "position": 3, "name": a["name"], "item": SITE + path}]}
    return shell(title=title, desc=desc, path=path, body=body, n=n, ld=(app_ld, crumbs),
                 og_title=f"{a['name']} by {b['name']} · spiteware.ai hall of fame",
                 og_desc=f"“{a['grudge']['quote']}”")


def author_page(handle, theirs, n):
    a = theirs[0]; b = a["builder"]; path = f"/hall-of-fame/{handle}/"
    body = f'''  <section class="hero">
    <div class="wrap fame__author">
      <span class="gcard__pic">{avatar(a, 150)}<span class="gcard__at">@{esc(gh(a) or b["handle"])}</span></span>
      <div>
        <span class="kicker"><a href="/hall-of-fame/">Hall of fame</a> · repeat offender</span>
        <h1>{esc(b["name"])}</h1>
        <p class="lede">{len(theirs)} grudges, {len(theirs)} shipped apps, <b>$0</b> charged.</p>
      </div>
    </div>
  </section>
  <section class="sec sec--alt">
    <div class="wrap"><div class="grid">{"".join(card(x) for x in theirs)}</div></div>
  </section>
'''
    return shell(title=f"{b['name']} · spiteware.ai hall of fame", path=path, body=body, n=n,
                 desc=f"{b['name']} built {', '.join(x['name'] for x in theirs)} out of spite and gave them away for free.")


def author_stub(a):
    """One app, one page: the author URL just forwards, so trimming the address never 404s."""
    url = SITE + fame(a)
    return (f'<!doctype html>\n<!-- generated by scripts/pages.py -->\n<meta charset="utf-8">\n<title>{esc(a["builder"]["name"])} · spiteware.ai</title>\n'
            f'<link rel="canonical" href="{esc(url)}">\n<meta name="robots" content="noindex,follow">\n'
            f'<meta http-equiv="refresh" content="0;url={fame(a)}">\n<a href="{fame(a)}">{esc(a["name"])} →</a>\n')


def index_page(apps):
    n = len(apps)
    def tile(a):
        v = (a["replaces"].get("name") or "").strip()
        return (f'<a class="inductee" href="{fame(a)}">{avatar(a, 64)}<span><b>{esc(a["builder"]["name"])}</b>'
                f'built {esc(a["name"])}' + (f"<s>{esc(v)}</s>" if v else "") + "</span></a>")
    body = f'''  <section class="hero">
    <div class="wrap">
      <span class="kicker">{n} inductees · inducted for spite</span>
      <h1>Hall of <span class="hl">fame.</span></h1>
      <p class="lede">Everyone who read the pricing page, said <b>no</b>, and shipped the thing instead. Pettiest first.</p>
    </div>
  </section>
  <section class="sec sec--alt">
    <div class="wrap"><div class="hall">{"".join(tile(a) for a in apps)}</div></div>
  </section>
'''
    ld = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": SITE + fame(a), "name": a["name"]} for i, a in enumerate(apps)]}
    return shell(title="Hall of fame: the people who built it instead of paying · spiteware.ai", path="/hall-of-fame/",
                 desc=f"{n} builders who got fed up with a paywall and shipped a free replacement. Every grudge, every victim, every price they didn't pay.",
                 body=body, n=n, ld=(ld,))


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)

def build():
    apps = order(json.loads((ROOT / "data/apps.json").read_text()))
    # a builder we only know by handle still gets a name on their page
    for a in apps: a["builder"]["name"] = (a["builder"].get("name") or "").strip() or a["builder"]["handle"]
    seen = {}
    for a in apps:
        if fame(a) in seen: raise SystemExit(f"{a['slug']} and {seen[fame(a)]} both want {fame(a)}")
        seen[fame(a)] = a["slug"]
    if OUT.exists(): shutil.rmtree(OUT)

    by = {}
    for a in apps: by.setdefault(author(a), []).append(a)
    urls = [("/", None), ("/apps.html", None), ("/hall-of-fame/", None), ("/manifesto.html", None), ("/rules.html", None)]
    for i, a in enumerate(apps):
        write(ROOT / fame(a).strip("/") / "index.html", app_page(a, apps, apps[(i + 1) % len(apps)]))
        urls.append((fame(a), a["added"]))
    for handle, theirs in by.items():
        solo = len(theirs) == 1
        write(OUT / handle / "index.html", author_stub(theirs[0]) if solo else author_page(handle, theirs, len(apps)))
        if not solo: urls.append((f"/hall-of-fame/{handle}/", None))
    write(OUT / "index.html", index_page(apps))

    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{SITE}{p}</loc>{f'<lastmod>{d}</lastmod>' if d else ''}</url>\n" for p, d in urls)
        + "</urlset>\n")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
    return {"apps": len(apps), "authors": len(by), "urls": len(urls)}

if __name__ == "__main__":
    r = build()
    print(f"hall of fame: {r['apps']} app pages, {r['authors']} author pages, {r['urls']} urls in sitemap.xml")
