#!/usr/bin/env python3
"""Recompute spite_score from the fields, so it can't drift between runs.

The table lives in criteria.md; this is the executable copy of it.
Run with --write to apply, without to see what would change.
"""
import json, sys, pathlib

APPS = pathlib.Path(__file__).resolve().parent.parent / "data/apps.json"

def score(a):
    r = a.get("replaces") or {}
    return (3 * bool((a.get("grudge") or {}).get("quote", "").strip())
          + 2 * bool(a.get("open_source"))
          + 2 * bool(a.get("vibe_coded"))
          + 2 * bool((r.get("name") or "").strip())
          + 1 * bool((r.get("price") or "").strip()))

def main(write=False):
    apps = json.loads(APPS.read_text())
    drift = [(a["name"], a["spite_score"], score(a)) for a in apps if a["spite_score"] != score(a)]
    for n, was, now in drift:
        print(f"  {n:26} {was:2} -> {now:2}")
    print(f"{len(drift)} of {len(apps)} differ")
    if write and drift:
        for a in apps:
            a["spite_score"] = score(a)
        APPS.write_text(json.dumps(apps, indent=2, ensure_ascii=False) + "\n")
        print("written")
    elif drift:
        print("(dry run — pass --write to apply)")

if __name__ == "__main__":
    main("--write" in sys.argv)
