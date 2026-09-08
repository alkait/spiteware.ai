# Where the agent looks each morning

Ordered by signal. Window: last 48 hours unless the run is catching up.

## Tier 1, no keys needed

- **Hacker News (Algolia API)**: `https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&numericFilters=created_at_i><unix>&hitsPerPage=200&page=<n>`
  No `query` — take **every** Show HN in the window and triage it. Phrase queries here
  cost us the grudges worded any other way ("prohibitively expensive", "they added paid
  tiers"). Fetch the item with `/api/v1/items/<id>` to read the author's own comments.
- **Reddit JSON**: `https://www.reddit.com/r/<sub>/new.json?limit=100` for r/SideProject, r/selfhosted, r/opensource, r/webdev, r/macapps, r/vibecoding, r/ClaudeAI. Send a descriptive User-Agent.
- **GitHub search**: `https://api.github.com/search/repositories?q=<phrase>+created:><date>&sort=stars`

## Tier 2, wide net

- **last30days skill**: one run per morning, query "free alternative built because subscription price". Take its top clustered hits and push them through the same filter.

## Tier 3, noisy

- Product Hunt, Indie Hackers, Bluesky search. Only when tiers 1 and 2 come back thin.

## Grudge phrases

These are a **hint, not a gate**. Show HN arrives whole and these only sort it; on Reddit
and GitHub they are still the filter, so keep them wide. Measured against the grudge
quotes already listed, this vocabulary recognises 40 of 41 — the one it misses ("I wanted
a version of Nomad List that was free") is the reminder that the agent reading the post is
the real detector:

- refusing to pay: "tired of paying", "sick of paying", "refused to pay", "don't want to
  pay", "wanna pay", "instead of paying", "why pay", "pay monthly", "pay $"
- the pricing itself: "subscription", "paywalled", "freemium", "free tier", "paid tier",
  "pro plan", "premium version", "went paid", "now charges", "price hike", "per seat",
  "per user", "add-on pricing", "contact sales", "pricing page", "$14.99/mo"
- the feeling: "expensive", "overpriced", "prohibitively", "costs money", "too limited",
  "limited free", "with ads", "enshittification", "rug pull"
- the build: "free alternative", "open source alternative", "self-hosted alternative",
  "free forever", "vibe coded", "weekend"

The live list is `GRUDGE_RE` in `scripts/sweep.py`. When a listed app's own words would not
have matched it, add them.

## Verification, per candidate

1. Open the app's own site. Look for a pricing section, a trial, a seat cap. Any of these fails gate 3.
2. Open the victim's pricing page. Record the plan name, monthly price, and URL.
3. Read the builder's post and comments. Copy the grudge sentence verbatim.
4. Check `data/apps.json` and `data/rejected.json` for the slug or URL.
