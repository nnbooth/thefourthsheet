#!/usr/bin/env python3
"""
newsletter.py — the weekly newsletter for The Fourth Sheet: a review spreadsheet in, a blog post out.

HOW IT WORKS
  1. Each week has ONE Excel file:  tools/newsletter/issues/<YYYY>-W<NN>/review.xlsx
       - "Items" sheet: one row per story. Claude fills the research columns; YOU tick (Include = Yes / No),
         add or delete rows yourself, and write your own words in the "My take" column.
       - "Settings" sheet: newsletter name, issue title, week, status (Draft / Published), your opening note and sign-off.
  2. Only rows marked Include = Yes make it into the post. Everything published is your wording:
       the headline, source and link are factual labels you can edit; "My take", the opening note and the sign-off are yours.
       The "Facts" and "Angle" columns are research notes for you and are NEVER published.
  3. The post is built from that file, so what you tick is what gets published. No bot decides.

COMMANDS (run from the repo root; Windows: py instead of python3)
    python3 tools/newsletter/newsletter.py new 2026-W44        # blank review file for a week (copy of the template)
    python3 tools/newsletter/newsletter.py build 2026-W43      # render that week's post + refresh the newsletter index
    python3 tools/newsletter/newsletter.py build-all           # rebuild every week (after a style change)
    python3 tools/newsletter/newsletter.py preview 2026-W43    # build it, then open it in your browser (Ctrl-C to stop). Nothing is published.

STATUS
  Draft      -> post is written to newsletter/<week>.html with "noindex", a DRAFT banner, and is NOT listed on the index.
  Published  -> the build STOPS unless the opening note, sign-off and a "My take" for every included item are filled in.
                The post loses the banner, loses noindex, and is listed on newsletter/index.html.
  Nothing goes live until the file is committed and pushed to main (the site publishes on every push).
"""

import html
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

REPO = Path(__file__).resolve().parents[2]
ISSUES = REPO / "tools" / "newsletter" / "issues"      # the review files (kept in git, not published: tools/ is excluded)
OUT = REPO / "newsletter"                               # the published posts
DOMAIN = "https://www.thefourthsheet.com.au"

# ---- the columns of the Items sheet, in order. Header text is what the build looks for. ----
ITEM_COLS = [
    ("Include", 9),                 # Yes / No dropdown: the tick and flick
    ("Lens", 14),                   # Finance / Operations / Both / Data craft: which section it lands in
    ("Headline", 44),               # published: a plain label for the story (edit freely)
    ("Source", 24),                 # published: who said it
    ("Link", 40),                   # published: where to read it
    ("Date", 12),                   # published (if filled): when it came out
    ("Facts (not published)", 60),  # research notes: what happened, in plain terms
    ("Angle (not published)", 50),  # a prompt for your take: where data meets operations or the numbers
    ("My take (published)", 70),    # YOUR words. Blank + Include=Yes means the item is not ready.
    ("Added by", 11),               # Claude / Nathan
]
LENSES = ["Finance", "Operations", "Both", "Data craft"]
SECTION_TITLES = {                  # how each lens is headed in the post, in the order they appear
    "Finance": "Finance and accounting",
    "Operations": "Operations",
    "Both": "Where the numbers and the work meet",
    "Data craft": "Data craft",
}

# ---- the Settings sheet: key, default, note ----
SETTINGS = [
    ("Newsletter name", "The Fourth Read", "Working title. Change it here and every post and the index change with it."),
    ("Tagline", "Data, operations and the numbers underneath. Weekly.", "Shown under the name. Yours to change."),
    ("Issue title", "", "Optional. A line for this week, in your words. Blank = just the week."),
    ("Week label", "", "e.g. Week of 19 October 2026"),
    ("Status", "Draft", "Draft or Published. Published is blocked until your words are in."),
    ("Opening note", "", "YOURS. A few lines on what you noticed this week."),
    ("Sign-off", "", "YOURS. How you close it."),
]


# ------------------------------------------------------------------------------------------ the review file
def week_dates(week):
    """'2026-W43' -> (Monday, Sunday) of that ISO week."""
    m = re.fullmatch(r"(\d{4})-W(\d{2})", week)
    if not m:
        sys.exit(f"Week must look like 2026-W43, not {week!r}")
    monday = date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    return monday, monday + timedelta(days=6)


def new_review(week, items=None, settings=None):
    """Create issues/<week>/review.xlsx. `items` is a list of dicts keyed by the ITEM_COLS names (Claude's research);
    `settings` overrides the Settings defaults."""
    monday, sunday = week_dates(week)
    folder = ISSUES / week
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "review.xlsx"
    if path.exists():
        sys.exit(f"{path} already exists. Not overwriting your ticks.")

    wb = Workbook()
    ws = wb.active
    ws.title = "Items"
    names = [c for c, _ in ITEM_COLS]
    ws.append(names)
    for col, (_, width) in enumerate(ITEM_COLS, start=1):
        ws.column_dimensions[ws.cell(1, col).column_letter].width = width
        c = ws.cell(1, col)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="2F7A5D")
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "D2"

    rows = list(items or [])
    for r in rows:
        ws.append([r.get(n, "") for n in names])
    SPARE = 12                                    # empty rows with the dropdowns already on, ready for you to add stories
    for _ in range(SPARE):
        ws.append(["No", "", "", "", "", "", "", "", "", "Nathan"])
    last = ws.max_row
    for row in ws.iter_rows(min_row=2, max_row=last):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    inc = DataValidation(type="list", formula1='"Yes,No"', allow_blank=False)
    lens = DataValidation(type="list", formula1='"' + ",".join(LENSES) + '"', allow_blank=True)
    ws.add_data_validation(inc)
    ws.add_data_validation(lens)
    inc.add(f"A2:A{last + 200}")                  # the dropdowns run well past the last row, so new rows just work
    lens.add(f"B2:B{last + 200}")
    green = PatternFill("solid", bgColor="E3F4E8")
    grey = PatternFill("solid", bgColor="EEF2EE")
    ws.conditional_formatting.add(f"A2:J{last + 200}", FormulaRule(formula=['$A2="Yes"'], fill=green))
    ws.conditional_formatting.add(f"A2:J{last + 200}", FormulaRule(formula=['AND($A2="No",$C2<>"")'], fill=grey))

    st = wb.create_sheet("Settings")
    st.append(["Setting", "Value", "Note"])
    for c in st[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="2F7A5D")
    st.column_dimensions["A"].width = 18
    st.column_dimensions["B"].width = 80
    st.column_dimensions["C"].width = 70
    over = settings or {}
    for key, default, note in SETTINGS:
        default = over.get(key, default)
        if key == "Week label" and not default:
            default = f"Week of {monday.day} {monday:%B %Y}"
        st.append([key, default, note])
    for row in st.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    status_dv = DataValidation(type="list", formula1='"Draft,Published"', allow_blank=False)
    st.add_data_validation(status_dv)
    status_dv.add("B6")                           # the Status row (row 6 = 5th setting + header)

    wb.save(path)
    print(f"created {path.relative_to(REPO)}  ({len(rows)} researched items + {SPARE} spare rows)")
    return path


def read_review(week):
    path = ISSUES / week / "review.xlsx"
    if not path.exists():
        sys.exit(f"No review file at {path}. Make one with:  python3 tools/newsletter/newsletter.py new {week}")
    wb = load_workbook(path, data_only=True)
    settings = {}
    for key, value, _ in wb["Settings"].iter_rows(min_row=2, values_only=True):
        if key:
            settings[str(key).strip()] = ("" if value is None else str(value).strip())
    header = [c.value for c in wb["Items"][1]]
    items = []
    for row in wb["Items"].iter_rows(min_row=2, values_only=True):
        rec = {h: ("" if v is None else (v.strftime("%-d %B %Y") if hasattr(v, "strftime") else str(v).strip()))
               for h, v in zip(header, row)}
        if rec.get("Headline"):                   # a row with no headline is an empty spare row
            items.append(rec)
    return settings, items


# ------------------------------------------------------------------------------------------ the post
def esc(s):
    return html.escape(s, quote=True)


def paragraphs(text):
    """Blank line = new paragraph. Nathan's words go in as typed (escaped), nothing added."""
    return "\n".join(f"<p>{esc(p.strip()).replace(chr(10), '<br>')}</p>" for p in re.split(r"\n\s*\n", text) if p.strip())


def safe_link(url):
    return url if re.match(r"https?://", url) else ""


NAV = """<header class="site-header">
      <div class="container nav-bar">
        <a class="brand" href="/"><span class="brand-mark" aria-hidden="true">4<sup>th</sup></span><span>The Fourth Sheet</span></a>
        <button class="nav-toggle" aria-label="Open menu" aria-expanded="false" aria-controls="primary-nav">☰</button>
        <nav class="nav-links" id="primary-nav" aria-label="Primary navigation">
          <a href="/sme.html">Businesses</a>
          <a href="/not-for-profit.html">Not-for-profits</a>
          <a href="/examples.html">Examples</a>
          <a href="/services.html">Services</a>
          <a href="/about.html">About</a>
          <a href="/contact.html">Contact</a>
          <a class="button primary nav-book" href="/contact.html?topic=numbers-check" data-track="numbers-check">Ask for a free 20-minute numbers check</a>
        </nav>
      </div>
    </header>"""

FOOTER = """<footer class="site-footer">
      <div class="container footer-content">
        <nav class="footer-links" aria-label="Site">
          <a href="/sme.html">Businesses</a><a href="/not-for-profit.html">Not-for-profits</a><a href="/examples.html">Examples</a><a href="/services.html">Services</a><a href="/about.html">About</a><a href="/numbers-explained.html">Numbers explained</a><a href="/contact.html">Contact</a>
        </nav>
        <p>© <span id="year">2026</span> The Fourth Sheet · Nathan Booth · Brisbane, Australia · ABN 31 839 620 153</p>
      </div>
    </footer>"""


def page(title, description, body, draft=False, canonical=None):
    robots = '<meta name="robots" content="noindex, nofollow" />' if draft else ""
    canon = f'<link rel="canonical" href="{canonical}" />' if canonical and not draft else ""
    return f"""<!DOCTYPE html>
<html lang="en-AU">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{esc(title)} | The Fourth Sheet</title>
    <meta name="description" content="{esc(description)}" />
    {robots}
    {canon}
    <link rel="icon" href="/assets/brand/mark-4th.svg?v=roboto" type="image/svg+xml" />
    <meta name="theme-color" content="#2f7a5d" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap">
    <link rel="stylesheet" href="/styles.css?v=dev" />
  </head>
  <body>
    {NAV}
    <main id="main">
{body}
    </main>
    {FOOTER}
    <script src="/script.js?v=dev"></script>
  </body>
</html>
"""


def problems_for_publish(settings, included):
    """Everything that must be in your own words before a post can go out as Published."""
    p = []
    if not settings.get("Opening note"):
        p.append("Settings: Opening note is empty")
    if not settings.get("Sign-off"):
        p.append("Settings: Sign-off is empty")
    for it in included:
        if not it.get("My take (published)"):
            p.append(f"No 'My take' yet: {it['Headline']}")
        if not safe_link(it.get("Link", "")):
            p.append(f"Missing or invalid link: {it['Headline']}")
    if not included:
        p.append("No items ticked Yes")
    return p


def build(week):
    settings, items = read_review(week)
    monday, sunday = week_dates(week)
    name = settings.get("Newsletter name") or "The Fourth Read"
    status = settings.get("Status", "Draft")
    draft = status != "Published"
    included = [i for i in items if i.get("Include", "").lower() == "yes"]
    todo = problems_for_publish(settings, included)
    if not draft and todo:
        print("NOT PUBLISHED. Status says Published but these still need your words:")
        for t in todo:
            print("  -", t)
        sys.exit(1)

    week_label = settings.get("Week label") or f"Week of {monday.day} {monday:%B %Y}"
    issue_title = settings.get("Issue title", "")
    placeholder = '<span class="tbc">[Nathan to write]</span>'

    parts = []
    banner = ""
    if draft:
        banner = (f'<p class="note-card"><strong>DRAFT, not published.</strong> {len(included)} stories ticked. '
                  f'Still to write: {len(todo)} item(s). This page is hidden from search engines and not linked anywhere.</p>')
    opening = settings.get("Opening note", "")
    parts.append(f"""      <section class="section page-top section-alt">
        <div class="container">
          <div class="section-heading">
            <p class="eyebrow">{esc(name)} · {esc(week_label)}</p>
            <h1>{esc(issue_title) if issue_title else esc(name)}</h1>
            <p class="lead">{esc(settings.get('Tagline', ''))}</p>
          </div>
          {banner}
          <div class="newsletter-note">
            {paragraphs(opening) if opening else '<p>' + placeholder + '</p>'}
          </div>
        </div>
      </section>""")

    for lens in LENSES:
        group = [i for i in included if (i.get("Lens") or "Both") == lens]
        if not group:
            continue
        cards = []
        for it in group:
            link = safe_link(it.get("Link", ""))
            src = esc(it.get("Source", ""))
            when = esc(it.get("Date", ""))
            meta = " · ".join(x for x in [src, when] if x)
            head = esc(it["Headline"])
            title_html = f'<a href="{esc(link)}" rel="noopener" target="_blank">{head}</a>' if link else head
            take = it.get("My take (published)", "")
            cards.append(f"""            <article class="info-card">
              <h3>{title_html}</h3>
              <p class="muted">{meta}</p>
              {paragraphs(take) if take else '<p>' + placeholder + '</p>'}
            </article>""")
        parts.append(f"""      <section class="section">
        <div class="container">
          <div class="section-heading"><h2>{esc(SECTION_TITLES[lens])}</h2></div>
          <div class="card-grid card-grid--two">
{chr(10).join(cards)}
          </div>
        </div>
      </section>""")

    signoff = settings.get("Sign-off", "")
    parts.append(f"""      <section class="section section-alt">
        <div class="container">
          {paragraphs(signoff) if signoff else '<p>' + placeholder + '</p>'}
          <p><a class="button primary" href="/contact.html?topic=numbers-check" data-track="numbers-check">Ask for a free 20-minute numbers check</a></p>
          <p><a href="/newsletter/">All issues of {esc(name)}</a></p>
        </div>
      </section>""")

    OUT.mkdir(exist_ok=True)
    slug = week.lower()
    desc = f"{name}, {week_label}: data and operations news read through the numbers."
    (OUT / f"{slug}.html").write_text(
        page(f"{name}: {week_label}", desc, "\n".join(parts), draft, f"{DOMAIN}/newsletter/{slug}.html"), encoding="utf-8")
    print(f"built newsletter/{slug}.html  [{status}]  {len(included)} stories ticked, {len(todo)} still need your words")
    build_index()


def build_index():
    """newsletter/index.html: lists Published issues only, newest first."""
    published = []
    name, tagline = "The Fourth Read", ""
    for review in sorted(ISSUES.glob("*/review.xlsx"), reverse=True):
        week = review.parent.name
        settings, items = read_review(week)
        name = settings.get("Newsletter name") or name
        tagline = settings.get("Tagline") or tagline
        if settings.get("Status") == "Published":
            n = sum(1 for i in items if i.get("Include", "").lower() == "yes")
            published.append((week, settings.get("Week label", week), settings.get("Issue title", ""), n))
    if published:
        rows = "\n".join(
            f'          <li><a href="/newsletter/{w.lower()}.html"><strong>{esc(label)}</strong></a>'
            f'{" · " + esc(t) if t else ""} <span class="muted">({n} stories)</span></li>'
            for w, label, t, n in published)
        listing = f"<ul>\n{rows}\n        </ul>"
    else:
        listing = "<p>The first issue isn't out yet.</p>"
    body = f"""      <section class="section page-top section-alt">
        <div class="container">
          <div class="section-heading">
            <p class="eyebrow">Newsletter</p>
            <h1>{esc(name)}</h1>
            <p class="lead">{esc(tagline)}</p>
          </div>
          {listing}
        </div>
      </section>"""
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(
        page(name, f"{name}: weekly data and operations news read through the numbers.", body, draft=not published,
             canonical=f"{DOMAIN}/newsletter/"), encoding="utf-8")


# ------------------------------------------------------------------------------------------ preview
def preview(week):
    """Build the week, serve the site folder on your own machine and open the page. Drafts show here whatever the
    Status; nothing is committed or published. Stop with Ctrl-C."""
    import functools, http.server, threading, webbrowser
    build(week)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(REPO))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/newsletter/{week.lower()}.html"
    print(f"previewing {url}   (Ctrl-C to stop)")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


# ------------------------------------------------------------------------------------------ command line
if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "new":
        new_review(args[1])
    elif len(args) == 2 and args[0] == "build":
        build(args[1])
    elif len(args) == 2 and args[0] == "preview":
        preview(args[1])
    elif args == ["build-all"]:
        for r in sorted(ISSUES.glob("*/review.xlsx")):
            build(r.parent.name)
    else:
        print(__doc__)
        sys.exit(2)
