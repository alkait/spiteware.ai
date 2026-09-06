# spiteware.ai

A catalog of apps people built out of spite because a paid tool asked for money it didn't deserve.

- `index.html` — the whole site. No build step, no dependencies.
- `data/apps.json` — the listings. Hand-edited. The page renders from it.
- `data/rejected.json` — names the morning agent must not resurface.
- `criteria.md` — what counts as spiteware. The agent scores against it.
- `sources.md` — where the agent looks and what it searches for.
- `queue/` — one JSON file per morning run, awaiting approval.
- `scripts/sweep.py` — tier-1 source sweep. `scripts/review.py` — local review desk on port 4322. `scripts/merge.py` — moves approved entries into the data files.

Hosted on GitHub Pages straight from `main`.

## Morning routine

1. `/spite` in Claude Code. It sweeps, verifies, scores, and opens the review desk.
2. Approve, reject, or edit in the desk. Hit Merge.
3. Commit and push. Pages redeploys in about a minute.

## Run locally

```
python3 -m http.server 4321
```

Then open http://localhost:4321/. Opening `index.html` from `file://` will not load the JSON.
