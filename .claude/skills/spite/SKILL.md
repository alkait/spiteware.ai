---
name: spite
description: Morning spiteware hunt. Sweeps HN, Reddit, GitHub and last30days for apps built out of spite against paid tools, scores them against criteria.md, drafts cards into queue/YYYY-MM-DD.json, lists everything that passed both gates, and renders the day's short video, all in one run. /spite review stops at the review desk instead. Also merges a reviewed queue file and renders a short on its own. Triggers on /spite, /spite review, /spite merge, /spite short, "morning run", "find spiteware", "make the short".
---

# /spite

You are the spiteware.ai morning agent. You find candidates, draft cards, list them, and make the day's short. The user has given the morning run standing approval: every candidate that passes both hard gates is listed the same day, without waiting for the review desk. You still never write to `data/apps.json` yourself; only `scripts/merge.py` does.

Nobody reads the queue before it is listed, so the gates are the only review there is. A candidate you are unsure about, a quote that is a paraphrase, a price you could not source: drop it with the reason. A missed app can be found tomorrow; a wrong one is on the site.

Read `criteria.md` and `sources.md` first on every run. They are the rules and they change.

## Mode: sweep (default, `/spite` with no args or a number of hours; `/spite review` for the manual path)

1. **Sweep tier 1.** Run:
   ```
   python3 scripts/sweep.py --hours ${HOURS:-48} --out queue/raw-$(date +%F).json
   ```
   Read the output file. Each hit has title, url, author, points, text, discussion, and
   `matched` — the phrase that hinted at it, or `null`. **`null` does not mean "skip".**
   Every Show HN in the window is in there whether or not it used our words; the hinted
   ones are just sorted first. Read the titles of the unhinted ones too — that is where
   the grudges phrased in normal English live.

2. **Sweep tier 2.** Run `/last30days` once with the topic: `free alternative apps built because of subscription pricing, indie developers, last few days`. Use `--days 3`. Collect every distinct app it names with a link. Add them to the hit list as `source: last30days`.

3. **Triage.** Drop anything that is obviously not an app built against a paid tool: listicles, "best X alternatives" blog posts, job posts, questions, the paid tool itself. Keep everything that could plausibly be spiteware. Aim for 5 to 15 survivors.

4. **Verify each survivor**, in parallel where possible:
   - Fetch the app's own site. Look for a pricing section, trial, seat cap, "Pro", "Team", "Enterprise". Any of these fails hard gate 2. Note "bring your own key" as allowed.
   - Fetch the HN or Reddit discussion, and the README or site if needed. Find the builder's own words for the grudge. Copy one sentence verbatim. No quote, no grudge, fails hard gate 1.
   - If the builder names the tool they're reacting to, record it, and fetch its pricing page for plan name, price, and URL. If unreachable, use a dated 2026 secondary source and set note `secondary`. Never guess a victim or a price; leave the field empty instead.
   - Note builder name and handle. Set `open_source` true if the project has a public
     GitHub repo — the app's own URL or one linked from its landing page; that is the
     whole test, no licence check. Record that repo as `owner/name` in `repo`; if the
     app's own URL is a github.com link, derive it from there. `repo` is what
     `scripts/star.py` stars, so an open-source app without it is a silent miss.
     Set `vibe_coded` if the builder says AI or vibe coding was used. Both are scored,
     and both drive their own filter button.

5. **Score** each with `python3 scripts/score.py` after the queue is written — the score
   is a pure function of the fields, so do not assign it by hand. Apply the automatic rejects. Everything that passes both gates goes to the queue; the score is for sorting.

6. **Draft cards** into `queue/YYYY-MM-DD.json` using exactly the schema in `queue/README.md`. Every candidate starts `"status": "pending"`. Write the tagline in the voice from `criteria.md`: sarcastic, revenge-flavored, friendly, the joke is the price and never the person. Tag from the closed list in `criteria.md` — at most 3, never a word that isn't on it; `utilities` is the catch-all. Fill `why` with the score breakdown. Put dropped candidates with one-line reasons in the `dropped` array.

7. **Check the catalog for rot.** Run `python3 scripts/links.py --external`. It takes about a minute and checks every link already on the site. `DEAD` lines are findings; `SUSPECT`, `MOVED` and `UNKNOWN` are not, so leave them out unless the user asks. Never run `--bury` yourself and never edit `data/apps.json` to fix a link: report it, and bury only when the user says so.

8. **List them.** Run:
   ```
   python3 scripts/merge.py --approve-all queue/$(date +%F).json
   ```
   It approves every candidate still `pending` in today's file and merges it into
   `data/apps.json`. Name the file: older queue files with pending candidates are the
   user's to decide and are not touched. Show its output. A `HELD, dead link` line means a
   candidate was not listed because one of its links already 404s; it stays in the queue,
   and you do not reach for `--no-check`. Then run
   `python3 -c "import json;json.load(open('data/apps.json'))"` to confirm the JSON is
   valid, and `python3 scripts/star.py` to star the new repos from the user's GitHub
   account (report any `RENAMED` or `UNRESOLVABLE` lines), exactly as in **Mode: merge**.

   **`/spite review` skips this step and step 9.** Instead, check
   `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4322/`; if it isn't 200, start
   `(nohup python3 scripts/review.py 4322 >/dev/null 2>&1 &)` (never pkill in this repo's
   shell; it kills the session), open http://localhost:4322/ in the browser, and report
   that the desk is open. The user approves, rejects, and edits there; approving stars the
   candidate's `repo`.

9. **Make the short.** If step 8 listed anything, follow **Mode: short** below. Nothing
   listed, no short.

10. **Report** to the user in under 200 words: how many hits, how many survived, what was listed (name, score, one line each for the top three, names for the rest), what was held or dropped and why, then the short's report from Mode: short. Say plainly if a source failed. If step 7 found dead links, list them first: app, which link, and the `--bury` command that would retire it. End with the fact that nothing is committed or pushed: the listings are live only after the user says to push.

Never fabricate a quote, a price, or a builder. If verification fails, drop the candidate and say why in the report.

## Mode: merge (`/spite merge [file]`)

The sweep already merges its own candidates. This mode is for what it left behind: a `/spite review` run, a held candidate whose link got fixed, or an older queue file. The review desk has a Merge button that does the same thing; when the user decides in chat instead ("approve X, reject Y"), set those statuses in the queue JSON, then:

1. Run `python3 scripts/merge.py` (defaults to the newest queue file) and show its output. A `HELD, dead link` line means an approved candidate was not listed because one of its links already 404s; tell the user which link, and do not reach for `--no-check` unless they ask.
2. Run `python3 -c "import json;json.load(open('data/apps.json'))"` to confirm the JSON is valid.
3. Run `python3 scripts/star.py` to star the newly listed repos from the user's GitHub
   account, and show its output. The desk stars on Approve, so this is the backstop for
   the chat path and for any star that failed at the time. It reads `data/apps.json`,
   not the queue, so re-running is free. Report any `RENAMED` or `UNRESOLVABLE` lines —
   those are stale `repo` values to fix by hand, not noise.
4. If the merge listed anything, make the day's short: follow **Mode: short** below.
5. Commit and push only if the user asks. A push publishes to GitHub Pages.

## Mode: short (`/spite short [date]`, and the last step of every sweep or merge that listed something)

A 45-second vertical video of the day's fresh spite, narrated, for Shorts, TikTok and Reels.
No new apps that day, no short. The desk's Merge button does not do this, so when the user
says they merged there, run this mode.

1. Read `shorts/README.md` (the script format and the writing rules) and the newest
   `shorts/*.json` (the reference). They are the rules and they change.
2. Take the apps in `data/apps.json` whose `added` is the date. Top 3 by `spite_score`, a
   filled `replaces` breaking ties; the count of the rest goes in `more`.
3. Write `shorts/YYYY-MM-DD.json`. Quotes verbatim from `grudge.quote`, prices and victims only
   from `replaces`, never a pronoun for a builder, anything hard to pronounce spelled out in `say`.
   Fill in `post` too (title, caption, tags): it is the text that goes out with the video, and
   the render refuses a script without it.
4. Render: `python3 scripts/short.py --open`. It voices the script (about 2 cents, takes are
   cached), screenshots the frames, and opens the posting desk, `shorts/YYYY-MM-DD.html`: the
   video plus each platform's text behind Copy buttons. Over 50 seconds means the script is
   too long: cut words, not tempo.
5. Read `shorts/.build/YYYY-MM-DD/sheet.png` and fix anything that overflows or is missing.
6. Report in under 80 words: the file, its length, which apps made it, the title you gave it,
   that the posting desk is open, and what to listen for, since you cannot hear it: the phonetic
   spellings, and "Free." landing on the stamp. If a line sounds wrong to the user,
   `python3 scripts/short.py --reroll <slug|hook|outro> --open`.

Never upload or post the video anywhere, and never drive a browser to do it. The user posts by
hand from the posting desk. The one exception is YouTube, and only when the user asks for it in
that message: `python3 scripts/upload.py` (private; `--public`, `--unlisted` or `--at` only if
they said which), then report the link it prints. The hall of fame links in the description only work once the
merge is pushed, so say so if it has not been.

## Mode: status (`/spite status`)

List queue files with pending counts, total apps listed, and last added date. Read-only.
