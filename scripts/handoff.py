#!/usr/bin/env python3
"""The posting desk for a daily short: shorts/DATE.json -> shorts/DATE.html.

Usage: python3 scripts/handoff.py [shorts/DATE.json] [--open]

One local page with the video, the text for each platform behind a Copy button, and a
link to each upload screen. Nothing here uploads anything: posting is done by hand, by the
user, or for YouTube by scripts/upload.py on the user's word, with the texts() from here.
scripts/short.py builds this page after every render.

The script's "post" block holds the only hand-written words: a title, a caption and the
hashtags. The app list, builder credits and hall of fame links are filled in from
data/apps.json, so a link or a name in a description cannot be mistyped.
"""
import argparse, json, pathlib, re, subprocess, sys

import pages

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHORTS = ROOT / "shorts"
SITE = "https://spiteware.ai"
LIMITS = {"youtube title": 100, "youtube description": 5000, "tiktok caption": 2200, "instagram caption": 2200}


def check(script):
    """Exit with a plain sentence when the post block is missing or will not fit."""
    post = script.get("post")
    if not isinstance(post, dict):
        sys.exit('The script has no "post" block (title, caption, tags). See shorts/README.md.')
    title, caption, tags = post.get("title", ""), post.get("caption", ""), post.get("tags", [])
    if not 10 <= len(title) <= 70:
        sys.exit(f"post.title is {len(title)} characters; keep it between 10 and 70")
    if not 40 <= len(caption) <= 300:
        sys.exit(f"post.caption is {len(caption)} characters; keep it between 40 and 300")
    if re.search(r"[<>]|https?://", title + caption):
        sys.exit("post.title and post.caption take no angle brackets and no links; the links are added for you")
    if not 3 <= len(tags) <= 5 or not all(re.fullmatch(r"[a-z0-9]{2,30}", t) for t in tags):
        sys.exit("post.tags is 3 to 5 lowercase words, letters and digits only, without the #")


def texts(script, apps):
    """The words for each platform, assembled from the post block and data/apps.json."""
    post = script["post"]
    chosen = [apps[s["slug"]] for s in script["segments"] if s["scene"] == "app"]
    more, tags = script.get("more", 0), " ".join("#" + t for t in post["tags"])
    def credit(a):
        r = a.get("replaces") or {}
        return f"{a['name']} by {a['builder']['name']}" + (f", replaces {pages.victim(a)}" if r.get("name") or r.get("price") else "")
    fresh = f"{SITE}/apps.html?sort=new"
    description = "\n\n".join([
        post["caption"],
        "\n\n".join(f"{credit(a)}\n{SITE}{pages.fame(a)}" for a in chosen),
        (f"Plus {more} more fresh today: {fresh}" if more else f"The whole catalog, newest first: {fresh}"),
        "Every app is free. Every grudge is quoted from the person who built it.\nThe narrator is an AI voice.",
        tags])
    # no clickable links on TikTok or in an Instagram caption, so the address is just said
    names = " · ".join(a["name"] for a in chosen) + (f" · +{more} more" if more else "")
    short = "\n\n".join([post["title"], post["caption"], names, "All free at spiteware.ai"])
    out = {"youtube": {"title": post["title"], "description": description},
           "tiktok": {"caption": f"{short}\n\n{tags}"},
           "instagram": {"caption": f"{short} (link in bio)\n\n{tags}"}}
    for where, fields in out.items():
        for field, text in fields.items():
            if len(text) > LIMITS[f"{where} {field}"]:
                sys.exit(f"The {where} {field} came out at {len(text)} characters, over the {LIMITS[f'{where} {field}']} limit")
    return out


def build(script, apps):
    """Write shorts/DATE.html and return its path."""
    check(script)
    mp4 = SHORTS / f"{script['date']}.mp4"
    seconds = 0.0
    if mp4.exists():
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                               capture_output=True, text=True)
        seconds = float(probe.stdout.strip() or 0)
    y, m, d = map(int, script["date"].split("-"))
    data = {"date": script["date"], "label": f"{'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()[m - 1]} {d}",
            "video": mp4.name if mp4.exists() else "", "path": str(mp4), "seconds": round(seconds, 1),
            "mb": round(mp4.stat().st_size / 1e6, 1) if mp4.exists() else 0, "text": texts(script, apps)}
    page = SHORTS / f"{script['date']}.html"
    tpl = (ROOT / "scripts" / "handoff.html").read_text()
    page.write_text(tpl.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
    return page


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("script", nargs="?", help="shorts/DATE.json, default the newest")
    ap.add_argument("--open", action="store_true", help="open the page in the browser")
    a = ap.parse_args()
    src = pathlib.Path(a.script) if a.script else max(SHORTS.glob("20*.json"))
    apps = {x["slug"]: x for x in json.loads((ROOT / "data" / "apps.json").read_text())}
    page = build(json.loads(src.read_text()), apps)
    print(page.relative_to(ROOT))
    if a.open:
        subprocess.Popen(["xdg-open", str(page)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
