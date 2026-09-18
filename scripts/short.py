#!/usr/bin/env python3
"""Render the daily short: shorts/DATE.json (the narration script) -> shorts/DATE.mp4.

Usage: python3 scripts/short.py [shorts/DATE.json] [--tempo 1.05] [--reroll SEG] [--guides] [--open]

Defaults to the newest script in shorts/. One 1080x1920 H.264 file that every platform
takes. The voice comes first and sets the clock: each segment is one take from
scripts/voice.py, its cues are timed to the pauses in that take, and scripts/short.html
is screenshotted once per cue with headless Firefox. Hard cuts and a two-frame wobble,
no tweening: it matches the site. Needs firefox and ffmpeg; stdlib otherwise.

--guides draws the platform UI zones over every frame, to check the safe area.
--reroll takes a segment's slug, or "hook" or "outro", and voices it again: every take is a
fresh performance, and the rest stay cached. A contact sheet of the cut lands next to the
build files, so an agent can look at the frames without playing the video. Every render ends
by writing the posting desk, shorts/DATE.html (scripts/handoff.py): nothing is ever uploaded.

The script format and how to write one are in shorts/README.md.
"""
import argparse, array, concurrent.futures as cf, functools, hashlib, http.server, json, math, pathlib
import random, re, shutil, subprocess, sys, tempfile, threading, urllib.request, wave

import handoff, pages, voice

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHORTS = ROOT / "shorts"
RATE = voice.RATE
FPS = 30
GAP = 0.16      # silence between segments
TAIL = 1.6      # hold on the end card
WOBBLE = 0.27   # seconds per wobble frame


# ---------- voice and timing ----------

def speech_span(pcm):
    """(start, end, silences) in seconds. A silence is a (from, to) pause inside the speech."""
    s = array.array("h"); s.frombytes(pcm)
    win = RATE // 100
    loud = [max(map(abs, s[i:i + win])) > 500 for i in range(0, len(s) - win, win)]
    first = loud.index(True); last = len(loud) - 1 - loud[::-1].index(True)
    quiet, run = [], None
    for i in range(first, last + 1):
        if not loud[i]:
            run = i if run is None else run
        elif run is not None:
            if i - run >= 6:
                quiet.append((run / 100, i / 100))
            run = None
    return first / 100, (last + 1) / 100, quiet


def tighten(pcm, keep=0.22):
    """Cap every pause at `keep` seconds. The model breathes between sentences; a short cannot."""
    s = array.array("h"); s.frombytes(pcm)
    win = RATE // 100
    loud = [max(map(abs, s[i:i + win])) > 500 for i in range(0, len(s) - win, win)]
    out, run, half = array.array("h"), [], int(keep * 50)
    for i, is_loud in enumerate(loud + [True]):
        if not is_loud:
            run.append(i); continue
        if len(run) > 2 * half:  # keep the decay into the pause and the attack out of it
            run = run[:half] + run[-half:]
        for k in run + ([i] if i < len(loud) else []):
            out.extend(s[k * win:(k + 1) * win])
        run = []
    return out.tobytes()


def cue_starts(cues, pcm):
    """Start time of each cue inside its take: by share of letters, snapped to a real pause."""
    start, end, quiet = speech_span(pcm)
    spoken = lambda c: re.sub(r"\[[^\]]*\]", "", c.get("say", c["cap"]))
    weight = [len(re.sub(r"\W", "", spoken(c))) + 4 * len(re.findall(r"[.:,]", spoken(c))) for c in cues]
    out, acc = [0.0], 0
    for w in weight[:-1]:
        acc += w
        guess = start + (end - start) * acc / sum(weight)
        near = [(abs((a + b) / 2 - guess), (a + b) / 2) for a, b in quiet if abs((a + b) / 2 - guess) < 0.45]
        t = min(near)[1] if near else guess
        out.append(max(t, out[-1] + 0.2))
    return out


def narrate(script, reroll=()):
    """Voice every segment. Returns (pcm, cues) with absolute start times on each cue."""
    pcm, timeline = b"", []
    for seg in script["segments"]:
        text = script["style"] + " " + " ".join(c.get("say", c["cap"]) for c in seg["cues"])
        take = tighten(voice.say(text, fresh=seg.get("slug", seg["scene"]) in reroll))
        t0 = len(pcm) / 2 / RATE
        for c, t in zip(seg["cues"], cue_starts(seg["cues"], take)):
            timeline.append({**c, "seg": seg, "t": t0 + t})
        pcm += take + b"\0\0" * int(GAP * RATE)
    return pcm + b"\0\0" * int(TAIL * RATE), timeline


# ---------- frames ----------

def frame_data(cue, script, apps, n_apps, guides):
    seg = cue["seg"]
    f = {"scene": seg["scene"], "step": cue["step"], "cap": cue["cap"], "n": n_apps, "guides": guides,
         "date": script["label"], "more": script.get("more", 0)}
    if seg["scene"] == "app":
        f.update(app=apps[seg["slug"]], face=face(apps[seg["slug"]]), i=seg["i"], gripe=seg.get("gripe", ""),
                 quote=seg["quote"], cut=seg.get("cut", False), said=0,
                 score=seg.get("score", True))
        if cue["step"] == "quote":  # how much of the quote has been read once this cue is done
            part = cue["cap"].strip("“”…\" ")
            at = seg["quote"].find(part)
            f["said"] = at + len(part) if at >= 0 and part and not part.endswith(":") else 0
    return f


def face(a):
    """The builder's avatar as the site shows it: their GitHub picture, kept locally so a
    frame never waits on the network, or the same initial tile pages.py falls back to."""
    who, b = pages.gh(a), a["builder"]
    if who and pages.out(a, "face", who):
        png = SHORTS / ".cache" / "faces" / f"{who}.png"
        if not png.exists():
            png.parent.mkdir(parents=True, exist_ok=True)
            try:
                with urllib.request.urlopen(f"https://github.com/{who}.png?size=460", timeout=30) as r:
                    png.write_bytes(r.read())
            except OSError:
                who = ""
        if who:
            return {"img": "/" + str(png.relative_to(ROOT)), "at": who}
    name = b["name"] or b["handle"]
    return {"hue": pages.HUES[len(name) % len(pages.HUES)], "initial": name[0].upper(), "at": b["handle"]}


def shoot(job, base, profile_root):
    html, png = job
    if png.exists():
        return
    prof = tempfile.mkdtemp(dir=profile_root)
    subprocess.run(["firefox", "--headless", "--no-remote", "--profile", prof, "--window-size=1080,1920",
                    "--screenshot", str(png), f"{base}/{html.relative_to(ROOT)}"],
                   capture_output=True, timeout=120)
    if not png.exists():
        sys.exit(f"Firefox did not write {png.name}")


def serve():
    quiet = type("H", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(quiet, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


# ---------- sound effects ----------

def sfx(events, seconds):
    """A thump on every visual change and a stamp on every FREE, as PCM at RATE."""
    out = [0.0] * int(seconds * RATE)
    rnd = random.Random(7)
    def add(t, samples):
        i = int(t * RATE)
        for k, v in enumerate(samples[:len(out) - i]):
            out[i + k] += v
    thump = [0.5 * math.sin(2 * math.pi * (110 - 260 * (k / RATE)) * (k / RATE)) * math.exp(-28 * k / RATE)
             for k in range(int(.2 * RATE))]
    stamp = [(0.55 * (rnd.random() * 2 - 1) * math.exp(-60 * k / RATE)
              + 0.8 * math.sin(2 * math.pi * (80 - 120 * (k / RATE)) * (k / RATE)) * math.exp(-16 * k / RATE))
             for k in range(int(.35 * RATE))]
    for t, kind in events:
        add(t, stamp if kind == "stamp" else thump)
    return array.array("h", (int(max(-1, min(1, v)) * 32000) for v in out)).tobytes()


# ---------- assemble ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("script", nargs="?", help="shorts/DATE.json, default the newest")
    ap.add_argument("--tempo", type=float, default=1.05, help="speed the finished cut up, pitch kept")
    ap.add_argument("--reroll", action="append", default=[], metavar="SEG",
                    help="voice this segment again: an app's slug, hook or outro")
    ap.add_argument("--guides", action="store_true", help="draw the platform UI zones on every frame")
    ap.add_argument("--open", action="store_true", help="open the posting desk (the video and each platform's text) when done")
    a = ap.parse_args()
    guides, show, tempo = a.guides, a.open, a.tempo
    src = pathlib.Path(a.script) if a.script else max(SHORTS.glob("20*.json"))
    script = json.loads(src.read_text())
    handoff.check(script)  # before the voice is paid for
    for tool in ("firefox", "ffmpeg"):
        if not shutil.which(tool):
            sys.exit(f"{tool} is not on PATH")

    apps = {a["slug"]: a for a in json.loads((ROOT / "data" / "apps.json").read_text())}
    app_segs = [s for s in script["segments"] if s["scene"] == "app"]
    for i, s in enumerate(app_segs, 1):
        s["i"] = i
        if s["slug"] not in apps:
            sys.exit(f"{s['slug']} is not in data/apps.json")
        if s["quote"] not in apps[s["slug"]]["grudge"]["quote"]:
            sys.exit(f"{s['slug']}: the quote is not verbatim from data/apps.json")
    y, m, d = map(int, script["date"].split("-"))
    script["label"] = f"{'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()[m - 1]} {d}"

    print("voice…")
    pcm, cues = narrate(script, a.reroll)
    total = len(pcm) / 2 / RATE
    build = SHORTS / ".build" / (script["date"] + ("-guides" if guides else ""))
    build.mkdir(parents=True, exist_ok=True)
    voice.write_wav(build / "voice.wav", pcm)

    # one still per distinct frame; identical frames share a file
    tpl = (ROOT / "scripts" / "short.html").read_text()
    jobs, stills = {}, []
    for c in cues:
        pair = []
        for j in (0, 1):
            data = json.dumps({**frame_data(c, script, apps, len(app_segs), guides), "j": j}, ensure_ascii=False)
            name = hashlib.sha1((tpl + data).encode()).hexdigest()[:12]
            html, png = build / f"{name}.html", build / f"{name}.png"
            html.write_text(tpl.replace("/*FRAME*/null", data.replace("</", "<\\/")))
            jobs[name] = (html, png); pair.append(png)
        stills.append(pair)
    print(f"frames… {len(jobs)} stills")
    srv, base = serve()
    with tempfile.TemporaryDirectory() as profiles, cf.ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda job: shoot(job, base, profiles), jobs.values()))
    srv.shutdown()

    # concat list: each cue holds until the next, wobbling between its two stills
    lines, events, prev = [], [], None
    for k, (c, pair) in enumerate(zip(cues, stills)):
        t, end = c["t"], cues[k + 1]["t"] if k + 1 < len(cues) else total
        t = 0.0 if k == 0 else t
        look = (id(c["seg"]), c["step"])
        if look != prev:
            events.append((t, "stamp" if c["step"] == "free" and c["seg"]["scene"] == "app" else "thump"))
        prev = look
        w = 0
        while t < end - 1e-6:
            hold = min(WOBBLE, end - t)
            lines += [f"file '{pair[w % 2]}'", f"duration {hold / tempo:.4f}"]
            t += hold; w += 1
    lines.append(lines[-2])  # the concat demuxer drops the last duration without a closing file
    (build / "frames.txt").write_text("\n".join(lines) + "\n")
    voice.write_wav(build / "sfx.wav", sfx(events, total))

    out = SHORTS / f"{script['date']}{'-guides' if guides else ''}.mp4"
    print("encode…")
    # Fedora's ffmpeg ships without libx264, so take the first H.264 encoder that works
    encoders = (["libx264", "-preset", "medium", "-crf", "18"], ["h264_nvenc", "-preset", "p6", "-cq", "19"],
                ["libopenh264", "-b:v", "8M"])
    for enc in encoders:
        done = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(build / "frames.txt"),
             "-i", str(build / "voice.wav"), "-i", str(build / "sfx.wav"), "-filter_complex",
             f"[0:v]fps={FPS},scale=1080:1920,format=yuv420p[v];"
             f"[1:a]atempo={tempo},loudnorm=I=-15:TP=-1.5[vo];[2:a]atempo={tempo},volume=0.5[fx];"
             "[vo][fx]amix=inputs=2:duration=first:normalize=0,aresample=48000[a]",
             "-map", "[v]", "-map", "[a]", "-c:v", *enc, "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", "-shortest", str(out)], capture_output=True, text=True)
        if done.returncode == 0:
            break
    else:
        sys.exit("ffmpeg could not encode H.264:\n" + done.stderr[-600:])
    sheet = build / "sheet.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out), "-vf", "fps=1/2.5,scale=300:-1,tile=10x2",
                    "-frames:v", "1", str(sheet)], capture_output=True)
    print(f"sheet  {sheet.relative_to(ROOT)}")
    print(f"{out.relative_to(ROOT)}  {total / tempo:.1f}s  {out.stat().st_size / 1e6:.1f} MB")
    if guides:
        page = out
    else:
        page = handoff.build(script, apps)
        print(f"desk   {page.relative_to(ROOT)}")
    if show:
        subprocess.Popen(["xdg-open", str(page)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
