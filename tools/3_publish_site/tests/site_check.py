#!/usr/bin/env python3
"""
site_check.py — check the whole website in a real browser. Run it after any change, on the Mac or the PC:

    python3 tools/3_publish_site/tests/site_check.py          (Windows: py tools\\3_publish_site\\tests\\site_check.py)

It starts its own local web server, then:
  - every page at desktop, tablet and phone width: no script errors, no sideways scrolling,
    and every local link, image and download resolves; every chart point, bar and mini-bar row has a
    value label, and hovering one shows it;
  - every report page, every period: the Period dropdown changes the report; the Export menu's header names the
    period and its three downloads point at that period's files (which must exist); a copied link (period and
    filter) restores the same view; ?period= links work; the "how it's worked out" dialog opens;
  - the Export menu works from the keyboard alone, and the home and deliveries menus point at real files.
Prints PROBLEMS: [] when everything passes (and exits 1 otherwise).
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import functools
import json
import http.server
import socket
import sys
import threading
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

import winutf8; winutf8.ensure()   # noqa: E402,E702  Windows: run in UTF-8 mode

REPO = Path(__file__).resolve().parents[3]
REPORTS = ["cost-to-win", "job-margins", "growth", "cash-payroll", "callbacks", "overtime", "cost-to-raise", "program-cost", "runway", "funding", "board", "people-helped", "calls", "volunteers"]


def serve():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Quiet, directory=str(REPO)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}/", httpd


def main():
    from playwright.sync_api import sync_playwright
    base, httpd = serve()
    probs, seen = [], {}

    def ok(u):
        if u not in seen:
            try:
                seen[u] = urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=10).status == 200
            except Exception:
                seen[u] = False
        return seen[u]

    pages = sorted(p.name for p in REPO.glob("*.html"))
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(channel="chrome")
        except Exception:
            br = pw.chromium.launch()
        for w in (1280, 768, 375):
            pg = br.new_page(viewport={"width": w, "height": 900})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "openstreetmap" not in m.text else None)
            for p in pages:
                errs.clear()
                pg.goto(base + p)
                pg.wait_for_timeout(400)
                if errs:
                    probs.append((w, p, errs[:3]))
                if pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                    probs.append((w, p, "sideways scrolling"))
                if w == 1280:
                    # every chart point, bar and mini-bar row shows its real number on hover / focus / tap
                    bare = pg.eval_on_selector_all("svg.dash-svg g.dash-row, svg.dash-svg rect.dash-bar:not(.dash-row rect), .mini-bars li",
                                                   "els => els.filter(e => !e.closest('[data-tip]') || !e.closest('[data-tip]').dataset.tip.trim()).length")
                    if bare:
                        probs.append((p, f"{bare} chart points or bars with no value label"))
                    tips = pg.query_selector_all("[data-tip]")
                    for t in tips[:1] + tips[-1:]:
                        try:
                            t.scroll_into_view_if_needed()
                            t.hover(force=True)
                            pg.wait_for_timeout(60)
                            if not pg.evaluate("(() => { const t = document.querySelector('.chart-tip'); return t && !t.hidden && t.textContent.trim().length > 0; })()"):
                                probs.append((p, "hover showed no value", t.get_attribute("data-tip")))
                        except Exception as e:
                            probs.append((p, "couldn't hover a chart point", str(e)[:80]))
                    for u in pg.eval_on_selector_all("a[href],img[src],script[src],link[href],video[src],source[src]",
                                                     "els => els.map(e => e.getAttribute('href') || e.getAttribute('src'))"):
                        if not u or u.startswith(("#", "mailto:", "tel:", "http", "data:", "javascript:")):
                            continue
                        full = urljoin(base + p, u.split("#")[0])
                        if urlparse(full).netloc == urlparse(base).netloc and not ok(full):
                            probs.append((p, "broken link", u))
            for s in REPORTS:
                pg.goto(base + f"report-{s}.html")
                pg.wait_for_timeout(400)
                opts = pg.eval_on_selector_all("#report-period option", "o => o.map(x => x.value)")
                labels = pg.eval_on_selector_all("#report-period option", "o => o.map(x => x.textContent.replace(' (incomplete)', ''))")
                if len(opts) < 2:
                    probs.append((w, s, "Period dropdown missing"))
                    continue
                before = pg.inner_text("#report-root")
                opening = pg.eval_on_selector("#report-period", "e => e.value")     # the period the page opens on (the month picked earlier in the visit carries over)
                default = json.loads((REPO / "data" / "reports" / f"{s}.json").read_text(encoding="utf-8"))["default"]   # the default month needs no ?period=
                if w == 1280:
                    periods = list(zip(opts, labels))           # every period at desktop width; the oldest elsewhere
                else:
                    periods = [(opts[-1], labels[-1])]
                for per, lab in periods:
                    pg.select_option("#report-period", per)
                    pg.wait_for_timeout(450)
                    if per != opening and pg.inner_text("#report-root") == before:
                        probs.append((w, s, per, "report didn't change with the period"))
                    if per != default and f"period={per}" not in pg.url:
                        probs.append((w, s, per, "address doesn't carry the period"))
                    pg.click(".xm-btn")
                    pg.wait_for_timeout(120)
                    head = pg.inner_text(".xm-head")
                    if lab.split(" to date")[0] not in head:
                        probs.append((w, s, per, "export menu header", head))
                    hrefs = pg.eval_on_selector_all(".xm-item", "a => a.map(x => x.getAttribute('href'))")
                    for u in hrefs:
                        if not u or per not in u or not ok(base + u):
                            probs.append((w, s, per, "export file missing", u))
                    # each download is saved under: business - report - period - generated <date time>
                    for nm in pg.eval_on_selector_all(".xm-item", "a => a.map(x => x.getAttribute('download'))"):
                        mon = lab.split(" to date")[0]
                        want_period = mon.split(" ")[0] if "to date" in lab else mon
                        if not nm or " - generated 20" not in nm or f" - {want_period} - " not in nm:
                            probs.append((w, s, per, "download name lacks business, period or generated time", nm))
                    pg.keyboard.press("Escape")
                # copy the link to this exact view (a non-default filter where there is one), reload it, same view back
                filt = pg.eval_on_selector_all(".report-filter .seg button", "b => b.map(x => x.dataset.filter)")
                if filt:
                    pg.click(f'.report-filter .seg button[data-filter="{filt[-1]}"]')
                    pg.wait_for_timeout(300)
                link = pg.url
                pg.goto(link)
                pg.wait_for_timeout(700)
                if pg.eval_on_selector("#report-period", "e => e.value") != periods[-1][0]:
                    probs.append((w, s, "copied link didn't restore the period", link))
                if filt and pg.eval_on_selector('.report-filter .seg button[aria-pressed="true"]', "b => b.dataset.filter") != filt[-1]:
                    probs.append((w, s, "copied link didn't restore the filter", link))
                mid = opts[len(opts) // 2]
                pg.goto(base + f"report-{s}.html?period={mid}")
                pg.wait_for_timeout(600)
                if pg.eval_on_selector("#report-period", "e => e.value") != mid:
                    probs.append((w, s, "?period= link didn't open that period"))
                pg.click("#report-root [data-sup]")
                pg.wait_for_timeout(150)
                if not pg.eval_on_selector("#support-dialog", "d => d.open"):
                    probs.append((w, s, "workings dialog didn't open"))
                pg.keyboard.press("Escape")
            if w == 1280:
                # keyboard only: Tab to Export, Enter opens with focus on the first item, arrows move, Esc closes and returns
                pg.goto(base + "report-job-margins.html")
                pg.wait_for_timeout(500)
                pg.focus(".xm-btn")
                pg.keyboard.press("Enter")
                pg.wait_for_timeout(120)
                f1 = pg.evaluate("document.activeElement.dataset.fmt")
                pg.keyboard.press("ArrowDown")
                f2 = pg.evaluate("document.activeElement.dataset.fmt")
                pg.keyboard.press("Escape")
                pg.wait_for_timeout(80)
                back = pg.evaluate("document.activeElement.classList.contains('xm-btn')")
                closed = pg.eval_on_selector(".xm-menu", "m => m.hidden")
                if (f1, f2, back, closed) != ("xlsx", "pdf", True, True):
                    probs.append(("keyboard", f1, f2, back, closed))
                # separate businesses, separate files: growth's Export menu follows the business on screen
                pg.goto(base + "report-growth.html")
                pg.wait_for_timeout(500)
                for blk, org in ((0, "trades"), (1, "services")):
                    pg.click(f'.report-blocks button[data-block="{blk}"]')
                    pg.wait_for_timeout(300)
                    pg.click(".xm-btn")
                    pg.wait_for_timeout(120)
                    hrefs = pg.eval_on_selector_all(".xm-item", "a => a.map(x => x.getAttribute('href'))")
                    if not hrefs or any(f"growth-{org}." not in (u or "") or not ok(base + u) for u in hrefs):
                        probs.append(("growth", org, "export files aren't this business's own", hrefs))
                    pg.keyboard.press("Escape")
                # home hero and deliveries: the Export menu points at real files
                for page, sel in (("index.html?period=2026-09", "#dash-export"), ("examples.html", "#deliv-export")):
                    pg.goto(base + page)
                    pg.wait_for_timeout(600)
                    pg.click(f"{sel} .xm-btn")
                    for u in pg.eval_on_selector_all(f"{sel} .xm-item", "a => a.map(x => x.getAttribute('href'))"):
                        if not u or not ok(base + u):
                            probs.append((page, "export file missing", u))
                    pg.keyboard.press("Escape")
                # other months on the home page: no monthly pack, said plainly; no invented balance sheet
                pg.goto(base + "index.html?period=2025-03")
                pg.wait_for_timeout(900)
                if pg.eval_on_selector("#dash-period", "e => e.value") != "2025-03":
                    probs.append(("index.html", "period link didn't open March 2025"))
                pg.click("#dash-export .xm-btn")
                if pg.eval_on_selector_all("#dash-export a.xm-item[href]", "a => a.length"):
                    probs.append(("index.html", "March 2025 offers September's export pack"))
                pg.keyboard.press("Escape")
                pg.click('[role="tab"][data-tab="bs"]')
                pg.wait_for_timeout(200)
                if not pg.locator(".dash-unavailable").count():
                    probs.append(("index.html", "March 2025 balance sheet has no 'not available' note"))
                    pg.keyboard.press("Escape")
        br.close()
    httpd.shutdown()
    print(f"{len(pages)} pages x 3 widths and {len(REPORTS)} reports checked. PROBLEMS: {probs}")
    if probs:
        sys.exit(1)


if __name__ == "__main__":
    main()
