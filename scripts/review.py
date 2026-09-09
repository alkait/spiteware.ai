#!/usr/bin/env python3
"""Local review UI for the morning queue. No deps.

Usage: python3 scripts/review.py [port]   then open http://localhost:4322/
Approve / reject / edit write straight back to queue/*.json. Approve also stars the
candidate's repo via scripts/star.py. Merge runs scripts/merge.py.
"""
import json, sys, pathlib, http.server, urllib.parse, importlib.util

ROOT = pathlib.Path(__file__).resolve().parent.parent
def load(name):
    """Re-read a sibling script on every use. The desk stays up for days; loading it
    once at startup silently serves whatever the file looked like back then."""
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M); return M

def queue_files():
    return sorted((p for p in (ROOT / "queue").glob("*.json") if not p.name.startswith("raw-")), reverse=True)

def load_all():
    out = []
    for p in queue_files():
        q = json.loads(p.read_text()); q["file"] = p.name; out.append(q)
    return out

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(ROOT), **k)
    def log_message(self, *a): pass
    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", len(b)); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/": self.path = "/scripts/review.html"
        if p == "/api/queue": return self._json({"runs": load_all(), "apps": json.loads((ROOT / "data/apps.json").read_text())})
        return super().do_GET()
    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if p == "/api/decide":
            qf = ROOT / "queue" / body["file"]; q = json.loads(qf.read_text())
            target = None
            for c in q["candidates"]:
                if c["slug"] == body["slug"]:
                    target = c
                    if "status" in body: c["status"] = body["status"]
                    for k in ("name", "tagline", "icon", "tags", "spite_score", "vibe_coded"):
                        if k in body: c[k] = body[k]
                    if "replaces" in body: c["replaces"].update(body["replaces"])
                    if "grudge" in body: c["grudge"].update(body["grudge"])
            qf.write_text(json.dumps(q, indent=2, ensure_ascii=False) + "\n")
            # Approving is the moment the app joins the list, so it is the moment to
            # star it. Kept synchronous — one star is two API calls — but timeboxed,
            # because a hung network must never wedge the desk. Starring is additive
            # and idempotent, so a later un-approve simply leaves the star behind.
            star = None
            if body.get("status") == "approve" and target is not None:
                state, detail = load("star").star_one(target.get("repo", ""), timeout=8)
                star = {"state": state, "detail": detail}
            return self._json({"ok": True, "star": star})
        if p == "/api/merge":
            M = load("merge")
            res = [dict(M.merge(qf), file=qf.name) for qf in queue_files()]; return self._json({"ok": True, "results": res})
        self._json({"error": "unknown"}, 404)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4322
    print(f"review UI: http://localhost:{port}/")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
