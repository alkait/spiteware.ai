#!/usr/bin/env python3
"""Upload a daily short to YouTube: shorts/DATE.mp4, with the posting desk's title and description.

Usage: python3 scripts/upload.py [shorts/DATE.json] [--public | --unlisted | --at 2026-09-20T09:00]
       python3 scripts/upload.py --auth [client_secret.json]   # once: consent in the browser

Private unless told otherwise. The words are handoff.texts(), the same ones the posting desk
shows, so the desk is still the place to read them first. A vertical video under three
minutes is a Short; there is nothing to set. Each upload is noted in shorts/.cache/uploaded.json
and a second run for the same date refuses without --again.

Until the Cloud project passes YouTube's API audit, every upload is locked to private whatever
is asked for here, and going public is a click in Studio. The audit is a free form:
https://support.google.com/youtube/contact/yt_api_form

YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN and YOUTUBE_CHANNEL_ID live in
.env; --auth writes all four. The channel is whichever one was picked on the consent screen, and
every upload checks the token still belongs to it: a Google account can own several channels, and
picking the wrong one there once sent a short to the wrong place. Stdlib only, like everything else here. Running this is posting: never without the
user's word.
"""
import argparse, datetime, http.server, json, os, pathlib, secrets, subprocess, sys
import urllib.error, urllib.parse, urllib.request

import handoff

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHORTS = ROOT / "shorts"
ENV = ROOT / ".env"
DONE = SHORTS / ".cache" / "uploaded.json"
SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
TOKEN = "https://oauth2.googleapis.com/token"
CATEGORY = "28"  # Science & Technology


def env(name):
    v = os.environ.get(name)
    if not v and ENV.exists():
        for line in ENV.read_text().splitlines():
            if line.startswith(name + "="):
                v = line.split("=", 1)[1].strip()
    return v


def keep(pairs):
    """Write NAME=value lines into .env, replacing any that are already there."""
    lines = [l for l in (ENV.read_text().splitlines() if ENV.exists() else []) if l.split("=", 1)[0] not in pairs]
    ENV.write_text("\n".join(lines + [f"{k}={v}" for k, v in pairs.items()]) + "\n")
    ENV.chmod(0o600)


def post(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Google said no, HTTP {e.code}: {e.read()[:300].decode(errors='replace')}")


def auth(client_json):
    """The one-time consent: a browser tab, a loopback redirect, a refresh token into .env."""
    if client_json:
        c = json.loads(pathlib.Path(client_json).read_text()).get("installed")
        if not c:
            sys.exit('That is not a "Desktop app" OAuth client file: it has no "installed" block')
        keep({"YOUTUBE_CLIENT_ID": c["client_id"], "YOUTUBE_CLIENT_SECRET": c["client_secret"]})
    cid, secret = env("YOUTUBE_CLIENT_ID"), env("YOUTUBE_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit("No YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env: pass the downloaded client JSON to --auth")
    got, state = {}, secrets.token_urlsafe(16)

    class Back(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            got.update({k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Done. Back to the terminal.")
        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Back)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state})
    print(f"Pick the channel's account in the browser. If no tab opens:\n{url}")
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while "code" not in got and "error" not in got:
        srv.handle_request()
    if got.get("state") != state or "code" not in got:
        sys.exit(f"Consent did not finish: {got.get('error', 'the state did not match')}")
    tok = post(TOKEN, {"code": got["code"], "client_id": cid, "client_secret": secret,
                       "redirect_uri": redirect, "grant_type": "authorization_code"})
    if "refresh_token" not in tok:
        sys.exit(f"No refresh token came back: {tok}")
    cid_, title = channel(tok["access_token"])
    keep({"YOUTUBE_REFRESH_TOKEN": tok["refresh_token"], "YOUTUBE_CHANNEL_ID": cid_})
    print(f"Uploads will go to the channel {title!r} ({cid_}).\n"
          "Not the one you meant? Run --auth again and pick the other channel on the first Google screen.\n"
          "The tokens are in .env. Delete the downloaded client JSON; .env has what it held.")


def access():
    cid, secret, refresh = env("YOUTUBE_CLIENT_ID"), env("YOUTUBE_CLIENT_SECRET"), env("YOUTUBE_REFRESH_TOKEN")
    if not (cid and secret and refresh):
        sys.exit("No YouTube credentials in .env: run python3 scripts/upload.py --auth client_secret.json")
    return post(TOKEN, {"client_id": cid, "client_secret": secret, "refresh_token": refresh,
                        "grant_type": "refresh_token"})["access_token"]


def channel(token):
    """The (id, title) of the channel this token uploads to."""
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            items = json.loads(resp.read()).get("items") or []
    except urllib.error.HTTPError as e:
        if e.code == 403:
            sys.exit("This token cannot see which channel it uploads to (it predates the channel check).\n"
                     "Run python3 scripts/upload.py --auth once more and pick the channel you want.")
        sys.exit(f"YouTube said no, HTTP {e.code}: {e.read()[:300].decode(errors='replace')}")
    if not items:
        sys.exit("The account you picked has no YouTube channel. Run --auth again and pick the channel itself.")
    return items[0]["id"], items[0]["snippet"]["title"]


def upload(mp4, title, description, tags, privacy, at, token):
    """A resumable upload in two requests: the metadata, then the bytes. Returns the API's video."""
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    if at:
        status["publishAt"] = at
    meta = json.dumps({"snippet": {"title": title, "description": description, "tags": tags, "categoryId": CATEGORY},
                       "status": status}).encode()
    bearer, video = {"Authorization": f"Bearer {token}"}, mp4.read_bytes()
    start = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", data=meta,
        headers={**bearer, "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(len(video))})
    try:
        with urllib.request.urlopen(start, timeout=60) as resp:
            session = resp.headers["Location"]
        put = urllib.request.Request(session, data=video, method="PUT", headers={**bearer, "Content-Type": "video/mp4"})
        with urllib.request.urlopen(put, timeout=600) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"YouTube said no, HTTP {e.code}: {e.read()[:500].decode(errors='replace')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("script", nargs="?", help="shorts/DATE.json, default the newest; with --auth, the client JSON")
    ap.add_argument("--auth", action="store_true", help="one-time browser consent, writes the tokens to .env")
    ap.add_argument("--public", action="store_true", help="publish at once")
    ap.add_argument("--unlisted", action="store_true")
    ap.add_argument("--at", help="publish at this local time, e.g. 2026-09-20T09:00")
    ap.add_argument("--again", action="store_true", help="upload a date that was already uploaded")
    ap.add_argument("--dry", action="store_true", help="print what would go up, and send nothing")
    a = ap.parse_args()
    if a.auth:
        return auth(a.script)
    src = pathlib.Path(a.script) if a.script else max(SHORTS.glob("20*.json"))
    script = json.loads(src.read_text())
    mp4 = SHORTS / f"{script['date']}.mp4"
    if not mp4.exists():
        sys.exit(f"No {mp4.relative_to(ROOT)}: render it first with python3 scripts/short.py")
    done = json.loads(DONE.read_text()) if DONE.exists() else {}
    if script["date"] in done and not a.again:
        sys.exit(f"{script['date']} is already up: https://youtube.com/shorts/{done[script['date']]} (--again to upload it twice)")
    at = None
    if a.at:
        when = datetime.datetime.fromisoformat(a.at).astimezone()
        if when <= datetime.datetime.now().astimezone():
            sys.exit(f"--at {a.at} is in the past")
        at = when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # a scheduled video waits as private; YouTube flips it at publishAt
    privacy = "private" if at else "public" if a.public else "unlisted" if a.unlisted else "private"
    handoff.check(script)
    apps = {x["slug"]: x for x in json.loads((ROOT / "data" / "apps.json").read_text())}
    text = handoff.texts(script, apps)["youtube"]
    if a.dry:
        return print(f"{mp4.relative_to(ROOT)}, {mp4.stat().st_size / 1e6:.1f} MB, {privacy}{' until ' + at if at else ''}\n\n"
                     f"{text['title']}\n\n{text['description']}")
    token = access()
    want, (cid, name) = env("YOUTUBE_CHANNEL_ID"), channel(token)
    if cid != want:
        sys.exit(f"The token uploads to {name!r} ({cid}), but .env says {want or 'no channel'}. Nothing sent.\n"
                 "Run python3 scripts/upload.py --auth and pick the right channel.")
    print(f"Uploading to {name!r} ({cid})…")
    # the description ends with the hashtags; the tags field takes the same words bare
    video = upload(mp4, text["title"], text["description"], script["post"]["tags"], privacy, at, token)
    DONE.parent.mkdir(parents=True, exist_ok=True)
    DONE.write_text(json.dumps({**done, script["date"]: video["id"]}, indent=1) + "\n")
    landed = video["status"]["privacyStatus"]
    print(f"https://youtube.com/shorts/{video['id']}  ({landed}{', public at ' + a.at if at else ''})")
    print(f"https://studio.youtube.com/video/{video['id']}/edit")
    if landed != privacy:
        print(f"Asked for {privacy}, got {landed}: the project has not passed the API audit yet. Flip it in Studio.")


if __name__ == "__main__":
    main()
