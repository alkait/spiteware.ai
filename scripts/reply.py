#!/usr/bin/env python3
"""Answer someone who wrote to spiteware, from spiteware.ai, through Resend.

The /spite inbox mode writes the words; this checks them and sends them, once:

    python3 scripts/reply.py --to them@example.com --subject "Re: ..." --key <gmail message id> < body.txt
    python3 scripts/reply.py ... --dry          # run every check, print what would go out, send nothing

It goes out as "spiteware.ai <hello@send.spiteware.ai>" with Reply-To hello@spiteware.ai, and
a Bcc to hello@spiteware.ai, so the iCloud rule drops a copy into the user's Gmail: that is
the user's Sent folder for spiteware. Never from the user's own Gmail.

The guardrails are here, not only in the skill, so a message that talked the agent into
something still cannot get it out the door. It refuses:
  - a second answer to the same --key (a re-run never answers the same email twice)
  - more than PER_PERSON replies to one address in a week, and more than PER_DAY in a day
    (no ping-pong with an auto-responder, no flood)
  - recipients that are spiteware itself, the user, or a robot (noreply, mailer-daemon, ...)
  - a body that contains a secret from .env (keys, tokens, passwords, login emails), the user's own address, or a word about the
    machinery behind the site (see INTERNAL)
  - a link to anywhere but spiteware.ai, github.com, or a site already on a card
Sent replies are noted in shorts/.cache/replied.json. RESEND_API_KEY is in .env.
"""
import argparse, datetime, json, re, subprocess, sys, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "shorts" / ".cache" / "replied.json"
FROM = "spiteware.ai <hello@send.spiteware.ai>"
INBOX = "hello@spiteware.ai"
PER_PERSON, PER_DAY = 3, 20
ROBOTS = re.compile(r"(no-?reply|do-?not-?reply|mailer-daemon|postmaster|bounce|notifications?@)", re.I)
SECRET = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSCODE|CLIENT_ID|CHAT_ID|EMAIL|_TO$")
INTERNAL = re.compile(r"""claude|anthropic|openrouter|resend|telegram|tailscale|tailnet|raspberry|
    \bpi\b|claude-pi|systemd|autorun|\.env\b|api[_ ]?key|token|password|credential|secret|
    system\ prompt|skill\.md|\bprompt\b|/home/|scripts/|\.py\b|\.sh\b|\bvnc\b|port\ 9222""", re.I | re.X)


def env():
    vals = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return vals


def own_addresses(vals):
    """The user's own addresses: never a recipient, never in a body."""
    mine = {v.lower() for v in vals.values() if re.fullmatch(r"[^@\s]+@[^@\s]+\.\w+", v)}
    try:
        mine.add(subprocess.run(["git", "config", "user.email"], cwd=ROOT, capture_output=True,
                                text=True).stdout.strip().lower())
    except OSError:
        pass
    return {m for m in mine if m}


def allowed_hosts():
    hosts = {"spiteware.ai", "github.com"}
    for a in json.loads((ROOT / "data" / "apps.json").read_text()):
        for u in (a.get("url"), (a.get("builder") or {}).get("url")):
            if u:
                hosts.add(urlparse(u).hostname or "")
    return {h.removeprefix("www.") for h in hosts if h}


def check(to, body, done, vals):
    """Every reason not to send, or [] when it may go."""
    why, to_l, now = [], to.lower(), datetime.datetime.now().astimezone()
    mine = own_addresses(vals)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.\w+", to):
        why.append(f"{to!r} is not an email address")
    if to_l.endswith(("@spiteware.ai", ".spiteware.ai")) or to_l in mine or ROBOTS.search(to_l):
        why.append(f"{to} is spiteware, the user or a robot")
    week = [d for d in done.values() if d["to"].lower() == to_l
            and now - datetime.datetime.fromisoformat(d["at"]) < datetime.timedelta(days=7)]
    if len(week) >= PER_PERSON:
        why.append(f"already {len(week)} replies to {to} this week: the user takes it from here")
    today = [d for d in done.values() if d["at"][:10] == now.date().isoformat()]
    if len(today) >= PER_DAY:
        why.append(f"{len(today)} replies today is the cap")
    low = body.lower()
    if any(len(v) >= 6 and v.lower() in low for k, v in vals.items() if SECRET.search(k)):
        why.append("the body contains a secret from .env")
    if any(m in low for m in mine):
        why.append("the body contains the user's own address")
    m = INTERNAL.search(body)
    if m:
        why.append(f"the body talks about the machinery ({m.group(0)!r})")
    hosts = allowed_hosts()
    for u in re.findall(r"https?://[^\s<>()\"']+", body):
        h = (urlparse(u).hostname or "").removeprefix("www.")
        if h not in hosts and not h.endswith(".spiteware.ai"):
            why.append(f"links to {h}, which is on no card")
    return why


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--to", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--key", required=True, help="the Gmail message id of the email being answered")
    p.add_argument("--dry", action="store_true")
    a = p.parse_args()
    body = sys.stdin.read().strip()
    if not body:
        sys.exit("no body on stdin")
    done = json.loads(LOG.read_text()) if LOG.exists() else {}
    if a.key in done:
        sys.exit(f"already answered {a.key} on {done[a.key]['at']}; not sending again")
    vals = env()
    why = check(a.to, a.subject + "\n" + body, done, vals)
    if why:
        sys.exit("NOT SENT: " + "; ".join(why))
    if a.dry:
        print(f"From: {FROM}\nReply-To: {INBOX}\nTo: {a.to}\nBcc: {INBOX}\nSubject: {a.subject}\n\n{body}")
        return
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps({"from": FROM, "to": [a.to], "bcc": [INBOX], "reply_to": INBOX,
                         "subject": a.subject, "text": body}).encode(),
        headers={"Authorization": f"Bearer {vals['RESEND_API_KEY']}",
                 "Content-Type": "application/json", "User-Agent": "spiteware-reply"})
    try:
        sent = json.loads(urllib.request.urlopen(req, timeout=30).read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Resend refused it: {e.code} {e.read().decode()}")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    done[a.key] = {"to": a.to, "subject": a.subject, "id": sent.get("id"),
                   "at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
    LOG.write_text(json.dumps(done, indent=2) + "\n")
    print(f"sent to {a.to}: {sent.get('id')}")


if __name__ == "__main__":
    main()
