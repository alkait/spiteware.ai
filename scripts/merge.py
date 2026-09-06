#!/usr/bin/env python3
"""Merge a reviewed queue file into data/apps.json and data/rejected.json.

Usage: python3 scripts/merge.py queue/YYYY-MM-DD.md
Blocks with `status: approve` go to apps.json, `status: reject` to rejected.json.
`pending` and `edit` blocks stay in the queue file untouched.
"""
import json, re, sys, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEAD = re.compile(r"^## (?P<name>.+?)\s+status:\s*(?P<status>\w+)\s+score:\s*(?P<score>\d+)/10\s*$", re.M)

def parse(md):
    blocks = []
    heads = list(HEAD.finditer(md))
    for i, h in enumerate(heads):
        body = md[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(md)]
        fields = {}
        for line in body.splitlines():
            m = re.match(r"^(\w+):\s*(.*)$", line)
            if m: fields[m.group(1)] = m.group(2).strip(); last = m.group(1)
            elif line.strip() and 'last' in dir() and line.startswith(" "):
                fields[last] += " " + line.strip()
        blocks.append({"name": h.group("name").strip(), "status": h.group("status").lower(),
                       "score": int(h.group("score")), "raw": md[h.start(): h.end() + len(body)], **fields})
    return blocks

def to_app(b):
    rep = re.match(r"^(?P<n>.+?)\s*·\s*(?P<p>\$[\d.,]+/\w+)\s*(?:\(source:\s*(?P<s>\S+?)\)?)?\s*$", b.get("replaces", ""))
    g_src = re.search(r"source:\s*(\S+)", b.get("grudge", "") + " " + b.get("grudge_source", ""))
    quote = re.sub(r'\s*source:\s*\S+\s*$', "", b.get("grudge", "")).strip().strip('"“”')
    bm = re.match(r"^(?P<n>.+?)\s*(?:\(@(?P<h>[\w.-]+)\))?\s*$", b.get("builder", ""))
    return {
        "slug": re.sub(r"[^a-z0-9]+", "-", b["name"].lower()).strip("-"),
        "name": b["name"], "url": b.get("url", ""), "icon": b.get("icon", "🔧"),
        "tagline": b.get("tagline", ""),
        "replaces": {"name": rep.group("n") if rep else b.get("replaces", ""), "price": rep.group("p") if rep else "", "source": (rep.group("s") if rep else "") or ""},
        "grudge": {"quote": quote, "source": g_src.group(1) if g_src else b.get("discussion", "")},
        "builder": {"name": bm.group("n") if bm else b.get("builder", ""), "handle": (bm.group("h") if bm else "") or "", "url": b.get("builder_url", "")},
        "tags": [t.strip() for t in b.get("tags", "").split(",") if t.strip()],
        "vibe_coded": b.get("vibe", "no").lower().startswith("y"),
        "spite_score": b["score"], "added": datetime.date.today().isoformat(),
    }

def main():
    qf = pathlib.Path(sys.argv[1]); md = qf.read_text()
    apps_f, rej_f = ROOT / "data/apps.json", ROOT / "data/rejected.json"
    apps, rej = json.loads(apps_f.read_text()), json.loads(rej_f.read_text())
    slugs = {a["slug"] for a in apps}
    kept, added, rejected = [], [], []
    for b in parse(md):
        if b["status"] == "approve":
            a = to_app(b)
            if a["slug"] in slugs: print(f"skip {a['name']}: already listed"); kept.append(b["raw"]); continue
            apps.append(a); slugs.add(a["slug"]); added.append(a["name"])
        elif b["status"] == "reject":
            rej.append({"name": b["name"], "url": b.get("url", ""), "rejected": datetime.date.today().isoformat()}); rejected.append(b["name"])
        else:
            kept.append(b["raw"])
    apps_f.write_text(json.dumps(apps, indent=2, ensure_ascii=False) + "\n")
    rej_f.write_text(json.dumps(rej, indent=2, ensure_ascii=False) + "\n")
    header = md[: HEAD.search(md).start()] if HEAD.search(md) else md
    qf.write_text(header.rstrip() + "\n\n" + "\n".join(k.rstrip() + "\n" for k in kept) if kept else header.rstrip() + "\n\n_All reviewed and merged._\n")
    print(f"approved: {added or 'none'}\nrejected: {rejected or 'none'}\nstill pending: {len(kept)}")

if __name__ == "__main__":
    main()
