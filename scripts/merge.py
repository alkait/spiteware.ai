#!/usr/bin/env python3
"""Merge reviewed queue JSON into data/apps.json and data/rejected.json.

Usage: python3 scripts/merge.py [queue/YYYY-MM-DD.json]   (default: newest queue file)
       python3 scripts/merge.py --no-check [file]        skip the link check
       python3 scripts/merge.py --approve-all [file]     approve everything still pending first
approve -> apps.json, reject -> rejected.json, pending/edit stay in the queue.
Anything approved also rebuilds the hall of fame pages (scripts/pages.py).

An approved candidate with a dead link (scripts/links.py) is held in the queue, still
approved, rather than listed: fix the link in the desk and merge again. The ones that
make it get a Wayback Machine capture requested, so there is a copy the day they die.

--approve-all is the morning run's standing approval: every candidate the agent drafted
passed both hard gates, so the run lists them without waiting for the desk. It only
touches "pending"; a reject or an edit made in the desk stands.
"""
import json, sys, pathlib, datetime, importlib.util

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIELDS = ["slug", "name", "url", "icon", "tagline", "replaces", "grudge", "builder", "tags", "open_source", "vibe_coded", "repo", "spite_score", "added"]

def newest():
    files = sorted(p for p in (ROOT / "queue").glob("*.json") if not p.name.startswith("raw-"))
    return files[-1] if files else None

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M); return M

def merge(qf, check=True, approve_all=False):
    q = json.loads(qf.read_text())
    if approve_all:
        for c in q["candidates"]:
            if c.get("status", "pending") == "pending": c["status"] = "approve"
    apps_f, rej_f = ROOT / "data/apps.json", ROOT / "data/rejected.json"
    apps, rej = json.loads(apps_f.read_text()), json.loads(rej_f.read_text())
    slugs = {a["slug"] for a in apps}
    today = datetime.date.today().isoformat()
    kept, added, rejected, held, new = [], [], [], [], []
    for c in q["candidates"]:
        st = c.get("status", "pending")
        if st == "approve":
            if c["slug"] in slugs: kept.append(c); continue
            dead = load("links").dead_fields(c) if check else {}
            if dead: kept.append(c); held.append(f"{c['name']} ({', '.join(f'{k}: {v}' for k, v in dead.items())})"); continue
            a = {k: c.get(k) for k in FIELDS}; a["added"] = today
            a["replaces"] = {k: c["replaces"].get(k, "") for k in ("name", "product", "price", "source")}
            apps.append(a); slugs.add(a["slug"]); added.append(a["name"]); new.append(a)
        elif st == "reject":
            rej.append({"name": c["name"], "url": c["url"], "rejected": today}); rejected.append(c["name"])
        else:
            kept.append(c)
    q["candidates"] = kept
    apps_f.write_text(json.dumps(apps, indent=2, ensure_ascii=False) + "\n")
    rej_f.write_text(json.dumps(rej, indent=2, ensure_ascii=False) + "\n")
    qf.write_text(json.dumps(q, indent=2, ensure_ascii=False) + "\n")
    if added: load("pages").build()
    return {"approved": added, "rejected": rejected, "held": held, "pending": len(kept), "total_apps": len(apps), "new": new}

if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if x not in ("--no-check", "--approve-all")]
    qf = pathlib.Path(args[0]) if args else newest()
    if not qf: sys.exit("no queue file")
    r = merge(qf, check="--no-check" not in sys.argv, approve_all="--approve-all" in sys.argv)
    print(f"approved: {r['approved'] or 'none'}\nrejected: {r['rejected'] or 'none'}\nstill pending: {r['pending']}\napps listed: {r['total_apps']}")
    for h in r["held"]: print(f"HELD, dead link: {h}")
    if r["new"]:
        saved = load("links").archive(r["new"])
        print(f"wayback: {sum(saved.values())} of {len(saved)} captures requested" + ("" if all(saved.values()) else " (the rest failed; it is best effort)"))
