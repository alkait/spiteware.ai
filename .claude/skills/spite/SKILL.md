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
   Read the output file. Each hit has title, url, author, points, text, discussion, matched phrase.

2. **Sweep tier 2.** Run `/last30days` once with the topic: `free alternative apps built because of subscription pricing, indie developers, last few days`. Use `--days 3`. Collect every distinct app it names with a link. Add them to the hit list as `source: last30days`.

3. **Triage.** Drop anything that is obviously not an app built against a paid tool: listicles, "best X alternatives" blog posts, job posts, questions, the paid tool itself. Keep everything that could plausibly be spiteware. Aim for 5 to 15 survivors.

4. **Verify each survivor**, in parallel where possible:
   - Fetch the app's own site. Look for a pricing section, trial, seat cap, "Pro", "Team", "Enterprise". Any of these fails hard gate 3. Note "bring your own key" as allowed.
   - Fetch the HN or Reddit discussion. Find the builder's own words for the grudge. Copy one sentence verbatim. No quote, no grudge, fails hard gate 1.
   - Identify the victim tool. Fetch its pricing page. Record plan name, monthly price, and URL. If the pricing page is unreachable, use a dated 2026 secondary source and mark it `(secondary)`.
   - Note builder name and handle, solo or team, license, and whether the builder says AI or vibe coding was used.

5. **Score** each against the table in `criteria.md`. Apply the automatic rejects. Drop anything under 6.

6. **Draft cards** into `queue/YYYY-MM-DD.json` using exactly the schema in `queue/README.md`. Every candidate starts `"status": "pending"`. Write the tagline in the voice from `criteria.md`: sarcastic, revenge-flavored, friendly, the joke is the price and never the person. Fill `why` with the score breakdown. Put dropped candidates with one-line reasons in the `dropped` array.

7. **Open the review desk.** Check `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4322/`. If it isn't 200, start `(nohup python3 scripts/review.py 4322 >/dev/null 2>&1 &)`. Never use pkill in this repo's shell; it kills the session. Then open http://localhost:4322/ in the browser. The user approves, rejects, and edits there.

8. **Report** to the user in under 150 words: how many hits, how many survived, the top three by score with one line each, and that the review desk is open. Say plainly if a source failed.

Never fabricate a quote, a price, or a builder. If verification fails, drop the candidate and say why in the report.

## Mode: merge (`/spite merge [file]`)

The review desk has a Merge button that does the same thing. This mode is for when the user decides in chat instead ("approve X, reject Y"): set those statuses in the queue JSON, then:

1. Run `python3 scripts/merge.py` (defaults to the newest queue file) and show its output.
2. Run `python3 -c "import json;json.load(open('data/apps.json'))"` to confirm the JSON is valid.
3. Commit and push only if the user asks. A push publishes to GitHub Pages.

## Mode: status (`/spite status`)

List queue files with pending counts, total apps listed, and last added date. Read-only.
