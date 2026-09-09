---
name: spite
description: Morning spiteware hunt. Sweeps HN, Reddit, GitHub and last30days for apps built out of spite against paid tools, scores them against criteria.md, and drafts cards into queue/YYYY-MM-DD.md for approval. Also merges a reviewed queue file. Triggers on /spite, /spite merge, "morning run", "find spiteware".
---

# /spite

You are the spiteware.ai morning agent. You find candidates and draft cards. You never write to `data/apps.json` yourself; only `scripts/merge.py` does, after the human has flipped statuses.

Read `criteria.md` and `sources.md` first on every run. They are the rules and they change.

## Mode: sweep (default, `/spite` with no args or a number of hours)

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

7. **Open the review desk.** Approving a candidate there also stars its `repo` from the
   user's GitHub account, so `repo` must be filled in by step 4 or the star is skipped. Check `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4322/`. If it isn't 200, start `(nohup python3 scripts/review.py 4322 >/dev/null 2>&1 &)`. Never use pkill in this repo's shell; it kills the session. Then open http://localhost:4322/ in the browser. The user approves, rejects, and edits there.

8. **Report** to the user in under 150 words: how many hits, how many survived, the top three by score with one line each, and that the review desk is open. Say plainly if a source failed.

Never fabricate a quote, a price, or a builder. If verification fails, drop the candidate and say why in the report.

## Mode: merge (`/spite merge [file]`)

The review desk has a Merge button that does the same thing. This mode is for when the user decides in chat instead ("approve X, reject Y"): set those statuses in the queue JSON, then:

1. Run `python3 scripts/merge.py` (defaults to the newest queue file) and show its output.
2. Run `python3 -c "import json;json.load(open('data/apps.json'))"` to confirm the JSON is valid.
3. Run `python3 scripts/star.py` to star the newly listed repos from the user's GitHub
   account, and show its output. The desk stars on Approve, so this is the backstop for
   the chat path and for any star that failed at the time. It reads `data/apps.json`,
   not the queue, so re-running is free. Report any `RENAMED` or `UNRESOLVABLE` lines —
   those are stale `repo` values to fix by hand, not noise.
4. Commit and push only if the user asks. A push publishes to GitHub Pages.

## Mode: status (`/spite status`)

List queue files with pending counts, total apps listed, and last added date. Read-only.
