#!/usr/bin/env python3
"""
render_mockups.py: turn the HTML dashboard mock-ups in tools/mockups/ into
the PNG images used on the website (media/mockups/display-*.png, report-*.png and template-excel.png, 1600x900).

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
    browser.close()
    import sync_media   # media/ kept identical with OneDrive
    sync_media.sync()
