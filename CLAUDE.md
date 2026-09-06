# spiteware.ai — working rules

- **Never commit or push unless the user explicitly says so in that message.** Editing files is fine. Staging, committing, and pushing wait for the word. A push publishes to GitHub Pages at https://spiteware.ai.
- Never use `pkill` in this repo's shell. It kills the session. Check a port with curl and start servers with `(nohup ... &)`.
- The site is static: `index.html` (home, top 6 by spite score), `apps.html` (full catalog with search, tag filter, sort), shared `style.css` and `site.js`, all rendering from `data/apps.json`. No build step, no dependencies, no external requests.
- Content is hand-curated. The `/spite` skill drafts candidates into `queue/`; only the review desk or the user's explicit approval moves them into `data/apps.json`.
- Local preview: `python3 -m http.server 4321` and open http://localhost:4321/. Review desk: `python3 scripts/review.py 4322`.
- Design is locked: flat, thick black borders, hard offset shadows, cream paper, acid yellow, hot pink. Strikethrough "replaces X · $N/mo" badge is the signature element.
