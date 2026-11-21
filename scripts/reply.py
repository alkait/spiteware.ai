#!/usr/bin/env python3
"""Answer someone who wrote to hello@spiteware.ai, from spiteware.ai, through Resend.

The /spite inbox mode writes the words; this only sends them, once:

    python3 scripts/reply.py --to them@example.com --subject "Re: ..." --key <gmail thread id> < body.txt
    python3 scripts/reply.py ... --dry          # print what would go out, send nothing

It goes out as "spiteware.ai <hello@send.spiteware.ai>" with Reply-To hello@spiteware.ai, so
an answer lands back in the inbox the run reads. Never from the user's own Gmail. Each --key
is noted in shorts/.cache/replied.json and a second send with the same key is refused, so a
re-run never answers the same email twice. RESEND_API_KEY is in .env.
"""
import argparse, datetime, json, sys, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "shorts" / ".cache" / "replied.json"
FROM = "spiteware.ai <hello@send.spiteware.ai>"
REPLY_TO = "hello@spiteware.ai"


def env(name):
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"')
    sys.exit(f"{name} is not in .env")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--to", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--key", required=True, help="the Gmail thread id (or any id) of the email being answered")
    p.add_argument("--dry", action="store_true")
    a = p.parse_args()
    body = sys.stdin.read().strip()
    if not body:
        sys.exit("no body on stdin")
    done = json.loads(LOG.read_text()) if LOG.exists() else {}
    if a.key in done:
        sys.exit(f"already answered {a.key} on {done[a.key]['at']}; not sending again")
    if a.dry:
        print(f"From: {FROM}\nReply-To: {REPLY_TO}\nTo: {a.to}\nSubject: {a.subject}\n\n{body}")
        return
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps({"from": FROM, "to": [a.to], "reply_to": REPLY_TO,
                         "subject": a.subject, "text": body}).encode(),
        headers={"Authorization": f"Bearer {env('RESEND_API_KEY')}",
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
