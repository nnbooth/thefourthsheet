#!/usr/bin/env python3
"""
render_og_image.py — draw assets/brand/og-image.png, the picture LinkedIn and others show when the site is shared
(1200 x 630). Same layout as before, in Roboto like the site and the business cards.

    python3 tools/archive/render_og_image.py
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import sys
from pathlib import Path

import winutf8; winutf8.ensure()   # noqa: E402,E702  Windows: run in UTF-8 mode

REPO = Path(__file__).resolve().parent.parent.parent
OUT = REPO / "assets" / "brand" / "og-image.png"

HTML = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700;900&display=swap">
<style>
  html, body { margin: 0; width: 1200px; height: 630px; overflow: hidden; }
  body { background: #f4f7f2; color: #25342a; font-family: "Roboto", "Segoe UI", Arial, sans-serif; position: relative; }
  .brand { position: absolute; left: 80px; top: 72px; display: flex; align-items: center; gap: 22px; }
  .brand img { width: 76px; height: 76px; display: block; }
  .brand b { font-size: 34px; font-weight: 700; letter-spacing: -0.01em; }
  sup { font-size: 0.55em; vertical-align: 0.75em; line-height: 0; }
  .eyebrow { position: absolute; left: 80px; top: 240px; color: #2f7a5d; font-size: 21px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; }
  h1 { position: absolute; left: 80px; top: 278px; margin: 0; font-size: 56px; line-height: 1.12; font-weight: 700; letter-spacing: -0.025em; }
  h1 span { color: #2f7a5d; }
  .sub { position: absolute; left: 80px; top: 500px; color: #5f6f63; font-size: 27px; }
  .bar { position: absolute; left: 0; right: 0; bottom: 0; height: 24px; background: #2f7a5d; }
</style></head><body>
  <div class="brand"><img src="MARK"><b>The Fourth Sheet</b></div>
  <div class="eyebrow">For SMEs and not-for-profits</div>
  <h1>Your accountant gives you three sheets.<br><span>I give you the fourth.</span></h1>
  <div class="sub">The numbers underneath. Without the full-time hire.</div>
  <div class="bar"></div>
</body></html>"""


def main():
    from playwright.sync_api import sync_playwright
    mark = (REPO / "assets" / "brand" / "mark-4th.svg").as_uri()
    page_file = REPO / "assets" / "brand" / ".og-image.html"
    page_file.write_text(HTML.replace("MARK", mark), encoding="utf-8")
    try:
        with sync_playwright() as pw:
            try:
                b = pw.chromium.launch(channel="chrome")
            except Exception:
                b = pw.chromium.launch()
            p = b.new_page(viewport={"width": 1200, "height": 630})
            p.goto(page_file.as_uri(), wait_until="networkidle")
            p.evaluate("document.fonts.ready")
            if not p.evaluate("document.fonts.check('700 56px Roboto')"):
                sys.exit("Roboto didn't load (no internet?): og-image.png not changed")
            p.screenshot(path=str(OUT))
            b.close()
    finally:
        page_file.unlink(missing_ok=True)
    print(f"wrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
