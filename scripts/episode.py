#!/usr/bin/env python3
"""Render the monthly episode: episodes/YYYY-MM.json (the script) -> episodes/YYYY-MM.mp4.

Usage: python3 scripts/episode.py [episodes/YYYY-MM.json] [--measure] [--stills] [--secs N] [--tempo 1.06] [--open]

Defaults to the newest script in episodes/. One 1920x1080 H.264 file: two hosts talking through the
month's apps. Each turn is one voice take from scripts/voice.py (hers and his are different voices,
set in episodes/hosts.json); captions are timed to the pauses in the take; scripts/episode.html is
screenshotted per caption with headless Firefox. The equalizer is real: each host's voice is its
own track, ffmpeg draws its spectrum (hers pink, his yellow) on a black layer, and the stills sit on
top with keyed-out windows where it shows through. Every sound effect is synthesized here, so there
is nothing to license. Needs firefox and ffmpeg; stdlib otherwise.

--measure voices the script and prints how long each segment runs, without rendering.
--stills renders one still per kind of frame into the build folder, to look at before a full render.
--secs N renders only the first N seconds.

Before the voice is paid for, the script is checked against every earlier episode: a site tip that
was already used is refused, and reused stickers or repeated lines are listed. A contact sheet
(sheet.png), the thumbnail (thumb.jpg) and the YouTube description (description.txt) land in
episodes/.build/YYYY-MM/. Nothing is uploaded here: scripts/upload.py does that, on the user's
word. The format and the writing rules are in episodes/README.md.
"""
import argparse, array, concurrent.futures as cf, hashlib, json, math, pathlib, random, re, shutil
import subprocess, sys, tempfile

import handoff, pages, short, voice

ROOT = pathlib.Path(__file__).resolve().parent.parent
EPISODES = ROOT / "episodes"
RATE, FPS, WOBBLE, TAIL = voice.RATE, 30, 0.27, 2.2
TARGET, LIMIT = 300, 345              # seconds: what an episode aims for, and where the render starts complaining
TAG = re.compile(r"<([^<>]+)>")
KEY = "0x00FF01"                      # the stills paint this where the equalizer shows through
EQ, MINI = (530, 270, 1240, 440), (300, 48, 360, 56)   # x, y, w, h of the two windows, as in episode.html
MONTHS = "January February March April May June July August September October November December".split()
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
STAGE_SOUND = {"bill": "ching", "app": "punch", "shot": "punch", "spite": "punch"}

APPS = {a["slug"]: a for a in json.loads((ROOT / "data" / "apps.json").read_text())}
HOSTS = json.loads((EPISODES / "hosts.json").read_text())
EP, BUILD = {}, None                  # the script being rendered and its build folder; load() sets both


def load(path):
    global BUILD
    EP.update(json.loads(pathlib.Path(path).read_text()))
    y, m = map(int, EP["month"].split("-"))
    EP["label"] = f"{MONTHS[m - 1]} {y}"
    EP["live"] = [a for a in APPS.values() if a["added"].startswith(EP["month"]) and pages.alive(a)]
    EP["products"] = len({a["replaces"].get("product") for a in EP["live"] if a["replaces"].get("product")})
    EP["wall_apps"] = [a["name"] for a in EP["live"] if a["replaces"].get("product") == EP.get("wall")]
    BUILD = EPISODES / ".build" / EP["month"]
    (BUILD / "shots").mkdir(parents=True, exist_ok=True)
    handoff.check(EP)


def number(n):
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")
    return "a hundred" + (" and " + number(n % 100) if n % 100 else "")


def plain(text):
    return re.sub(r"\s+", " ", TAG.sub("", text)).strip()


def spoken(text):
    """What the voice reads for a caption: the script's own pronunciations first, then the standing ones."""
    for a, b in EP.get("say", []) + HOSTS["say"]:
        text = text.replace(a, b)
    return re.sub(r"\b(\d{1,3}) (more|new|of those)\b", lambda m: f"{number(int(m.group(1)))} {m.group(2)}", text)


def turns():
    out = [{"seg": s["title"], "who": who, "text": text} for s in EP["segments"] for who, text in s["turns"]]
    script = " ".join(plain(t["text"]) for t in out) + " " + ", ".join(EP["wall_apps"])  # the wall shows them all
    named = [a for a in EP["live"] if re.search(r"(?<![\w-])" + re.escape(a["name"]) + r"(?![\w-])", script)]
    EP["named"] = named
    for t in out:
        t["text"] = t["text"].replace("{MORE}", str(len(EP["live"]) - len(named))).replace("{LIVE}", str(len(EP["live"])))
        for tag in TAG.findall(t["text"]):
            p = tag.split()
            if p[0] in STAGE_SOUND and p[1] not in APPS:
                sys.exit(f"no such app: {p[1]}")
            if p[0] in STAGE_SOUND and not pages.alive(APPS[p[1]]):
                sys.exit(f"{p[1]} is buried; an episode does not feature a dead app")
            if p[0] in ("fx", "sfx", "pre"):
                synth(p[2] if p[0] == "fx" else p[1])  # a misspelt sound should fail before the voice is paid for
    return out


def memory():
    """What earlier episodes already did, so this one does not do it again. Exits on a repeated site tip."""
    mine = {plain(t).lower() for s in EP["segments"] for _, t in s["turns"] if len(plain(t).split()) >= 4}
    def emoji(script):  # 💬 and 🔔 are the standing ones: every episode asks the viewer something and asks them to subscribe
        return {p[2] if p[0] == "pre" else p[1] for s in script["segments"] for _, t in s["turns"]
                for p in map(str.split, TAG.findall(t)) if p[0] in ("fx", "pre")} - {"💬", "🔔"}
    stickers = emoji(EP)
    for path in sorted(EPISODES.glob("20*.json")):
        old = json.loads(path.read_text())
        if old["month"] >= EP["month"]:
            continue
        again = set(EP.get("site_tips", [])) & set(old.get("site_tips", []))
        if again:
            sys.exit(f"site tip already used in {old['month']}: {', '.join(sorted(again))}. Pick another; episodes/ledger.md lists what is left.")
        theirs = {plain(t).lower() for s in old["segments"] for _, t in s["turns"]}
        for line in sorted(mine & theirs):
            print(f"  said word for word in {old['month']}: {line}")
        used = emoji(old)
        if len(stickers & used) > len(stickers) / 3:
            print(f"  stickers shared with {old['month']}: {' '.join(sorted(stickers & used))}  (each episode gets its own set)")
    if not EP.get("site_tips"):
        sys.exit('The script has no "site_tips": every episode mentions one thing about the site. See episodes/README.md.')


# ---------- voice ----------

def take(t):
    """One cleaned take for a turn. The provider's filter now and then refuses a short line, so try other framings."""
    host, text = HOSTS["hosts"][t["who"]], spoken(plain(t["text"]))
    tries = [f"{host['style']} {text}", f"{HOSTS['fallback_style']} {text}", text, f"{host['style']} {text}"]
    err = None
    for k, prompt in enumerate(tries):
        try:
            pcm = voice.say(prompt, voice=host["voice"], fresh=(k == 3))
            a, b, _ = short.speech_span(pcm)
            pcm = pcm[int(max(0, a - 0.03) * RATE) * 2:int((b + 0.08) * RATE) * 2]
            return short.tighten(pcm, keep=0.24)
        except (SystemExit, Exception) as e:  # noqa: BLE001
            err = e
    raise RuntimeError(f"no take for {t['who']}: {t['text'][:60]} | {str(err)[:200]}")


def voiced(ts):
    with cf.ThreadPoolExecutor(5) as ex:
        return list(ex.map(take, ts))


def gap_after(t, nxt):
    if nxt is None:
        return 0.0
    return 0.10 if nxt["who"] == t["who"] else 0.17


# ---------- captions and stages ----------

def chunks(text):
    """Caption-sized pieces of a turn, each {"text", "events"}: a tag opens a new caption and belongs to it."""
    res, pos, ev = [], 0, []

    def add(seg, events):
        cur, n, first, mine = [], 0, True, []
        for w in seg.split():
            cur.append(w)
            n += 1
            end = w.rstrip("\"”'")[-1:]
            if (end in ".!?" and not re.fullmatch(r"[A-Z]\.", w) and n >= 5) or (end in ",;:" and n >= 11) or n >= 19:
                mine.append({"text": " ".join(cur), "events": events if first else []})
                cur, n, first = [], 0, False
        if cur:
            if mine and len(cur) < 3:
                mine[-1]["text"] += " " + " ".join(cur)
            else:
                mine.append({"text": " ".join(cur), "events": events if first else []})
        res.extend(mine)

    for m in TAG.finditer(text):
        seg = text[pos:m.start()]
        if seg.strip():
            add(seg, ev)
            ev = []
        ev.append(m.group(1).split())
        pos = m.end()
    if text[pos:].strip():
        add(text[pos:], ev)
    return res


def web(path):
    return "/" + str(path.relative_to(ROOT))


def firefox(url, png, size, profiles):
    for _ in range(4):  # a headless Firefox now and then hangs on start; a fresh profile gets through
        prof = tempfile.mkdtemp(dir=profiles)
        try:
            subprocess.run(["firefox", "--headless", "--no-remote", "--profile", prof, f"--window-size={size}",
                            "--screenshot", str(png), url], capture_output=True, timeout=45)
        except subprocess.TimeoutExpired:
            continue
        if png.exists():
            return True
    return False


def crop(png):
    tmp = png.with_suffix(".c.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(png), "-vf", "crop=min(iw\\,1280):min(ih\\,800):0:0",
                    "-update", "1", str(tmp)], check=True)
    tmp.replace(png)


def app_shot(slug):
    """A screenshot of the app's own page, or "" when it comes out blank (a page that draws itself after load
    does). The script's "shots" can point a slug at another address, such as its repo."""
    png = BUILD / "shots" / f"{slug}.png"
    if not png.exists():
        url = EP.get("shots", {}).get(slug) or pages.out(APPS[slug], "url", APPS[slug]["url"])
        with tempfile.TemporaryDirectory() as profiles:
            if not (url and firefox(url, png, "1280,800", profiles)):
                return ""
        crop(png)
    return web(png) if png.stat().st_size > 20000 else ""


def site_shot(page, query=""):
    """A screenshot of one of the site's own pages, from the working tree, with analytics stripped so a render is not a visit."""
    png = BUILD / "shots" / f"site-{page}-{query or 'all'}.png"
    if not png.exists():
        src = (ROOT / f"{page}.html").read_text()
        src = re.sub(r'<script async src="https://www\.googletagmanager\.com[^>]*></script>', "", src)
        src = re.sub(r"<script>\s*window\.dataLayer[\s\S]*?</script>", "", src)
        # the page fetches its data after load, too late for a screenshot: hand it over synchronously, and keep it offline
        data = (ROOT / "data" / "apps.json").read_text().replace("</", "<\\/")
        shim = ('<head><base href="/"><script>window.fetch = u => String(u).includes("apps.json") ? Promise.resolve({ok: true, status: 200, '
                'json: () => Promise.resolve(' + data + ')}) : Promise.reject(new Error("offline"));</script>')
        copy = BUILD / f"site-{page}.html"
        copy.write_text(src.replace("<head>", shim, 1))
        srv, base = short.serve()
        with tempfile.TemporaryDirectory() as profiles:
            ok = firefox(base + web(copy) + (f"?q={query}" if query else ""), png, "1280,800", profiles)
        srv.shutdown()
        if not ok:
            sys.exit(f"could not screenshot the site's {page} page")
        crop(png)
    return web(png)


def app_view(slug, shot=False):
    a = APPS[slug]
    price = re.sub(r"\s*\(.*\)$", "", a["replaces"].get("price", ""))
    return {"slug": slug, "name": a["name"], "icon": a["icon"], "builder": a["builder"]["name"] or a["builder"]["handle"],
            "victim": a["replaces"].get("name", ""), "price": price, "tags": a["tags"], "open_source": a["open_source"],
            "face": short.face(a), "shot": app_shot(slug) if shot else ""}


def timeline(ts, takes):
    """Every caption as a frame (who speaks, what the stage shows, when), the mixed voice, one track per host, and the sounds."""
    cues, sounds, pcm = [], [], bytearray()
    solo = {k: bytearray() for k in HOSTS["hosts"]}
    stage, heard, sticker, until, stuck = {"t": "eq"}, {}, None, 0.0, 0
    live, more = len(EP["live"]), len(EP["live"]) - len(EP["named"])

    def silence(sec):
        z = b"\0\0" * int(sec * RATE)
        pcm.extend(z)
        for k in solo:
            solo[k].extend(z)

    def frame(t, who, seg, cap):
        view = dict(stage)
        if view.get("slug"):
            view["app"] = app_view(view["slug"], view["t"] == "shot")
            if view["t"] == "shot" and not view["app"]["shot"]:
                view["t"] = "app"  # no usable screenshot: the card instead
        if view["t"] == "wall":
            said = heard.get(seg, "")
            view["named"] = EP["wall_apps"] if view.get("lit") else [n for n in EP["wall_apps"] if re.search(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", said)]
            view.update(all=EP["wall_apps"], product=EP["wall"])
        if view["t"] in ("title", "outro"):
            view.update(live=live, more=more, month=EP["label"], products=EP["products"])
        on = sticker if t < until else None
        fresh = bool(on) and (not cues or (cues[-1]["sticker"] or {}).get("n") != on["n"])
        cues.append({"t": t, "who": who, "seg": seg, "cap": cap, "stage": view, "sticker": on, "fresh": fresh})

    for k, (t, tk) in enumerate(zip(ts, takes)):
        parts = chunks(t["text"])
        first = parts[0]["events"]
        air = [float(e[1]) for e in first if e[0] == "gap"]
        if air:  # a breath between items: nobody talking, the last card still up
            frame(len(pcm) / 2 / RATE, "", t["seg"], "")
            silence(air[0])
        pre = [e for e in first if e[0] == "pre"]
        if pre:  # the sound gets the floor before the line
            t0 = len(pcm) / 2 / RATE
            if any(e[0] == "eq" for e in first):
                stage = {"t": "eq"}
            sounds.append((t0, pre[0][1]))
            stuck += 1
            sticker, until = {"e": pre[0][2], "n": stuck, "p": ""}, t0 + 2.2
            frame(t0, "", t["seg"], "")
            silence(0.85)
        starts = short.cue_starts([{"cap": spoken(p["text"])} for p in parts], tk) if len(parts) > 1 else [0.0]
        t0 = len(pcm) / 2 / RATE
        for p, st in zip(parts, starts):
            at = t0 + st
            for e in p["events"]:
                if e[0] in STAGE_SOUND:
                    stage = {"t": "app" if e[0] == "spite" else e[0], "slug": e[1]}
                    if e[0] == "spite":
                        stage["stamp"] = "SPITE OF THE MONTH"
                    sounds.append((at, STAGE_SOUND[e[0]]))
                elif e[0] in ("eq", "wall", "outro", "title"):
                    stage = {"t": e[0], "lit": len(e) > 1}
                elif e[0] == "site":
                    stage = {"t": "site", "img": site_shot(e[1], e[2] if len(e) > 2 else ""),
                             "label": "spiteware.ai/" + e[1] + (f"  ·  search: {e[2]}" if len(e) > 2 else "")}
                    sounds.append((at, "whoosh"))
                elif e[0] == "stats":
                    stage = {"t": "title", "stats": True}
                elif e[0] == "fx":
                    stuck += 1
                    sticker, until = {"e": e[1], "n": stuck, "p": e[3] if len(e) > 3 else ""}, at + 1.5
                    sounds.append((at, e[2]))
                elif e[0] == "sfx":
                    sounds.append((at, e[1]))
            heard[t["seg"]] = heard.get(t["seg"], "") + " " + p["text"]
            frame(at, t["who"], t["seg"], p["text"])
        pcm.extend(tk)
        for h in solo:
            solo[h].extend(tk if h == t["who"] else b"\0" * len(tk))
        silence(gap_after(t, ts[k + 1] if k + 1 < len(ts) else None))
    silence(TAIL)
    return cues, bytes(pcm), {h: bytes(b) for h, b in solo.items()}, sounds


# ---------- sound effects, all synthesized ----------

def synth(name):
    """A short cartoon sound as floats in -1..1 at RATE. Nothing sampled, so nothing to license."""
    rnd, R, tau = random.Random(len(name) * 7 + ord(name[0])), RATE, 2 * math.pi

    def sweep(dur, freq, amp, shape=math.sin):
        out, ph = [], 0.0
        for k in range(int(dur * R)):
            t = k / R
            ph += tau * freq(t) / R
            out.append(shape(ph) * amp(t))
        return out

    def bells(dur, partials, decay, amp):
        return [amp * math.exp(-decay * k / R) * sum(w * math.sin(tau * f * k / R) for f, w in partials) for k in range(int(dur * R))]

    def mix(*layers):
        out = [0.0] * max(len(x) + o for x, o in layers)
        for x, o in layers:
            for i, v in enumerate(x):
                out[o + i] += v
        return out

    square = lambda ph: math.sin(ph) + math.sin(3 * ph) / 3 + math.sin(5 * ph) / 5  # noqa: E731
    saw = lambda ph: sum(math.sin(h * ph) / h for h in range(1, 9)) * 0.6  # noqa: E731
    noise = lambda dur, decay, amp: [amp * (rnd.random() * 2 - 1) * math.exp(-decay * k / R) for k in range(int(dur * R))]  # noqa: E731

    if name == "punch":
        return mix((sweep(0.24, lambda t: 150 * math.exp(-16 * t) + 45, lambda t: 0.9 * math.exp(-13 * t)), 0), (noise(0.05, 80, 0.55), 0))
    if name == "ching":
        hit = bells(0.55, [(2093, 1), (2637, .7), (3136, .5), (4186, .3)], 8, 0.16)
        return mix((noise(0.03, 150, 0.3), 0), (hit, int(.02 * R)), (hit, int(.12 * R)))
    if name == "ding":
        return bells(0.9, [(1318.5, 1), (2637, .4), (3955, .2)], 5, 0.32)
    if name == "pop":
        return sweep(0.09, lambda t: 320 + 9000 * t, lambda t: 0.75 * (1 - t / 0.09))
    if name == "boing":
        return sweep(0.6, lambda t: 210 * math.exp(-1.4 * t) * (1 + 0.28 * math.sin(tau * 17 * t)), lambda t: 0.6 * math.exp(-4.5 * t))
    if name == "buzzer":
        return sweep(0.42, lambda t: 104, lambda t: 0.3 * min(1, t / .01, (0.42 - t) / .03), square)
    if name == "alarm":
        return sweep(0.9, lambda t: 880 if int(t / 0.11) % 2 == 0 else 1320, lambda t: 0.26 * min(1, t / .01, (0.9 - t) / .05), square)
    if name == "squeak":
        chirp = sweep(0.1, lambda t: 1700 + 9000 * t, lambda t: 0.28 * math.sin(math.pi * t / 0.1))
        return mix((chirp, 0), (chirp, int(.14 * R)))
    if name == "gong":
        return bells(1.7, [(196, 1), (296.6, .5), (415.3, .35), (587.3, .2)], 2.2, 0.3)
    if name == "whoosh":
        out, y, dur = [], 0.0, 0.5
        for k in range(int(dur * R)):
            t = k / R
            y += (0.03 + 0.5 * t / dur) * ((rnd.random() * 2 - 1) - y)
            out.append(1.3 * y * math.sin(math.pi * t / dur))
        return out
    if name == "fanfare":
        notes, out = [(523.3, .1), (659.3, .1), (784, .1), (1046.5, .45)], []
        for f, d in notes:
            out += sweep(d, lambda t, f=f: f, lambda t, d=d: 0.26 * min(1, t / .008) * math.exp(-2.5 * t / d * (0.4 if d > .2 else .2)), square)
        return out
    if name == "trombone":
        notes, out = [(233.1, .24), (220, .24), (207.7, .24), (196, .7)], []
        for f, d in notes:
            out += sweep(d, lambda t, f=f, d=d: f * (1 - (0.04 * t / d if d > .5 else 0)),
                         lambda t, d=d: 0.3 * min(1, t / .02, (d - t) / .05) * (1 - 0.25 * math.sin(tau * 6 * t) * (d > .5)), saw)
        return out
    if name == "drumroll":
        layers, t = [], 0.0
        while t < 0.75:
            layers.append((noise(0.03, 110, 0.12 + 0.3 * t), int(t * R)))
            t += 1 / 26
        layers.append((synth("punch"), int(0.8 * R)))
        return mix(*layers)
    if name == "meow":
        dur, out, ph = 0.66, [], 0.0
        for k in range(int(dur * R)):
            t = k / R
            x = t / dur
            f0 = (470 + 250 * (x / .2) if x < .2 else 720 + 50 * ((x - .2) / .35) if x < .55 else 770 - 340 * ((x - .55) / .45))
            f0 *= 1 + 0.012 * math.sin(tau * 7 * t)
            ph += tau * f0 / R
            bright = math.sin(math.pi * x) ** 0.8
            s = sum(math.exp(-(h - 1) * (1.5 - 1.15 * bright)) * math.sin(h * ph) for h in range(1, 9))
            out.append(0.2 * s * min(t / .07, 1) * min((dur - t) / .2, 1))
        return out
    sys.exit(f"no such sound: {name}. The ones there are: alarm boing buzzer ching ding drumroll fanfare gong meow pop punch squeak trombone whoosh")


def sound_track(sounds, seconds):
    out = array.array("h", bytes(2 * int(seconds * RATE)))
    made = {}
    for t, name in sounds:
        wave_ = made.setdefault(name, synth(name))
        i = int(t * RATE)
        for k, v in enumerate(wave_[:len(out) - i]):
            out[i + k] = max(-32000, min(32000, out[i + k] + int(v * 32000)))
    return out.tobytes()


# ---------- frames ----------

def stills(cues):
    """A pair of stills (mouth shut, mouth open) per caption, and a third where a sticker lands; identical frames share a file."""
    tpl = (ROOT / "scripts" / "episode.html").read_text()
    hosts = {k: {"name": v["name"], "role": v["role"]} for k, v in HOSTS["hosts"].items()}
    jobs, pairs = {}, []
    for c in cues:
        pair = []
        for j in (0, 1, 2) if c.get("fresh") else (0, 1):  # 2 = the sticker landing, shown once
            data = json.dumps({"who": c["who"], "seg": c["seg"], "cap": c["cap"], "stage": c["stage"], "sticker": c["sticker"],
                               "j": j, "hosts": hosts, "month": EP["label"]}, ensure_ascii=False)
            name = hashlib.sha1((tpl + data).encode()).hexdigest()[:14]
            page, png = BUILD / f"{name}.html", BUILD / f"{name}.png"
            page.write_text(tpl.replace("/*FRAME*/null", data.replace("</", "<\\/")))
            jobs[name] = (page, png)
            pair.append(png)
        pairs.append(pair)
    todo = [(p, g) for p, g in jobs.values() if not g.exists()]
    print(f"frames… {len(jobs)} stills, {len(todo)} to shoot", flush=True)
    srv, base = short.serve()
    with tempfile.TemporaryDirectory() as profiles, cf.ThreadPoolExecutor(4) as ex:
        ok = list(ex.map(lambda job: firefox(base + web(job[0]), job[1], "1920,1080", profiles), todo))
    srv.shutdown()
    if not all(ok):
        sys.exit(f"{ok.count(False)} stills were not written")
    return pairs


def measure(ts, takes):
    total, per, words = 0.0, {}, {}
    for k, (t, tk) in enumerate(zip(ts, takes)):
        d = len(tk) / 2 / RATE + gap_after(t, ts[k + 1] if k + 1 < len(ts) else None)
        d += sum(float(p[1]) for p in map(str.split, TAG.findall(t["text"])) if p[0] == "gap")
        per[t["seg"]] = per.get(t["seg"], 0) + d
        words[t["seg"]] = words.get(t["seg"], 0) + len(plain(t["text"]).split())
        total += d
    for seg in per:
        print(f"  {seg:22s} {per[seg]:6.1f}s  {words[seg]:4d} words")
    cut = (total + TAIL) / EP.get("tempo", 1.06)
    print(f"  {'TOTAL':22s} {total:6.1f}s  {sum(words.values())} words -> about {int(cut // 60)}:{int(cut % 60):02d} at tempo {EP.get('tempo', 1.06)}; "
          f"{len(EP['named'])} apps named, {len(EP['live']) - len(EP['named'])} more")


def describe(marks):
    """The YouTube description: the caption, chapters from the real cut, every app named with its hall of fame page."""
    post = EP["post"]
    chapters = "\n".join(f"{int(t // 60)}:{int(t % 60):02d} {s[0].upper() + s[1:]}" for s, t in marks.items())
    def credit(a):
        r = a.get("replaces") or {}
        return f"{a['name']} by {a['builder']['name'] or a['builder']['handle']}" + (f", replaces {pages.victim(a)}" if r.get("name") or r.get("price") else "")
    apps = "\n\n".join(f"{credit(a)}\n{handoff.SITE}{pages.fame(a)}" for a in EP["named"])
    more = len(EP["live"]) - len(EP["named"])
    # YouTube only makes description links clickable for a channel with its advanced features on, and shortens
    # the ones it does not link. So say where everything is in words a viewer can type, before the list.
    find = f"Every app here is on spiteware.ai: type its name into the search box on the apps page."
    text = "\n\n".join([post["title"], post["caption"], find, chapters, apps,
                        f"Plus {more} more from {EP['label'].split()[0]}: {handoff.SITE}/apps.html?sort=new",
                        "Every app is free. Prices and grudges come from the people who built them.\n"
                        "The hosts are AI voices and their stories are scripted.",
                        " ".join("#" + t for t in post["tags"])])
    (BUILD / "description.txt").write_text(text + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("script", nargs="?", help="episodes/YYYY-MM.json, default the newest")
    ap.add_argument("--measure", action="store_true", help="voice the script and print segment lengths, no render")
    ap.add_argument("--stills", action="store_true", help="one still per kind of frame, into the build folder's test/")
    ap.add_argument("--secs", type=float, default=0, help="render only the first N seconds")
    ap.add_argument("--tempo", type=float, help="speed the cut up, pitch kept; default the script's, else 1.06")
    ap.add_argument("--open", action="store_true", help="open the video when done")
    a = ap.parse_args()
    for tool in ("firefox", "ffmpeg"):
        if not shutil.which(tool):
            sys.exit(f"{tool} is not on PATH")
    load(a.script or max(EPISODES.glob("20*.json")))
    memory()
    ts = turns()
    print("voice…", flush=True)
    takes = voiced(ts)
    measure(ts, takes)
    if a.measure:
        return
    tempo = a.tempo or EP.get("tempo", 1.06)
    cues, pcm, solo, sounds = timeline(ts, takes)

    if a.stills:
        seen, pick = set(), []
        for c in cues:
            s = c["stage"]
            key = (s["t"], bool(s.get("stats")), bool(s.get("stamp")), bool(s.get("lit")), c["who"] == "",
                   (c["sticker"] or {}).get("n", 0) % 5 if c.get("fresh") else None)
            if key not in seen:
                seen.add(key)
                pick.append(c)
        out = BUILD / "test"
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir()
        for n, (c, pair) in enumerate(zip(pick, stills(pick))):
            shutil.copy(pair[-1], out / f"{n:02d}-{c['stage']['t']}.png")
        print(f"{len(pick)} stills in {out.relative_to(ROOT)} (green is where the equalizer goes)")
        return

    total = len(pcm) / 2 / RATE
    if a.secs:
        total = min(total, a.secs * tempo)
        cues, sounds = [c for c in cues if c["t"] < total], [s for s in sounds if s[0] < total]
        pcm, solo = pcm[:int(total * RATE) * 2], {h: b[:int(total * RATE) * 2] for h, b in solo.items()}
    pairs = stills(cues)
    voice.write_wav(BUILD / "voice.wav", pcm)
    for h, b in solo.items():
        voice.write_wav(BUILD / f"solo-{h}.wav", b)
    voice.write_wav(BUILD / "sfx.wav", sound_track(sounds, total))

    # concat list: each caption holds until the next, mouth flapping between its two stills
    lines = []
    for k, (c, pair) in enumerate(zip(cues, pairs)):
        t, end = (0.0 if k == 0 else c["t"]), (cues[k + 1]["t"] if k + 1 < len(cues) else total)
        w = 0
        while t < end - 1e-6:
            hold = min(WOBBLE, end - t)
            still = pair[2] if (w == 0 and len(pair) > 2) else pair[(w % 2) if c["who"] else 0]
            lines += [f"file '{still}'", f"duration {hold / tempo:.4f}"]
            t += hold
            w += 1
    lines.append(lines[-2])  # the concat demuxer drops the last duration without a closing file
    (BUILD / "frames.txt").write_text("\n".join(lines) + "\n")

    out = EPISODES / f"{EP['month']}{'-sample' if a.secs else ''}.mp4"
    print("encode…", flush=True)
    (ex, ey, ew, eh), (mx, my, mw, mh) = EQ, MINI
    # Half-width spectrum, mirrored, so the voice peaks in the middle. Planar RGB so adding the two tracks stays
    # black on black. No time averaging: with it a bin can stick at full height for the rest of the video. The crop
    # drops the lowest bins (rumble) and the top half (quiet speech then fills the panel).
    eq = (f"atempo={tempo},aresample=8000,volume=5,showfreqs=s={ew // 2 + 20}x{eh * 2}:rate={FPS}:mode=bar:ascale=cbrt:"
          f"fscale=lin:win_size=128:averaging=1:colors={{c}},crop={ew // 2}:{eh}:20:{eh},format=gbrp")
    graph = (
        f"[0:v]fps={FPS},scale=1920:1080,colorkey={KEY}:0.08:0.0[fg];"
        f"[3:a]{eq.format(c='0xFF3E9A')}[ev];[4:a]{eq.format(c='0xFFE600')}[eg];"
        f"[ev][eg]blend=all_mode=addition,split[h1][h2];[h1]hflip[h1f];[h1f][h2]hstack,"
        f"drawgrid=w=20:h={eh}:t=6:c=black,format=rgb24,split[eqb][eqm];"
        f"[eqm]scale={mw}:{mh}[eqs];color=c=black:s=1920x1080:r={FPS}[bg];"
        f"[bg][eqb]overlay={ex}:{ey}[b1];[b1][eqs]overlay={mx}:{my}[b2];[b2][fg]overlay=0:0,format=yuv420p[v];"
        f"[1:a]atempo={tempo},loudnorm=I=-16:TP=-1.5[vo];[2:a]atempo={tempo},volume=0.5[fx];"
        "[vo][fx]amix=inputs=2:duration=first:normalize=0,aresample=48000[a]")
    done = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(BUILD / "frames.txt"),
         "-i", str(BUILD / "voice.wav"), "-i", str(BUILD / "sfx.wav"), "-i", str(BUILD / "solo-V.wav"),
         "-i", str(BUILD / "solo-G.wav"), "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
         "-t", f"{total / tempo:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(out)], capture_output=True, text=True)
    if done.returncode:
        sys.exit("ffmpeg failed:\n" + done.stderr[-1200:])
    subprocess.run(["xattr", "-d", "com.apple.quarantine", str(out)], capture_output=True)  # macOS flags files a sandbox wrote

    marks = {}
    for c in cues:
        marks.setdefault(c["seg"], c["t"] / tempo)
    describe(marks)
    # the thumbnail upload.py sets: the title card, with the month's two numbers if the script shows them
    card = next((c for c in cues if c["stage"].get("stats")), None) or next((c for c in cues if c["stage"]["t"] == "title"), cues[0])
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{card['t'] / tempo + 0.4:.2f}", "-i", str(out), "-frames:v", "1",
                    "-vf", "scale=1280:720", "-q:v", "3", "-update", "1", str(BUILD / "thumb.jpg")], capture_output=True)
    sheet = BUILD / "sheet.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out), "-vf", "fps=1/8,scale=384:-1,tile=6x8",
                    "-frames:v", "1", "-update", "1", str(sheet)], capture_output=True)
    length = total / tempo
    print(f"sheet  {sheet.relative_to(ROOT)}")
    print(f"words  {(BUILD / 'description.txt').relative_to(ROOT)}")
    print(f"{out.relative_to(ROOT)}  {int(length // 60)}:{int(length % 60):02d}  {out.stat().st_size / 1e6:.1f} MB")
    if length > LIMIT and not a.secs:
        print(f"That is over {LIMIT // 60}:{LIMIT % 60:02d}. An episode aims for {TARGET // 60}:00: cut apps or lines, not the breaths between them.")
    if a.open:
        handoff.show(out)


if __name__ == "__main__":
    main()
