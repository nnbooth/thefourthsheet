#!/usr/bin/env python3
"""serve.py — preview the site locally with caching turned off, so the browser
always shows the current files.   python3 tools/3_publish_site/serve.py   ->  http://127.0.0.1:8765"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]
import functools
import http.server
from pathlib import Path
import winutf8; winutf8.ensure()   # Windows: run in UTF-8 mode (the tools write characters like ¢ and ▲)


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    handler = functools.partial(NoCache, directory=str(Path(__file__).resolve().parent.parent.parent))
    http.server.ThreadingHTTPServer(("127.0.0.1", 8765), handler).serve_forever()
