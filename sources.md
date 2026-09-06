# Where the agent looks each morning

Ordered by signal. Window: last 48 hours unless the run is catching up.

## Tier 1, no keys needed

- **Hacker News (Algolia API)**: `https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&query=<phrase>&numericFilters=created_at_i><unix>`
  Fetch the item with `/api/v1/items/<id>` to read the author's own comments.
- **Reddit JSON**: `https://www.reddit.com/r/<sub>/new.json?limit=100` for r/SideProject, r/selfhosted, r/opensource, r/webdev, r/macapps, r/vibecoding, r/ClaudeAI. Send a descriptive User-Agent.
- **GitHub search**: `https://api.github.com/search/repositories?q=<phrase>+created:><date>&sort=stars`

## Tier 2, wide net

- **last30days skill**: one run per morning, query "free alternative built because subscription price". Take its top clustered hits and push them through the same filter.

## Tier 3, noisy

- Product Hunt, Indie Hackers, Bluesky search. Only when tiers 1 and 2 come back thin.

## Grudge phrases

Search each of these against every tier 1 source:

- "free alternative to"
- "tired of paying"
- "sick of paying"
- "refused to pay"
- "no subscription"
- "no paywall"
- "killed the free tier" / "removed the free plan"
- "went paid" / "now charges"
- "vibe coded" + "free"
- "built in a weekend" + "free"
- "why pay"
- "upgrade to pro"

## Verification, per candidate

1. Open the app's own site. Look for a pricing section, a trial, a seat cap. Any of these fails gate 3.
2. Open the victim's pricing page. Record the plan name, monthly price, and URL.
3. Read the builder's post and comments. Copy the grudge sentence verbatim.
4. Check `data/apps.json` and `data/rejected.json` for the slug or URL.
