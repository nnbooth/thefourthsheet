#!/usr/bin/env python3
"""
publish_site.py — the last step before the site goes live (run by .github/workflows/pages.yml on every push to main).

The repo keeps its comments: they're the notes that explain each page. The published copy doesn't, so nothing internal
reaches a visitor's "view source". On the built site folder (Jekyll's _site):

  1. strips every HTML comment from every page (outside <script>, <style>, <pre> and <textarea>), and every CSS comment
     from the stylesheets; data-placeholder attributes are untouched
  2. stamps every ?v= cache-buster (CSS, JS, data files, images) with one version: the commit's short hash, so a
     browser fetches new files after each publish and never otherwise (script.js passes the same ?v= on to the data
     files it loads)
  3. writes sitemap.xml (every public page, www domain) beside robots.txt

    python3 tools/3_publish_site/publish_site.py _site <version>       # what the workflow runs
    python3 tools/3_publish_site/publish_site.py --sitemap .           # refresh the repo's sitemap.xml after adding a page

Stops (exit 1) if a comment is left anywhere in the published pages.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import re
import sys
from datetime import date
from pathlib import Path

DOMAIN = "https://www.thefourthsheet.com.au"
NOT_PAGES = {"404.html"}                     # pages that exist but aren't listed in the sitemap
KEEP = re.compile(r"(<(script|style|pre|textarea)\b.*?</\2\s*>)", re.S | re.I)
HTML_COMMENT = re.compile(r"<!--(?!\[if).*?-->", re.S)
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
VERSION = re.compile(r"\?v=[\w.-]+")


def strip_html(text):
    parts = KEEP.split(text)
    out, i = [], 0
    while i < len(parts):
        out.append(HTML_COMMENT.sub("", parts[i]))           # outside the kept blocks
        if i + 1 < len(parts):
            out.append(parts[i + 1])                          # a <script>/<style>/<pre>/<textarea> block, as is
        i += 3
    text = "".join(out)
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)  # the blank lines a removed comment leaves


def pages(root):
    return sorted(p for p in root.glob("*.html") if p.name not in NOT_PAGES)


def sitemap(root):
    today = date.today().isoformat()
    urls = []
    for p in pages(root):
        loc = f"{DOMAIN}/" if p.name == "index.html" else f"{DOMAIN}/{p.name}"
        urls.append(f"  <url><loc>{loc}</loc><lastmod>{today}</lastmod></url>")
    (root / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n")
    return len(urls)


def publish(site, version):
    left = []
    for p in site.rglob("*.html"):
        t = VERSION.sub(f"?v={version}", strip_html(p.read_text(encoding="utf-8")))
        p.write_text(t, encoding="utf-8")
        if HTML_COMMENT.search(KEEP.sub("", t)):
            left.append(str(p.relative_to(site)))
    for p in site.rglob("*.css"):
        p.write_text(VERSION.sub(f"?v={version}", CSS_COMMENT.sub("", p.read_text(encoding="utf-8"))), encoding="utf-8")
    n = sitemap(site)
    if left:
        raise SystemExit(f"comments left in: {', '.join(left)}")
    print(f"published: comments stripped, ?v={version} on every asset, sitemap of {n} pages")


if __name__ == "__main__":
    if sys.argv[1] == "--sitemap":
        print(f"sitemap.xml: {sitemap(Path(sys.argv[2]))} pages")
    else:
        publish(Path(sys.argv[1]), sys.argv[2])
