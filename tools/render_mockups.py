#!/usr/bin/env python3
"""
render_mockups.py: turn the HTML dashboard mock-ups in tools/mockups/ into
the PNG images used on the website (media/mockups/display-*.png, report-*.png and template-excel.png, 1600x900),
and the home page hero picture (hero-pack*.png: laid out at 460x388 and 360x190, saved at 2x and 3x for sharp screens).

The data in them is invented ("Sample Co") and labelled illustrative.
Edit a .html file, then run from the repo root:   python3 tools/render_mockups.py
(Needs Playwright: pip install playwright; uses your installed Google Chrome.)
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
import winutf8; winutf8.ensure()   # Windows: run in UTF-8 mode (the tools write characters like ¢ and ▲)

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "tools" / "mockups"
OUT = REPO / "media" / "mockups"
NAMES = {
    "warehouse": "display-warehouse.png", "reception": "display-reception.png", "boardroom": "display-boardroom.png",
    "report-sales": "report-sales.png", "report-purchasing": "report-purchasing.png", "report-payroll": "report-payroll.png",
    "template-excel": "template-excel.png",
}
HERO = {"hero-pack": (460, 388), "hero-pack-kpis": (360, 190)}   # name: (width, height) as laid out

with sync_playwright() as p:
    try:
        browser = p.chromium.launch(channel="chrome")
    except Exception:
        browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    for name, out in NAMES.items():
        page.goto((SRC / f"{name}.html").as_uri(), wait_until="networkidle")
        page.evaluate("document.fonts.ready")          # Roboto loaded before the picture is taken
        page.screenshot(path=str(OUT / out))
        print("wrote", (OUT / out).relative_to(REPO))
    for name, (w, h) in HERO.items():
        for scale, suffix in ((2, ""), (3, "@3x")):
            pg = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
            pg.goto((SRC / f"{name}.html").as_uri(), wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.screenshot(path=str(OUT / f"{name}{suffix}.png"))
            pg.close()
            print("wrote", f"media/mockups/{name}{suffix}.png")
    browser.close()
    import sync_media   # media/ kept identical with OneDrive
    sync_media.sync()
