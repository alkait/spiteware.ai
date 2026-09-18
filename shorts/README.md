# Daily shorts

One narration script per merge day, `shorts/YYYY-MM-DD.json`, rendered to `shorts/YYYY-MM-DD.mp4`
(gitignored, like the voice cache and build files). The scripts are committed: they are the
record of what was said about whom.

```
python3 scripts/short.py --open              # newest script -> mp4, then open its posting desk
python3 scripts/short.py --reroll jinx       # voice one segment again, keep the rest
python3 scripts/short.py --guides            # same cut with the platform UI zones drawn on
python3 scripts/handoff.py --open            # rebuild just the posting desk, no render
```

One 1080x1920 H.264 file, made for Shorts, TikTok and Reels alike. Voice: Gemini 3.1 Flash TTS,
voice Aoede, through OpenRouter (`OPENROUTER_API_KEY` in `.env`), about 2 cents a short. Needs
`firefox` and `ffmpeg`. **Rendering is local and free to repeat; uploading is the user's call,
every time, like a push.**

Every render ends by writing the **posting desk**, `shorts/YYYY-MM-DD.html` (gitignored): the
video, the text for YouTube Shorts, TikTok and Instagram Reels behind Copy buttons, a link to
each upload screen and the settings to tick there. Posting is by hand, by the user. YouTube and
TikTok lock API uploads from an unaudited app to private, so there is no uploader, and no
agent posts anything.

## Script

```json
{
  "date": "2026-09-18",
  "style": "[fast-paced, quick delivery, dry, amused, deadpan]",
  "more": 0,
  "post": {
    "title": "Bitly wants $10 a month. Jinx is a text file.",
    "caption": "Three fresh grudges, each replaced by someone annoyed enough to build the free version.",
    "tags": ["freesoftware", "opensource", "indiedev", "subscriptions", "selfhosted"]
  },
  "segments": [
    {"scene": "hook", "cues": [
      {"cap": "Fresh spite.", "step": "stamp"},
      {"cap": "September 18th.", "say": "September eighteenth.", "step": "date"},
      {"cap": "Three new grudges.", "step": "count"}]},
    {"scene": "app", "slug": "jinx",
     "quote": "Paid link shorteners cost money every month for something that's really just a lookup table.",
     "cues": [
      {"cap": "Bitly wants $10 a month", "say": "Bitly wants ten dollars a month", "step": "badge"},
      {"cap": "to shorten a link.", "step": "badge"},
      {"cap": "Gordon McDonald:", "say": "[matter-of-fact] Gordon McDonald:", "step": "quote"},
      {"cap": "“Paid link shorteners cost money every month", "say": "[sarcastic] Paid link shorteners cost money every month", "step": "quote"},
      {"cap": "for something that's really just a lookup table.”", "say": "for something that's really just a lookup table.", "step": "quote"},
      {"cap": "So: Jinx. A text file.", "say": "[quick] So: Jinx. A text file.", "step": "app"},
      {"cap": "Free.", "say": "[smug] Free.", "step": "free"}]},
    {"scene": "outro", "cues": [
      {"cap": "All free.", "step": "free"},
      {"cap": "All built out of pure spite.", "step": "spite"},
      {"cap": "More grudges daily", "say": "[upbeat] More grudges daily,", "step": "url"},
      {"cap": "at spiteware.ai", "say": "at spiteware dot A I.", "step": "url"}]}
  ]
}
```

`shorts/2026-09-18.json` is the reference script. Copy its shape.

- A **segment** is one voice take. A **cue** is one caption and one still; `step` says what the
  frame shows. Steps run in order and never go back: hook `stamp → date → count`; app
  `badge` (or `gripe`) `→ quote → app → free`; outro `free → spite → url`.
- `cap` is the caption on screen. `say` is what the voice reads, when it differs: numbers and
  prices spelled out ("ten dollars a month"), names spelled the way they sound ("mock-freely",
  "Lazy Map Layers"), and delivery cues in `[square brackets]`. Without `say`, `cap` is read.
- `quote` is a **verbatim, unbroken** stretch of the app's `grudge.quote`; the render refuses
  anything else. Trim a long quote to its first clause and set `"cut": true` for the ellipsis.
  The quote cues' captions must be pieces of that text, in order: the frame highlights them as read.
- No victim or price in `replaces`? Open with `gripe` instead of `badge` and give the segment a
  `"gripe"`: the complaint in one short sentence, no invented victim, no invented price.
- `"score": false` keeps the spite meter off screen. Use it under 6: a low score on a video
  reads as a dig at the builder, and the joke is the price, never the person.
- `more` is how many of the day's apps did not make the cut; the end card shows "+N more fresh
  today". When it is above zero, say so in the outro ("Plus four more, at spiteware dot A I.").

- `post` is the text that goes out with the video, and the render refuses a script without
  it. `title`: 10 to 70 characters, the top app's bill against its price of nothing; it is the
  YouTube title and the first line everywhere else. `caption`: one or two sentences, 40 to 300
  characters, on what the day's apps replace. `tags`: 3 to 5 lowercase hashtags without the `#`;
  keep `freesoftware`, `indiedev` and `subscriptions`, and spend the rest on the day's apps.
  No links and no app list in either: `scripts/handoff.py` adds the apps, the builder credits
  and the hall of fame links from `data/apps.json`. Same rules as the narration: only prices and
  victims that are in `replaces`, no pronouns for builders. No @-tags: a GitHub handle is
  somebody else's name on TikTok.

## Writing one

- **Top 3** of the day's merged apps by `spite_score`; on a tie, the one with a filled
  `replaces` wins, because the struck-out bill is the best frame. The rest go in `more`.
- **Under 50 seconds**, which is about 110 spoken words in all. Around 30 per app: the bill and
  what it buys, the builder's name, the quote, the app, "Free." The render prints the length.
- Captions of 8 words or fewer. Split a sentence across cues at its commas.
- The site voice from `criteria.md`: sarcastic, revenge-flavoured, friendly.
- **Never a pronoun for a builder.** We do not know them. "Enter Jinx.", "So: Jinx.", not "so he built".
- Never say or show a price, victim or quote that is not in `data/apps.json`.

## Checking a render

Read `shorts/.build/DATE/sheet.png` after every render: a frame every 2.5 seconds. Look for text
running out of its box or past the right edge, a missing avatar, a caption over three lines.
Nobody but the user can hear it, so tell them what to listen for: that "Free." lands on the
stamp, and each name you spelled phonetically.
