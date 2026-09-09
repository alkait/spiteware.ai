#!/usr/bin/env python3
"""Star listed open-source apps from the signed-in GitHub account.

Usage: python3 scripts/star.py [--dry-run] [--delay SECONDS]

As a script it works off data/apps.json rather than a queue file, so it
self-heals: anything an earlier run missed gets picked up on the next one.
As a module it backs the review desk's Approve button via star_one().
Idempotent either way — it only writes the difference.
"""
import json, pathlib, subprocess, shutil, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent


def gh(*args, timeout=30):
    """Run gh, return (ok, stdout). A 404 is data here, not an error."""
    try:
        p = subprocess.run(("gh",) + args, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, ""
    return p.returncode == 0, p.stdout.strip()


def preflight():
    """Returns an error string, or None when gh is usable."""
    if not shutil.which("gh"):
        return ("gh not on PATH. It is a mise install here, so a bare cron shell will "
                "not see it; run from an interactive shell or use an absolute path.")
    return None if gh("auth", "status")[0] else "gh is not authenticated. Run: gh auth login"


def canonical(repo):
    """Canonical owner/name, or None if it cannot be resolved. Repos get renamed."""
    ok, full = gh("api", f"repos/{repo}", "--jq", ".full_name")
    return full if ok and full else None


def star_one(repo, timeout=20):
    """Star a single repo. Returns (state, detail) for display.

    state is one of: already, starred, gone, failed. The starred-check endpoint
    follows rename redirects on its own, so it is asked first and a rename costs
    nothing on the common path.
    """
    repo = (repo or "").strip()
    if not repo:
        return "skipped", "no repo"
    err = preflight()
    if err:
        return "failed", err
    if gh("api", f"/user/starred/{repo}", "--silent", timeout=timeout)[0]:
        return "already", repo
    full = canonical(repo)
    if not full:
        return "gone", f"{repo} — deleted, private, or a typo"
    ok, _ = gh("api", "--method", "PUT", f"/user/starred/{full}", timeout=timeout)
    if not ok:
        return "failed", full
    return "starred", full if full.lower() == repo.lower() else f"{full} (renamed from {repo})"


def starred_set():
    ok, out = gh("api", "--paginate", "/user/starred", "--jq", ".[].full_name", timeout=120)
    if not ok:
        sys.exit("could not read your starred list")
    return {n.lower() for n in out.splitlines() if n}


def main():
    dry = "--dry-run" in sys.argv
    delay = float(sys.argv[sys.argv.index("--delay") + 1]) if "--delay" in sys.argv else 4.0

    err = preflight()
    if err:
        sys.exit(err)

    apps = json.loads((ROOT / "data/apps.json").read_text())
    repos = [(a["slug"], a["repo"].strip()) for a in apps if (a.get("repo") or "").strip()]
    have = starred_set()

    todo, already, renamed, gone = [], [], [], []
    for slug, repo in repos:
        if repo.lower() in have:
            already.append(repo)
            continue
        # Not starred under the configured name — it may just have been renamed, and
        # re-PUTting a renamed repo every single run would be pure noise. Resolve first.
        full = canonical(repo)
        if not full:
            gone.append((slug, repo))
            continue
        if full.lower() != repo.lower():
            renamed.append((slug, repo, full))
        (already if full.lower() in have else todo).append(full)

    print(f"listed repos: {len(repos)} · already starred: {len(already)} · to star: {len(todo)}")
    for slug, repo in gone:
        print(f"  UNRESOLVABLE  {repo}  ({slug}) — deleted, private, or a typo")
    for slug, repo, full in renamed:
        print(f"  RENAMED       {repo} -> {full}  ({slug}) — update data/apps.json")

    if dry:
        for r in todo:
            print(f"  would star    {r}")
        return 0

    failed = []
    for i, repo in enumerate(todo):
        ok, _ = gh("api", "--method", "PUT", f"/user/starred/{repo}")
        print(f"  {'starred      ' if ok else 'FAILED       '} {repo}")
        if not ok:
            failed.append(repo)
        if i < len(todo) - 1:
            time.sleep(delay)  # paced so a big backfill does not look like abuse

    print(f"done — starred:{len(todo) - len(failed)} already:{len(already)} "
          f"failed:{len(failed)} unresolvable:{len(gone)}")
    return 1 if failed or gone else 0


if __name__ == "__main__":
    sys.exit(main())
