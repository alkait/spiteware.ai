#!/usr/bin/env python3
"""The words that go up with a daily short, and the checks on them.

scripts/short.py checks the script's post block before it pays for a voice, and
scripts/upload.py sends texts() as the video's title and description. TikTok and Instagram
are posted through the browser by the /spite run, which takes its caption from here and notes
each post here, so the runner can check it and a re-run cannot post the same day twice:

    python3 scripts/handoff.py --caption [DATE]
    python3 scripts/handoff.py --posted tiktok|instagram URL [DATE]

The script's "post" block holds the only hand-written words: a title, a caption and the
hashtags. The app list, builder credits and hall of fame links are filled in from
data/apps.json, so a link or a name in a description cannot be mistyped.
"""
import argparse, datetime, json, re, subprocess, sys
from pathlib import Path

import pages

ROOT = Path(__file__).resolve().parent.parent
POSTED = ROOT / "shorts" / ".cache" / "posted.json"
SITE = "https://spiteware.ai"
LIMITS = {"youtube title": 100, "youtube description": 5000}


def show(target):
    """Open a file or URL in the default browser: `open` on macOS, `xdg-open` elsewhere."""
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
    """The YouTube title and description, assembled from the post block and data/apps.json."""
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
    out = {"youtube": {"title": post["title"], "description": description}}
    for where, fields in out.items():
        for field, text in fields.items():
            if len(text) > LIMITS[f"{where} {field}"]:
                sys.exit(f"The {where} {field} came out at {len(text)} characters, over the {LIMITS[f'{where} {field}']} limit")
    return out


def social(script):
    """The TikTok and Instagram caption. Neither makes a caption link clickable, so it names the site."""
    post = script["post"]
    return "\n\n".join([post["title"], post["caption"],
                        "Every app is free, at spiteware.ai.\nThe narrator is an AI voice.",
                        " ".join("#" + t for t in post["tags"])])


def note(where, url, date):
    """Record a live post in shorts/.cache/posted.json."""
    posted = json.loads(POSTED.read_text()) if POSTED.exists() else {}
    posted.setdefault(date, {})[where] = url
    POSTED.write_text(json.dumps(posted, indent=1) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--caption", nargs="?", const=datetime.date.today().isoformat(), metavar="DATE")
    ap.add_argument("--posted", nargs="+", metavar="WHERE URL [DATE]")
    args = ap.parse_args()
    if args.caption:
        print(social(json.loads((ROOT / "shorts" / f"{args.caption}.json").read_text())))
    elif args.posted and args.posted[0] in ("tiktok", "instagram") and len(args.posted) in (2, 3):
        note(args.posted[0], args.posted[1], (args.posted[2:] or [datetime.date.today().isoformat()])[0])
    else:
        ap.error("pass --caption [DATE] or --posted tiktok|instagram URL [DATE]")
