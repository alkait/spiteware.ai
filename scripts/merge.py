#!/usr/bin/env python3
"""Merge reviewed queue JSON into data/apps.json and data/rejected.json.

Usage: python3 scripts/merge.py [queue/YYYY-MM-DD.json]   (default: newest queue file)
approve -> apps.json, reject -> rejected.json, pending/edit stay in the queue.
"""
import json, sys, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIELDS = ["slug", "name", "url", "icon", "tagline", "replaces", "grudge", "builder", "tags", "open_source", "vibe_coded", "spite_score", "added"]

def newest():
    files = sorted(p for p in (ROOT / "queue").glob("*.json") if not p.name.startswith("raw-"))
    return files[-1] if files else None

def merge(qf):
    q = json.loads(qf.read_text())
    apps_f, rej_f = ROOT / "data/apps.json", ROOT / "data/rejected.json"
    apps, rej = json.loads(apps_f.read_text()), json.loads(rej_f.read_text())
    slugs = {a["slug"] for a in apps}
    today = datetime.date.today().isoformat()
    kept, added, rejected = [], [], []
    for c in q["candidates"]:
        st = c.get("status", "pending")
        if st == "approve":
            if c["slug"] in slugs: kept.append(c); continue
            a = {k: c.get(k) for k in FIELDS}; a["added"] = today
            a["replaces"] = {k: c["replaces"].get(k, "") for k in ("name", "price", "source")}
            apps.append(a); slugs.add(a["slug"]); added.append(a["name"])
        elif st == "reject":
            rej.append({"name": c["name"], "url": c["url"], "rejected": today}); rejected.append(c["name"])
        else:
            kept.append(c)
    q["candidates"] = kept
    apps_f.write_text(json.dumps(apps, indent=2, ensure_ascii=False) + "\n")
    rej_f.write_text(json.dumps(rej, indent=2, ensure_ascii=False) + "\n")
    qf.write_text(json.dumps(q, indent=2, ensure_ascii=False) + "\n")
    return {"approved": added, "rejected": rejected, "pending": len(kept), "total_apps": len(apps)}

if __name__ == "__main__":
    qf = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else newest()
    if not qf: sys.exit("no queue file")
    r = merge(qf)
    print(f"approved: {r['approved'] or 'none'}\nrejected: {r['rejected'] or 'none'}\nstill pending: {r['pending']}\napps listed: {r['total_apps']}")
