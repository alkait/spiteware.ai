# The monthly episode

One script per month, `episodes/YYYY-MM.json`, rendered to `episodes/YYYY-MM.mp4` (gitignored, like
the build files). The scripts are committed: they are the record of what was said about whom, and
the memory the next episode is checked against.

```
python3 scripts/episode.py --measure        # newest script: voice it, print each segment's length
python3 scripts/episode.py --stills         # one still per kind of frame, to look at first
python3 scripts/episode.py --secs 40        # just the opening, as episodes/YYYY-MM-sample.mp4
python3 scripts/episode.py --open           # the whole thing, then open it
```

One 1920x1080 H.264 file for YouTube, about five minutes: two hosts, Vera and Gus, talking through
the month's apps. Voices are Gemini 3.1 Flash TTS through OpenRouter (`OPENROUTER_API_KEY` in
`.env`), about 4 cents per finished minute; every line is cached, so a re-render only pays for the
lines that changed. Needs `firefox` and `ffmpeg`. A full render takes about five minutes.
**Rendering is local and free to repeat. Uploading is the user's call, every time**: the morning
run's standing exception does not cover the monthly episode.

```
python3 scripts/upload.py episodes/2026-09.json --dry       # print what would go up, send nothing
python3 scripts/upload.py episodes/2026-09.json             # upload it, private
python3 scripts/upload.py episodes/2026-09.json --public    # or --unlisted, or --at 2026-10-07T09:00
```

It goes up as an ordinary video with the title, chapters and app links from
`episodes/.build/YYYY-MM/description.txt`, and the title card as its thumbnail. Each upload is
noted in `shorts/.cache/uploaded.json`, so a month never goes up twice (`--again` overrides).

Read these before writing one, in this order:

1. This file: the format and the rules. The rules came out of four rounds of the user watching
   cuts and saying what was wrong, so each one is here because its opposite was tried.
2. `episodes/hosts.md`: who Vera and Gus are, what has been said on air, how they talk.
3. `episodes/ledger.md`: what earlier episodes used up, and what is still unused.
4. The newest `episodes/*.json`: the reference script. Copy its shape, never its lines.

## The shape of an episode

About 800 words and 20 apps. In order:

| Part | What happens |
|---|---|
| Settle in | One light line. "Okay. Everybody settled? Here we go." was September's; write a new one. |
| Welcome | "This is Spiteware Monthly." Welcome everybody, wish them something, say what they are about to get. |
| The running bit | One or two lines that set up a small story about a host, paid off in the outro. |
| The apps | Grouped by the pattern behind the grudge ("it used to be free", "the last button"), three to five groups. |
| Wall of shame | The month's most replaced product, with the count and the replacements on screen. |
| On the site | One thing about spiteware.ai, about 20 seconds, played for a laugh. A different thing every month. |
| Outro | Pay off the running bit. Gus picks the spite of the month. Ask what they would use, ask them to subscribe and hit the bell, sign off with a callback. |

## Rules

**Length.** Aim for 5:00 and stay under 5:45. The render prints the length and complains past it.
When it runs long, cut an app or a line; never the breaths between apps.

**Report the gist; do not read quotes.** For each app: what it replaces, the price, the grudge in
one sentence, who built it, what it is called. No verbatim quote read aloud, and no host comment
after every app. More software beats lingering on one.

**A breath and a lead-in between apps.** Half a second of air (`<gap 0.6>`), then one short line
that brings in the next app, then the bill. Write each lead-in fresh for the app it introduces
("Okay. Same story, bigger bill.", "This one is loud."). Let Gus ask for some of them ("Who else
pulls that?"). **Never the same lead-in twice, in an episode or across episodes**: the render lists
any line an earlier episode said word for word.

**Talk to the viewer about four times**, differently each time: would they use it, are they paying
for this right now, tell us which one. A 💬 sticker goes with it.

**Side stories are two lines, not a scene.** At most three per episode, one or two lines each, and
only where an app gives a reason. A story that needed a card on screen to follow was too long.

**No laughs.** No `[laughs]` cues: they sound forced. Keep delivery cues out of the script
altogether; the hosts' styles are set once in `hosts.json`.

**The site moment is light.** One feature of the site, said the way a friend would mention it,
with a joke in it. Put its name in the script's `"site_tips"`; the render refuses one that an
earlier episode used. `ledger.md` lists what is left.

**Only what the card says.** A price, a victim or a reason is said only if it is in
`data/apps.json` for that app. Never a pronoun for a builder: we do not know them. A host's own
story never names a real product or company. The joke is the price, never the person.

**Counts come from the data.** Write `{LIVE}` for the month's app count and `{MORE}` for the ones
not named; the render fills both in and says them as words.

## Script

```json
{
 "month": "2026-09",
 "tempo": 1.06,
 "wall": "Wispr Flow",
 "site_tips": ["search", "manifesto"],
 "post": {"title": "…", "caption": "…", "tags": ["freesoftware", "…"]},
 "shots": {"some-slug": "https://github.com/owner/repo"},
 "say": [["$4.99", "four ninety-nine"], ["Spliit", "Split"]],
 "segments": [
  {"title": "it used to be free", "turns": [
   ["V", "<gap 0.6>Okay. First pattern. It was free, and then one day it wasn't."],
   ["V", "<gap 0.3><bill spliit>Splitwise now caps free accounts at three expenses a day. The fourth one costs $4.99 a month."],
   ["G", "<fx 🍝 pop>Three a day is one dinner."],
   ["V", "<shot spliit>So Sebastien Castiel built Spliit. No limit, no account, no ads."]]}
 ]
}
```

- A **turn** is one host's line and one voice take: `"V"` is Vera, `"G"` is Gus. The text is the
  caption; the render splits it into caption-sized pieces and times them to the take.
- `wall` is the `replaces.product` of the month's most replaced product; the render finds its apps.
- `post` is the YouTube title (10 to 70 characters), caption and 3 to 5 hashtags, checked like a
  short's. The render writes the full description, with chapters and every named app's hall of
  fame link, to `episodes/.build/YYYY-MM/description.txt`.
- `say` is how the voice should read what the caption shows: every price spelled out, every name
  spelled the way it sounds. Standing ones (the site's address) live in `hosts.json`.
- `shots` points a slug at another address to screenshot when the app's own page comes out blank.
- A segment's `title` is the chip in the corner and the chapter name.

**Tags** sit in the text, in front of the words they belong to:

| Tag | What it does |
|---|---|
| `<eq>` | Clears the stage to the equalizer: the hosts are just talking. |
| `<bill slug>` | The paid product's name and price, with a cash register. |
| `<app slug>` | The app's card: icon, name, the builder's face, tags, the price struck out, FREE, with a punch. |
| `<shot slug>` | The same with a screenshot of the app's own page; falls back to the card if the page is blank. |
| `<spite slug>` | The app's card with the SPITE OF THE MONTH stamp. |
| `<wall>` / `<wall all>` | The wall of shame, names lighting up as they are said / all lit. |
| `<title>` / `<stats>` | The title card / with the month's two numbers. |
| `<site page [search]>` | A screenshot of the site's own page, e.g. `<site apps slack>`. |
| `<outro>` / `<outro sub>` | The end card / with the subscribe box. |
| `<fx 🍝 pop [tr\|br\|tl\|tm]>` | A sticker and its sound, optionally pinned to a corner. |
| `<sfx whoosh>` | A sound alone. |
| `<pre meow 🐱>` | At the start of a turn: the sound plays in a short silence before the line. |
| `<gap 0.6>` | At the start of a turn: that many seconds of air first, both hosts at rest. |

Sounds, all synthesized in `episode.py`: alarm, boing, buzzer, ching, ding, drumroll, fanfare,
gong, meow, pop, punch, squeak, trombone, whoosh. A new one is a few lines in `synth()`.

**Stickers belong to their episode.** Pick emoji for this month's moments (September had a plate
of spaghetti for "three a day is one dinner"). Shape, size and motion vary on their own; the
render lists stickers that an earlier episode already used.

## Choosing the apps

- From the month's live apps (`added` starts with the month, not `"status": "dead"`), highest
  `spite_score` first; among equals, the ones with a filled `replaces` and a price.
- Group them by what the grudges have in common. The groups are the segments.
- At most one app per paid product, except the wall of shame, which is the point of that segment.
- Run `python3 scripts/links.py --external` and leave out anything it reports DEAD.

## Checking a render

- Run `--stills` first and read the stills in `episodes/.build/YYYY-MM/test/`: text running out
  of a box, a sticker sitting on a price or a FREE stamp (pin it to another corner), a missing
  avatar. The green boxes are where the equalizer goes.
- After the render, read `episodes/.build/YYYY-MM/sheet.png`: a frame every eight seconds.
- Nobody but the user can hear it. Tell them what to listen for: each name spelled phonetically in
  `say`, the sound effects (synthesized, so judge them by ear), and any line the render had to
  voice with the plainer fallback style.

## Things that went wrong once

- The voice provider refuses some very short lines ("Go.", "Free."). The render retries with a
  plainer style; if a line still fails, give it a few more words.
- The frame template shares `/style.css` with the site. A class name the site already uses
  (`.wall`, `.shame`, `.sticker`) silently breaks a frame: check new class names against it.
- An app whose page draws itself after load screenshots blank. Put its repo in `shots`.
- A sandbox marks the mp4 as quarantined and macOS refuses to open it; the render clears the flag.
- The site screenshot is taken from the working tree with analytics stripped, so a render is
  never a visit. Keep it that way.
