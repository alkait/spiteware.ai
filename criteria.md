# What counts as spiteware

The agent scores every candidate against this file. Edit it to change what gets through.

## Hard gates (fail either one, reject)

1. **A grudge.** The builder states, in their own words, why they built it instead of paying: a price hike, a paywalled feature, a killed free tier, a "contact sales" button, a freemium nag, subscription fatigue. Quote one sentence verbatim. The quote may come from the HN post, the builder's comments, the README, or the app's own site. "I wanted a self-hosted option" alone is not a grudge, but "every tool for this wants a subscription" is.
2. **Free, no strings.** No trial, no seat cap, no pricing section anywhere on the app's own site. Open source preferred, not required. "Bring your own API key" is allowed if the key has a free tier. A noncommercial licence is allowed if the app is fully usable for free.

## Automatic rejects

- Open-core: a free core with a paid tier from the same maker.
- VC-backed or YC-backed "open source alternative to X". Competitors, not grudges.
- Needs an email address or account before you can try it.
- Already in `data/apps.json`, `data/rejected.json`, or a pending queue file.

## Victim and price (wanted, not required)

Record the paid tool the builder is reacting to when they name one, and its price when a pricing page or a dated 2026 source gives one. Leave `replaces.name` or `replaces.price` empty when unknown. Never guess a victim or a price.

## Score (0 to 10, for sorting; anything that passes both gates goes to review)

| Signal | Points |
|---|---|
| Grudge is explicit and quotable | 3 |
| Victim named by the builder | 1 |
| Victim price verified | 1 |
| Solo builder or two people | 2 |
| Vibe coded or AI-assisted, stated by the builder | 2 |
| Does one thing | 1 |

## Tags (closed list — never invent one)

Pick **at most 3**, only from this list. Nothing else is a tag. Anything else the app
is about — chess, expat life, minesweeper, WHOOP straps — is already findable through
search, which covers name, tagline, victim, builder and quote. A tag exists so somebody
can click it and get more than one app.

- **platform** (0 or 1): `macos` `ios` `windows` `web` `desktop` `browser-extension`
- **ethos** (0 to 2): `open-source` `self-hosted` `local-first` `byo-key` `privacy`
- **what it does** (exactly 1): `ai` `career` `dev-tools` `dictation` `finance` `forms`
  `games` `health` `images` `learning` `marketing` `productivity` `travel` `utilities`
  `video` `writing`

Use `utilities` when nothing else fits — do not add a seventeenth category. If a new
category is genuinely earning its keep (three or more apps stuck in `utilities` that
belong together), say so in the run report and let the human add it here.

Do not tag `vibe coded` — the site derives that button from the `vibe_coded` field.

## Voice for the card copy

Sarcastic, revenge-flavored, friendly. Short sentences. The joke is always the price, never the person. Never mock the builder. Name the victim tool plainly when there is one. One line of tagline, one quote from the builder, done.
