#!/usr/bin/env python3
"""The share card of every app: cards/<slug>.jpg, the 1200x630 picture a link preview shows.

Usage: python3 scripts/cards.py            render whatever is missing or out of date
       python3 scripts/cards.py --all      render every card again

scripts/pages.py calls ensure() at the start of every build, so the morning merge, a card fixed
from the inbox and a change to the template all reach the cards without anyone remembering to.
A card is rendered again only when what it shows changes: cards/.hashes.json keeps a hash of
each card's words, face and template, and is committed with the cards.

The frame is scripts/card.html, filled in per app and screenshotted by headless Firefox like the
short's frames (short.shoot, short.serve and short.face, so the avatar comes from the same local
cache). No Firefox, no new cards: ensure() says so and pages.py keeps the site-wide /og.png for
any app without one, so a build never fails for want of a picture.
"""
import concurrent.futures as cf, hashlib, html, json, pathlib, re, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
HASHES = CARDS / ".hashes.json"
TEMPLATE = ROOT / "scripts" / "card.html"
BUILD = CARDS / ".build"   # gitignored: the filled-in frames and the raw screenshots


def path(a):
    """Where an app's card is served from, or None when it has none yet."""
    return f"/cards/{a['slug']}.jpg" if (CARDS / f"{a['slug']}.jpg").exists() else None


def size(name):
    """The app name's font size: long names step down so every one fits on two lines."""
    n = len(name)
    return 124 if n <= 9 else 104 if n <= 13 else 86 if n <= 18 else 70 if n <= 26 else 58


def victim(a):
    """What the badge strikes through: pages.victim() without the bracketed plan notes, which
    the site's own price column drops too ("$18/user/mo (Business+ plan, ...)" -> "$18/user/mo")."""
    import pages
    return re.sub(r"\s*\([^)]*\)", "", pages.victim(a)).strip()


def fill(a, face, template):
    import pages
    esc = lambda s: html.escape(str(s or ""), quote=True)
    b = a["builder"]
    who = (f'<img class="oc__av" src="{esc(face["img"])}" alt="">' if "img" in face else
           f'<div class="oc__av oc__fb" style="background:{face["hue"]}">{esc(face["initial"])}</div>')
    return (template
            .replace("{{icon}}", esc(a.get("icon") or "🔧"))
            .replace("{{name}}", esc(a["name"]))
            .replace("{{size}}", str(size(a["name"])))
            .replace("{{tagline}}", esc(pages.gist(a["tagline"], 190)))
            .replace("{{vsize}}", str(30 if len(victim(a)) <= 28 else 24 if len(victim(a)) <= 36 else 20))
            .replace("{{victim}}", esc(victim(a)))
            .replace("{{face}}", who)
            .replace("{{builder}}", esc(b.get("name") or b["handle"]))
            .replace("{{score}}", str(a["spite_score"])))


def digest(a, face, template):
    return hashlib.sha256(fill(a, face, template).encode()).hexdigest()[:16]


def ensure(apps, force=False):
    """Render the cards of these apps that are missing or stale. Returns how many it rendered."""
    if not shutil.which("firefox") or not shutil.which("ffmpeg"):
        print("cards: no firefox or ffmpeg here, so no new share cards; pages fall back to /og.png", file=sys.stderr)
        return 0
    sys.path.insert(0, str(ROOT / "scripts"))
    import short
    template = TEMPLATE.read_text()
    old = json.loads(HASHES.read_text()) if HASHES.exists() else {}
    jobs = []
    for a in apps:
        face = short.face(a)
        h = digest(a, face, template)
        if force or old.get(a["slug"]) != h or not (CARDS / f"{a['slug']}.jpg").exists():
            jobs.append((a, face, h))
    if not jobs:
        return 0
    BUILD.mkdir(parents=True, exist_ok=True)
    srv, base = short.serve()
    profile_root = short.profiles()
    profiles = profile_root.name
    try:
        def one(job):
            a, face, h = job
            page, png = BUILD / f"{a['slug']}.html", BUILD / f"{a['slug']}.png"
            page.write_text(fill(a, face, template))
            png.unlink(missing_ok=True)
            for _ in range(3):  # a headless Firefox now and then hangs on start; a fresh profile gets through
                try:
                    subprocess.run(["firefox", "--headless", "--no-remote", "--profile", tempfile.mkdtemp(dir=profiles),
                                    "--window-size=1200,630", "--screenshot", str(png), f"{base}/{page.relative_to(ROOT)}"],
                                   capture_output=True, timeout=45)
                except subprocess.TimeoutExpired:
                    continue
                if png.exists():
                    break
            if not png.exists():
                return a["slug"], None
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(png), "-q:v", "7",
                            str(CARDS / f"{a['slug']}.jpg")], check=True)
            return a["slug"], h
        with cf.ThreadPoolExecutor(4) as ex:
            done = list(ex.map(one, jobs))
    finally:
        srv.shutdown()
        profile_root.cleanup()
    failed = [s for s, h in done if not h]
    old.update({s: h for s, h in done if h})
    HASHES.write_text(json.dumps(dict(sorted(old.items())), indent=1) + "\n")
    if failed:
        print(f"cards: Firefox wrote nothing for {', '.join(failed)}; they keep /og.png until the next build", file=sys.stderr)
    return len(done) - len(failed)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    import pages
    apps = [a for a in json.loads((ROOT / "data/apps.json").read_text()) if pages.alive(a)]
    for a in apps: a["builder"]["name"] = (a["builder"].get("name") or "").strip() or a["builder"]["handle"]
    n = ensure(apps, force="--all" in sys.argv)
    print(f"cards: {n} rendered, {sum(1 for a in apps if path(a))} of {len(apps)} apps have one")
