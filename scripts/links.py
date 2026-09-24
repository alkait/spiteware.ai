#!/usr/bin/env python3
"""Find the links that 404 before a visitor does. No deps.

Usage: python3 scripts/links.py                 internal links only: offline and instant
       python3 scripts/links.py --external [-v] plus every outbound URL in data/apps.json and the static pages
       python3 scripts/links.py --app SLUG      one app's links, right now, no memory
       python3 scripts/links.py --bury SLUG     record what died in data/apps.json and rebuild the pages

Internal is a hard gate: scripts/pages.py runs it after every build and refuses a miss.

External is a report, because the rest of the web is not ours to fix. A link is DEAD
when the host itself says so (the GitHub and Hacker News APIs) or when it has 404ed on
two different days; one bad day is only SUSPECT. Bot walls and timeouts (403, 429, 5xx)
are UNKNOWN and never count against anyone. Exit code is 1 when anything is broken or
dead, so the morning run can't miss it.

--bury is the only thing here that writes to data/apps.json, and only on the user's
word. Each dead link lands in the app's `dead_links` as {field: wayback snapshot or ""}
and pages.py stops linking to the corpse. If the app's own `url` is among them the app
gets "status": "dead": off the home page and the catalog, while its hall of fame page
stays up with a stamp, so a link someone shared never 404s on our side either. Rerun
--bury later to fill in snapshots the Wayback Machine could not serve at the time.
"""
import json, re, sys, socket, shutil, pathlib, datetime, threading, subprocess, importlib.util
import urllib.request, urllib.error, urllib.parse
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS = ROOT / "data/apps.json"
STATE = ROOT / "scripts/.links-state.json"   # git-ignored: which URLs failed, and since when
SITE = "https://spiteware.ai"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0", "Accept": "text/html,*/*"}

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M); return M


# ---------- internal: everything we link to on our own domain is a file on disk

def resolves(ref, page):
    ref = ref.split("#")[0].split("?")[0]
    if not ref: return True
    p = ROOT / ref.lstrip("/") if ref.startswith("/") else page.parent / ref
    return (p / "index.html").exists() if p.is_dir() else p.exists()

def internal():
    """[(where, ref)] for every local href, src, sitemap entry and card link that points at nothing."""
    bad, n = [], 0
    for page in [*ROOT.glob("*.html"), *ROOT.glob("hall-of-fame/**/*.html"), *ROOT.glob("wall-of-shame/**/*.html")]:
        text = page.read_text()
        refs = re.findall(r'(?:href|src)="([^"]+)"', text) + re.findall(r'http-equiv="refresh" content="\d+;url=([^"]+)"', text)
        for ref in refs:
            if re.match(r"[a-z][a-z0-9+.-]*:|//|\$\{", ref): continue   # outbound, mailto:, or a JS template
            n += 1
            if not resolves(ref, page): bad.append((str(page.relative_to(ROOT)), ref))
    for loc in re.findall(r"<loc>([^<]+)</loc>", (ROOT / "sitemap.xml").read_text()):
        n += 1
        if not resolves(loc.removeprefix(SITE), ROOT / "sitemap.xml"): bad.append(("sitemap.xml", loc))
    # site.js builds card links at runtime, so nothing above sees them
    P = load("pages")
    for a in json.loads(APPS.read_text()):
        n += 1
        if not resolves(P.fame(a), ROOT / "site.js"): bad.append((f"card for {a['slug']}", P.fame(a)))
    if not (ROOT / "404.html").exists(): bad.append(("GitHub Pages", "/404.html"))
    return bad, n


# ---------- external: one URL in, (state, detail, sure) out
# state is ok, dead, unknown or moved. sure means the host said so itself, no second opinion needed.

def fetch(url, method="GET", timeout=15):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA, method=method), timeout=timeout)

def api(url, timeout):
    try:
        with fetch(url, timeout=timeout) as r: return True, json.loads(r.read() or b"null")
    except Exception:
        return False, None

def github(path, timeout):
    """Ask the API, not the website: no rate limit to speak of, and it knows a rename
    from a deletion. None means gh can't help and plain HTTP should have a go."""
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts or not shutil.which("gh"): return None
    what = f"repos/{parts[0]}/{parts[1].removesuffix('.git')}" if len(parts) > 1 else f"users/{parts[0]}"
    try:
        p = subprocess.run(("gh", "api", what, "--jq", '(.full_name // .login) + " " + ((.private // false) | tostring)'),
                           capture_output=True, text=True, timeout=timeout + 10)
    except subprocess.TimeoutExpired:
        return None
    if p.returncode:
        return ("dead", "github: not found", True) if "HTTP 404" in p.stderr else None
    now, private = p.stdout.split()
    if private == "true": return "dead", "github: repo went private", True
    was = "/".join(parts[:2]) if len(parts) > 1 else parts[0]
    return ("ok", "", True) if now.lower() == was.removesuffix(".git").lower() else ("moved", f"renamed to {now}", True)

def hackernews(u, timeout):
    id_ = urllib.parse.parse_qs(u.query).get("id", [""])[0]
    kind = {"/item": "item", "/user": "user"}.get(u.path)
    if not (kind and id_): return None
    ok, d = api(f"https://hacker-news.firebaseio.com/v0/{kind}/{urllib.parse.quote(id_)}.json", timeout)
    if not ok: return None
    if d is None: return "dead", f"hn: no such {kind}", True
    # a [dead] post still answers 200, but the public page is an empty shell: the quote we cite is gone
    return ("dead", "hn: deleted or [dead], the text is no longer public", True) if d.get("deleted") or d.get("dead") else ("ok", "", True)

def appstore(u, timeout):
    """apps.apple.com 429s anything that isn't a browser; the lookup API answers. It is
    per-storefront, so an empty answer is only evidence when the URL names the country."""
    m = re.search(r"/id(\d+)", u.path)
    if not m: return None
    cc = re.match(r"/([a-z]{2})/", u.path)
    ok, d = api(f"https://itunes.apple.com/lookup?id={m.group(1)}&country={cc.group(1) if cc else 'us'}", timeout)
    if not ok: return None
    if d.get("resultCount"): return "ok", "", True
    return ("dead", "app store: not in this storefront", False) if cc else ("unknown", "app store: not in the US storefront", False)

def same(a, b):
    k = lambda s: re.sub(r"^https?://(www\.)?", "", s.split("#")[0]).rstrip("/").lower()
    return k(a) == k(b)

def online():
    """A laptop with no network can't resolve anything, and that is not 287 dead links."""
    try: socket.getaddrinfo("github.com", 443); return True
    except OSError: return False

def http(url, timeout):
    err = "no answer"
    for method in ("HEAD", "GET"):   # plenty of hosts refuse HEAD, so a bad HEAD gets a second opinion
        try:
            with fetch(url, method, timeout) as r:
                return ("ok", "", False) if same(r.geturl(), url) else ("moved", f"redirects to {r.geturl()}", False)
        except urllib.error.HTTPError as e:
            err = str(e.code)
            if method == "GET" and e.code in (404, 410): return "dead", err, False
        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.gaierror) and online(): return "dead", "no such host", False
            err = type(e.reason).__name__
        except Exception as e:
            err = type(e).__name__
    return "unknown", err, False

_hosts, _lock = {}, threading.Lock()

def check(url, timeout=15):
    u = urllib.parse.urlparse(url)
    host = u.netloc.lower().removeprefix("www.")
    with _lock: gate = _hosts.setdefault(host, threading.Semaphore(2))   # hammering one host is how you earn a 429
    with gate:
        special = {"github.com": lambda: github(u.path, timeout), "news.ycombinator.com": lambda: hackernews(u, timeout),
                   "apps.apple.com": lambda: appstore(u, timeout)}.get(host)
        return (special and special()) or http(url, timeout)

def check_all(urls, timeout=15):
    urls = list(dict.fromkeys(urls))
    with ThreadPoolExecutor(16) as ex:
        return dict(zip(urls, ex.map(lambda x: check(x, timeout), urls)))


# ---------- what a card links to

def outbound(a):
    """An app's outbound links, keyed the way `dead_links` keys them. `face` is where the
    avatar points (pages.py: the GitHub account, else builder.url). `builder` and
    `replaces` are never rendered, but they are the receipts, so they get checked too."""
    who = load("pages").gh(a)
    b = (a["builder"].get("url") or "").strip()
    face = f"https://github.com/{who}" if who else b
    repo = (a.get("repo") or "").strip()
    out = {"url": a.get("url"), "repo": repo and f"https://github.com/{repo}", "grudge": a["grudge"].get("source"),
           "face": face, "builder": "" if same(b, face) else b, "replaces": (a.get("replaces") or {}).get("source")}
    return {k: v.strip() for k, v in out.items() if (v or "").strip().startswith("http")}

def check_app(a, timeout=15):
    """{field: (url, state, detail, sure)} for one app or queue candidate."""
    links = outbound(a)
    res = check_all(links.values(), timeout)
    return {k: (u, *res[u]) for k, u in links.items()}

def dead_fields(a, timeout=6):
    """What the review desk and merge.py ask before an app joins the list."""
    return {k: f"{u} ({detail})" for k, (u, state, detail, _) in check_app(a, timeout).items() if state == "dead"}


# ---------- the Wayback Machine, best effort: it is down or rate-limiting about as often as not

def snapshot(url, near=""):
    """Closest good capture to the day we listed it, '' if there is none, None if nobody answered."""
    q = urllib.parse.urlencode({"url": url, "timestamp": near.replace("-", "")})
    ok, d = api(f"https://archive.org/wayback/available?{q}", 25)
    if not ok: return None
    snap = ((d or {}).get("archived_snapshots") or {}).get("closest") or {}
    return snap["url"].replace("http://", "https://", 1) if snap.get("available") and snap.get("status") == "200" else ""

def archive(apps):
    """Ask the Wayback Machine to keep a copy of everything these apps link to, so there
    is something to point at the day a link dies. merge.py calls it on approve."""
    def save(url):
        try:
            with fetch("https://web.archive.org/save/" + url, timeout=60): return url, True
        except Exception:
            return url, False
    # GitHub profiles and HN users are not the evidence; the app, the repo and the two sources are
    urls = list(dict.fromkeys(u for a in apps for k, u in outbound(a).items() if k not in ("face", "builder")))
    with ThreadPoolExecutor(3) as ex:
        return dict(ex.map(save, urls))


# ---------- modes

def report_internal():
    bad, n = internal()
    print(f"internal: {n} links, {len(bad)} broken")
    for where, ref in bad: print(f"  BROKEN   {ref}  <- {where}")
    return bad

def run_external(verbose=False):
    apps = json.loads(APPS.read_text())
    where = {}
    for a in apps:
        known = a.get("dead_links") or {}   # already buried: pages.py no longer links to these
        for k, u in outbound(a).items():
            if k not in known: where.setdefault(u, []).append(f"{a['slug']}.{k}")
    for page in ROOT.glob("*.html"):
        for u in re.findall(r'href="(https?://[^"]+)"', page.read_text()):
            if not u.startswith(SITE): where.setdefault(u, []).append(page.name)
    res = check_all(where)

    today = datetime.date.today().isoformat()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    # one good answer clears the record; a bot wall in between neither clears nor counts
    state = {u: s for u, s in state.items() if res.get(u, ("ok",))[0] in ("dead", "unknown")}
    dead, suspect = [], []
    for u, (st, detail, sure) in res.items():
        if st != "dead": continue
        first = state.setdefault(u, {"first": today})["first"]
        state[u].update(last=today, detail=detail)
        (dead if sure or first < today else suspect).append(u)
    STATE.write_text(json.dumps(state, indent=2) + "\n")

    count = lambda s: sum(1 for r in res.values() if r[0] == s)
    print(f"outbound: {len(res)} links · {count('ok')} ok · {len(dead)} dead · {len(suspect)} suspect · "
          f"{count('moved')} moved · {count('unknown')} unknown")
    line = lambda tag, u: print(f"  {tag:8} {u}  ({res[u][1]})  <- {', '.join(where[u])}")
    for u in dead: line("DEAD", u)
    for u in suspect: line("SUSPECT", u)
    for u, r in res.items():
        if r[0] == "moved": line("MOVED", u)
    if verbose:
        for u, r in res.items():
            if r[0] == "unknown": line("UNKNOWN", u)
    slugs = sorted({w.split(".")[0] for u in dead for w in where[u] if "." in w and not w.endswith(".html")})
    if slugs:
        print("\nto stop linking to the dead ones, once the user agrees:")
        for s in slugs: print(f"  python3 scripts/links.py --bury {s}")
    if suspect: print("\nSUSPECT failed for the first time today. It is only DEAD if it fails again on another day.")
    return dead

def run_app(slug):
    a = next((x for x in json.loads(APPS.read_text()) if x["slug"] == slug), None)
    if not a: sys.exit(f"no app with slug {slug!r}")
    for k, (u, st, detail, _) in check_app(a).items():
        print(f"  {st.upper():8} {k:9} {u}" + (f"  ({detail})" if detail else ""))

def bury(slug):
    apps = json.loads(APPS.read_text())
    a = next((x for x in apps if x["slug"] == slug), None)
    if not a: sys.exit(f"no app with slug {slug!r}")
    links, had = outbound(a), dict(a.get("dead_links") or {})
    fresh = {k: u for k, (u, st, *_) in check_app(a).items() if st == "dead" and k not in had}
    retry = {k: links[k] for k, snap in had.items() if not snap and k in links}
    if not fresh and not retry:
        return print(f"{slug}: nothing new is dead, nothing written")
    for k, u in {**fresh, **retry}.items():
        snap = snapshot(u, a.get("added", ""))
        had[k] = snap or ""
        print(f"  {k:9} {u}\n            -> " + (snap or ("the Wayback Machine never captured it" if snap == ""
                                                           else "the Wayback Machine is not answering; rerun --bury later to retry")))
    a["dead_links"] = had
    if "url" in had and a.get("status") != "dead":
        a["status"], a["died"] = "dead", datetime.date.today().isoformat()
        print(f"  {a['name']} is delisted. Its hall of fame page stays up, stamped.")
    APPS.write_text(json.dumps(apps, indent=2, ensure_ascii=False) + "\n")
    r = load("pages").build()
    print(f"hall of fame rebuilt: {r['apps']} live apps, {r['dead']} taken down; wall of shame: {r['products']} products")

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--bury" in args: bury(args[args.index("--bury") + 1]); sys.exit(0)
    if "--app" in args: run_app(args[args.index("--app") + 1]); sys.exit(0)
    broken = report_internal()
    dead = run_external("-v" in args) if "--external" in args else []
    sys.exit(1 if broken or dead else 0)
