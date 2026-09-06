# Morning queue

One JSON file per run: `queue/YYYY-MM-DD.json`. Review it in the desk, not by hand:

```
python3 scripts/review.py 4322    # then open http://localhost:4322/
```

The desk shows each candidate as the live card with its evidence, lets you edit any text inline, and has Approve, Reject, and Merge buttons. Merge moves approved candidates into `data/apps.json`, rejected names into `data/rejected.json`, and leaves pending ones in the queue. Push to publish.

Schema:

```json
{
  "run": "2026-09-06",
  "swept": "hn (48h), reddit rss, github, last30days",
  "raw_hits": 39, "triaged": 13,
  "candidates": [{
    "slug": "lag-writer", "name": "lag-writer", "status": "pending", "spite_score": 8,
    "url": "https://github.com/Kryhr/lag-writer", "icon": "✍️",
    "tagline": "one line in the site voice",
    "replaces": {"name": "Grammarly Pro", "price": "$12/mo", "source": "https://www.grammarly.com/plans", "note": ""},
    "grudge": {"quote": "builder's words, verbatim", "source": "https://..."},
    "builder": {"name": "Kryhr", "handle": "Kryhr", "url": ""},
    "tags": ["writing", "web"], "vibe_coded": false,
    "why": "score breakdown", "added": "2026-09-06"
  }],
  "dropped": ["Name: one-line reason"]
}
```

`raw-YYYY-MM-DD.json` files are the unfiltered sweep output and are git-ignored.
