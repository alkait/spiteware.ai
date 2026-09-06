# What counts as spiteware

The agent scores every candidate against this file. Edit it to change what gets through.

## Hard gates (fail any one, reject)

1. **A named grudge.** The builder states, in their own words, the moment that made them build it: a price hike, a paywalled feature, a killed free tier, a "contact sales" button, a freemium nag. Quote it. "I wanted a self-hosted option" is not a grudge.
2. **A named victim with a current price.** One specific paid tool, one monthly (or yearly) price, verified today on the victim's own pricing page or a dated 2026 source. This becomes the strikethrough badge on the card.
3. **Free, no strings.** No trial, no seat cap, no "free for personal use", no pricing section anywhere on the app's own site. Open source preferred, not required. "Bring your own API key" is allowed if the key has a free tier.

## Automatic rejects

- Open-core: a free core with a paid tier from the same maker.
- VC-backed or YC-backed "open source alternative to X". Competitors, not grudges.
- Needs an email address or account before you can try it.
- Already in `data/apps.json` or `data/rejected.json`.

## Score (0 to 10, list at 6 or above)

| Signal | Points |
|---|---|
| Grudge is explicit and quotable | 3 |
| Victim price verified from a primary source | 2 |
| Solo builder or two people | 2 |
| Vibe coded or AI-assisted, stated by the builder | 2 |
| Does one thing | 1 |

## Voice for the card copy

Sarcastic, revenge-flavored, friendly. Short sentences. The joke is always the price, never the person. Never mock the builder. Name the victim tool plainly. One line of tagline, one quote from the builder, done.
