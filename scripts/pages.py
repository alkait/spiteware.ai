#!/usr/bin/env python3
"""Generate the hall of fame from data/apps.json. No deps.

Usage: python3 scripts/pages.py

Writes hall-of-fame/<author>/<app>/index.html for every app, a page per author, the
index of inductees, the wall of shame (wall-of-shame/, a leaderboard of the paid products
by how many times they've been replaced, and a page per product), sitemap.xml, robots.txt and 404.html (GitHub Pages serves that one
for any address that isn't a file, at any depth, hence the root-relative paths). These are real files rather than
something site.js renders, because link previews and most crawlers don't run JS.

hall-of-fame/ and wall-of-shame/ are wiped and rebuilt on every run, so never edit anything in them by hand.
scripts/merge.py runs this after an approve; run it yourself after hand-editing
data/apps.json.

An app with "status": "dead" (scripts/links.py --bury) is off every list and out of the
sitemap, but keeps its page, stamped, so a link someone shared never 404s. Any link in
an app's `dead_links` points at its Wayback snapshot, or isn't a link any more.

Every build ends with the internal link check from scripts/links.py and fails on a miss.
"""
import json, re, html, shutil, pathlib, urllib.parse, importlib.util

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "hall-of-fame"
SHAME = ROOT / "wall-of-shame"
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

def alive(a): return a.get("status") != "dead"

def out(a, field, url):
    """Where an outbound link points today: the URL itself, the Wayback snapshot that
    links.py --bury found for it, or None when it died without leaving a copy."""
    dl = a.get("dead_links") or {}
    return (dl[field] or None) if field in dl else url

def victim(a):
    """Mirrors SW.victim in site.js."""
    r = a.get("replaces") or {}
    n, p = (r.get("name") or "").strip(), (r.get("price") or "").strip()
    return f"{n} · {p}" if n and p else n if n else f"a paywall · {p}" if p else "a paywall"

def product(a):
    """The paid product a card is aimed at, plan stripped (replaces.product). Empty when the builder named none."""
    return ((a.get("replaces") or {}).get("product") or "").strip()

def shame(name):
    """URL of a product's wall of shame page."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not SAFE.fullmatch(s): raise SystemExit(f"product {name!r} makes no URL")
    return f"/wall-of-shame/{s}/"

def victims(apps):
    """[(product, its apps)]: most replaced first, then the pettiest replacement, then a to z."""
    by = {}
    for a in apps:
        if product(a): by.setdefault(product(a), []).append(a)
    return sorted(by.items(), key=lambda kv: (-len(kv[1]), -max(x["spite_score"] for x in kv[1]), kv[0].lower()))

def bill(theirs):
    """The price on a product's head: the one most of its cards cite, the pettiest card breaking ties."""
    prices = [(a["replaces"].get("price") or "").strip().split(" (")[0] for a in theirs]
    prices = [x for x in prices if x]
    return max(dict.fromkeys(prices), key=lambda x: (prices.count(x), -prices.index(x))) if prices else ""

def times(n): return "once" if n == 1 else "twice" if n == 2 else f"{n} times"

def order(apps):
    """Pettiest first, then newest, then a to z. Three stable sorts, least important first."""
    apps = sorted(apps, key=lambda a: a["name"].lower())
    apps.sort(key=lambda a: a["added"], reverse=True)
    return sorted(apps, key=lambda a: -a["spite_score"])

def avatar(a, px):
    """The builder's face, or an initial tile when there is no GitHub account to ask.
    site.js swaps a broken image for the same tile (img[data-who])."""
    who = gh(a)
    if who and out(a, "face", who):
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


# Google Analytics, first thing in every head. index, apps, about, manifesto, rules, submit, contact and privacy carry the same snippet by hand.
GTAG = '''<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XSP99C36LS"></script>
<script>
  // local previews and anything else off the real domain send nothing
  if (location.hostname !== 'spiteware.ai') window['ga-disable-G-XSP99C36LS'] = true;
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-XSP99C36LS');
</script>'''


def shell(*, title, desc, path, body, n, og_title=None, og_desc=None, ld=(), index=True, here="/hall-of-fame/"):
    url = SITE + path
    # "</" inside JSON would let a tagline close the script tag early
    lds = "".join('<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False).replace("</", "<\\/") + "</script>\n" for x in ld)
    return f'''<!doctype html>
<!-- generated by scripts/pages.py from data/apps.json. Edit the script, not this file. -->
<html lang="en">
<head>
{GTAG}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">{"" if index else f"""
<meta name="robots" content="noindex,follow">"""}
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
        <li><a href="/hall-of-fame/"{' aria-current="page"' if here == "/hall-of-fame/" else ""}>Hall of fame</a></li>
        <li><a href="/wall-of-shame/"{' aria-current="page"' if here == "/wall-of-shame/" else ""}>Wall of shame</a></li>
        <li><a href="/about.html">About</a></li>
        <li><a href="/submit.html">Submit</a></li>
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
        <p style="margin-top:20px"><a class="btn" href="/submit.html">Submit your spiteware →</a> &nbsp; <a class="btn btn--pink" href="/apps.html">See all {n} grudges</a></p>
      </div>
    </div>
  </section>
</main>

<footer>
  <div class="wrap foot">
    <div class="foot__l">
      <a class="counter" href="/analytics.html" title="Visits since launch. Click for the rest of the numbers.">
        <div class="odo" id="odo" aria-live="polite" aria-label="visitor counter"></div>
        <div class="counter__l">visits<br>since launch<br>and counting</div>
      </a>
      <nav class="badges" aria-label="Footer">
        <a class="badge" href="/privacy.html">privacy</a>
        <a class="badge badge--blue" href="/contact.html">contact</a>
        <a class="badge badge--pink ico ico--gh" href="https://github.com/alkait/spiteware.ai" target="_blank" rel="noopener">source</a>
        <a class="badge badge--green ico ico--yt" href="https://www.youtube.com/@spiteware" target="_blank" rel="noopener">youtube</a>
      </nav>
    </div>
    <div class="maker">
      <a class="gcard__pic" href="https://github.com/alkait" target="_blank" rel="noopener"><img class="gcard__av" src="/alkait.jpg" alt="alkait" width="150" height="150"></a>
      <span>this site was shamelessly vibe coded by <a href="https://github.com/alkait" target="_blank" rel="noopener">@alkait</a></span>
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
    path, who, dead = fame(a), gh(a), not alive(a)
    title = (f"{a['name']}: free alternative to {vname}" + (f" ({price})" if price else "") if vname
             else f"{a['name']}: built out of spite, free forever") + " · spiteware.ai"
    desc = f"{a['tagline']} Built by {b['name']} out of spite" + (f", instead of paying {vname}." if vname else ".")
    if dead:
        title = f"{a['name']} (taken down) · spiteware.ai hall of fame"
        desc = f"{a['name']} has been taken down since we listed it. The grudge stands. " + desc
    quote = re.sub(r"([$€£]\d[\d,]*(?:\.\d+)?(?:\s*/\s*\w+)?)", r"<em>\1</em>", esc(a["grudge"]["quote"]), count=1)
    qsize = "s" if len(a["grudge"]["quote"]) > 210 else "m" if len(a["grudge"]["quote"]) > 100 else "l"
    src = urllib.parse.urlparse(a["grudge"]["source"]).netloc.removeprefix("www.")

    # The face links to GitHub when that's where it came from, else wherever the builder lives.
    href = f"https://github.com/{who}" if who else b.get("url") if (b.get("url") or "").startswith("http") else ""
    href = out(a, "face", href) or ""
    at = f'<span class="gcard__at">@{esc(who or b["handle"])}</span>'
    pic = (f'<a class="gcard__pic" href="{esc(href)}" target="_blank" rel="noopener">{avatar(a, 200)}{at}</a>' if href
           else f'<span class="gcard__pic">{avatar(a, 200)}{at}</span>')

    share = urllib.parse.urlencode({"text": f"{a['name']} by {b['name']} made the spiteware.ai hall of fame."
                                            + (f" Replaces {vname}." if vname else ""), "url": SITE + path})
    # Outbound links go through out(): a dead one points at its snapshot, or stops being a link.
    repo_url = out(a, "repo", f'https://github.com/{a["repo"]}') if a.get("repo") else None
    repo = (f'<a class="btn btn--ghost" href="{esc(repo_url)}" target="_blank" rel="noopener">'
            f'{"Source on GitHub" if "repo" not in (a.get("dead_links") or {}) else "Archived source"}</a>' if repo_url else "")
    get_url, cite_url = out(a, "url", a["url"]), out(a, "grudge", a["grudge"]["source"])
    get = (f'<a class="btn btn--pink" href="{esc(get_url)}" target="_blank" rel="noopener">Get {esc(a["name"])} →</a>' if not dead
           else f'<a class="btn btn--ghost" href="{esc(get_url)}" target="_blank" rel="noopener">See the archived copy →</a>' if get_url else "")
    cite = (f'on {esc(src)} (no longer online)' if not cite_url
            else f'<a href="{esc(cite_url)}" target="_blank" rel="noopener">on {esc(src)}{"" if cite_url == a["grudge"]["source"] else ", archived"} ↗</a>')
    rip = (f'<span class="sticker sticker--dead">taken down{" · " + month(a.get("died")) if month(a.get("died")) else ""}</span>' if dead else "")
    gone = (f'<p class="fcard__rip">{esc(a["name"])} has been taken down since it was inducted. The grudge outlived the app.</p>' if dead else "")
    more = "".join(card(x) for x in related(a, apps))
    # the product page exists only while a living app names the product; a dead app's page must not point at nothing
    shamed = product(a) and any(product(x) == product(a) for x in apps)

    body = f'''  <section class="fame">
    <div class="wrap">
      <article class="fcard{" fcard--dead" if dead else ""}">
        <a class="deck__label" href="/hall-of-fame/">Hall of fame</a>{rip}
        <div class="fcard__who">
          {pic}
          <div class="fcard__name">{esc(b["name"])}</div>
          <dl class="fcard__facts">
            <div><dt>inducted</dt><dd>{month(a["added"])} · for spite</dd></div>
            <div><dt>spite score</dt><dd>🔥 {a["spite_score"]}/10</dd></div>{f"""
            <div class="fact--stack"><dt>free alternative to</dt><dd>{esc(product(a) or vname)}</dd></div>""" if vname else ""}
          </dl>
        </div>
        <div class="fcard__main">
          <blockquote class="fcard__q fcard__q--{qsize}">
            <p>“{quote}”</p>
            <cite>{esc(b["name"])}, {cite}</cite>
          </blockquote>
          <div class="fcard__app">
            <div class="card__icon">{esc(a.get("icon") or "🔧")}</div>
            <div class="fcard__what"><h1>{esc(a["name"])}</h1><p>{esc(a["tagline"])}</p></div>
            <div class="kills kills--xl">replaces<s>{esc(victim(a))}</s></div>
          </div>
          <div class="chips">{chips(a)}</div>
          {gone}{f"""<div class="cta">
            {get}
            {repo}
          </div>""" if get or repo else ""}
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
        <div class="sec__sub">{f'<a href="{shame(product(a))}">{esc(product(a))} on the wall of shame →</a> · ' if shamed else ""}<a href="/hall-of-fame/">all {n} inductees →</a></div>
      </div>
      <div class="grid">{more}</div>
    </div>
  </section>
'''
    tags = a.get("tags") or []
    app_ld = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": a["name"],
              "description": a["tagline"], **({"url": get_url} if get_url else {}), "isAccessibleForFree": True,
              "applicationCategory": next((CATEGORY[t] for t in tags if t in CATEGORY), "UtilitiesApplication"),
              "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
              "author": {"@type": "Person", "name": b["name"], **({"url": href} if href else {})}}
    if any(t in OS for t in tags): app_ld["operatingSystem"] = ", ".join(dict.fromkeys(OS[t] for t in tags if t in OS))
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "spiteware.ai", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": "Hall of fame", "item": SITE + "/hall-of-fame/"},
        {"@type": "ListItem", "position": 3, "name": a["name"], "item": SITE + path}]}
    return shell(title=title, desc=desc, path=path, body=body, n=n, ld=(app_ld, crumbs), index=not dead,
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


def shame_index(ranked, n):
    hits = sum(len(t) for _, t in ranked)
    def row(i, name, theirs):
        price = bill(theirs)
        return (f'<a class="shame__row" href="{shame(name)}"><span class="shame__rank">{i + 1:02d}</span>'
                f'<span class="shame__who"><b>{esc(name)}</b>replaced {times(len(theirs))}</span>'
                + (f'<span class="kills">wants<s>{esc(price)}</s></span>' if price else '<span class="kills">wants<s>a paywall</s></span>') + '</a>')
    body = f'''  <section class="hero">
    <div class="wrap">
      <span class="kicker">{len(ranked)} paid products · replaced {hits} times</span>
      <h1>Wall of <span class="hl">shame.</span></h1>
      <p class="lede">The paid tools people were annoyed enough to rebuild for free, ranked by how many people did it. The more the price asks, the longer the line. <b>Most replaced first.</b></p>
    </div>
  </section>
  <section class="sec sec--alt">
    <div class="wrap"><div class="shame">{"".join(row(i, name, theirs) for i, (name, theirs) in enumerate(ranked))}</div></div>
  </section>
'''
    ld = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": SITE + shame(name), "name": name} for i, (name, _) in enumerate(ranked)]}
    return shell(title="Wall of shame: the paid tools people rebuilt for free · spiteware.ai", path="/wall-of-shame/",
                 desc=f"{len(ranked)} paid products, ranked by how many people looked at the price and built the free version instead.",
                 body=body, n=n, ld=(ld,), here="/wall-of-shame/")


def shame_page(rank, total, name, theirs, n):
    theirs, path, price = order(theirs), shame(name), bill(theirs)
    k = len(theirs)
    title = f"Free alternatives to {name}" + (f" ({price})" if price else "") + f": {k} {'app' if k == 1 else 'apps'} built out of spite · spiteware.ai"
    desc = (f"{name} has been replaced {times(k)} by people who read the pricing page and built the free version: "
            + ", ".join(a["name"] for a in theirs) + ". Every one is free, and every grudge is quoted from the person who built it.")
    body = f'''  <section class="hero">
    <div class="wrap">
      <span class="kicker"><a href="/wall-of-shame/">Wall of shame</a> · #{rank} of {total}</span>
      <h1>{esc(name)}</h1>
      <div class="kills kills--xl">wants<s>{esc(price) if price else "a paywall"}</s></div>
      <p class="lede">{k if k > 1 else "One"} free {"alternatives" if k > 1 else "alternative"} to {esc(name)}, built out of spite. {"Each" if k > 1 else "It"} does the job for <b>$0</b>.{" Pettiest first." if k > 1 else ""}</p>
    </div>
  </section>
  <section class="sec sec--alt">
    <div class="wrap"><div class="grid grid--center">{"".join(card(a) for a in theirs)}</div></div>
  </section>
'''
    ld = {"@context": "https://schema.org", "@type": "ItemList", "name": f"Free alternatives to {name}", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": SITE + fame(a), "name": a["name"]} for i, a in enumerate(theirs)]}
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "spiteware.ai", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": "Wall of shame", "item": SITE + "/wall-of-shame/"},
        {"@type": "ListItem", "position": 3, "name": name, "item": SITE + path}]}
    return shell(title=title, desc=desc, path=path, body=body, n=n, ld=(ld, crumbs), here="/wall-of-shame/",
                 og_title=f"{name}: replaced {times(k)}, for free · spiteware.ai wall of shame")


def lost_page(n):
    body = f'''  <section class="hero">
    <div class="wrap">
      <span class="kicker">you've hit a 404</span>
      <h1>This page doesn't <span class="hl">exist.</span></h1>
      <p class="lede">There's nothing at this address. The apps are all still here, and they still cost <b>$0</b>.</p>
      <div class="cta"><a class="btn btn--pink" href="/apps.html">See all {n} grudges →</a> <a class="btn btn--ghost" href="/hall-of-fame/">Hall of fame</a> <a class="btn btn--ghost" href="/">Home</a></div>
    </div>
  </section>
'''
    return shell(title="404: this page doesn't exist · spiteware.ai", path="/404.html", body=body, n=n, index=False, here="",
                 desc="There's nothing at this address. The apps are all still here, and they still cost $0.")


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
    for d in (OUT, SHAME):
        if d.exists(): shutil.rmtree(d)

    # Every list, count and sitemap entry is the living only. The dead keep their page and nothing else.
    live, dead = [a for a in apps if alive(a)], [a for a in apps if not alive(a)]
    by = {}
    for a in apps: by.setdefault(author(a), []).append(a)
    urls = [("/", None), ("/apps.html", None), ("/hall-of-fame/", None), ("/wall-of-shame/", None), ("/about.html", None), ("/manifesto.html", None), ("/rules.html", None), ("/submit.html", None), ("/contact.html", None), ("/privacy.html", None)]
    for i, a in enumerate(live):
        write(ROOT / fame(a).strip("/") / "index.html", app_page(a, live, live[(i + 1) % len(live)]))
        urls.append((fame(a), a["added"]))
    for a in dead:
        write(ROOT / fame(a).strip("/") / "index.html", app_page(a, live, live[0]))
    for handle, theirs in by.items():
        standing = [a for a in theirs if alive(a)]
        solo = len(standing) < 2
        write(OUT / handle / "index.html", author_stub((standing or theirs)[0]) if solo else author_page(handle, standing, len(live)))
        if not solo: urls.append((f"/hall-of-fame/{handle}/", None))
    write(OUT / "index.html", index_page(live))
    ranked = victims(live)
    seen = {}
    for i, (name, theirs) in enumerate(ranked):
        if shame(name) in seen: raise SystemExit(f"products {name!r} and {seen[shame(name)]!r} both want {shame(name)}")
        seen[shame(name)] = name
        write(ROOT / shame(name).strip("/") / "index.html", shame_page(i + 1, len(ranked), name, theirs, len(live)))
        urls.append((shame(name), max(a["added"] for a in theirs)))
    write(SHAME / "index.html", shame_index(ranked, len(live)))
    write(ROOT / "404.html", lost_page(len(live)))

    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{SITE}{p}</loc>{f'<lastmod>{d}</lastmod>' if d else ''}</url>\n" for p, d in urls)
        + "</urlset>\n")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")

    spec = importlib.util.spec_from_file_location("links", ROOT / "scripts/links.py")
    L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)
    broken, _ = L.internal()
    if broken: raise SystemExit(f"{len(broken)} broken internal links:\n" + "\n".join(f"  {ref}  <- {where}" for where, ref in broken[:20])
                                + ("\n  ... python3 scripts/links.py lists them all" if len(broken) > 20 else ""))
    return {"apps": len(live), "dead": len(dead), "authors": len(by), "products": len(ranked), "urls": len(urls)}

if __name__ == "__main__":
    r = build()
    print(f"hall of fame: {r['apps']} app pages (+{r['dead']} taken down), {r['authors']} author pages, "
          f"wall of shame: {r['products']} products, {r['urls']} urls in sitemap.xml, internal links ok")
