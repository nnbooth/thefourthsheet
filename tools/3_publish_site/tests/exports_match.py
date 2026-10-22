#!/usr/bin/env python3
"""
exports_match.py — every download on the site says exactly what the site says. Run from the repo root:

    python3 -I tools/3_publish_site/tests/exports_match.py .

Uses only what's in the repo (data/reports/<report>.json, the site's own numbers, and media/exports/), so it
runs anywhere, including the publish step on GitHub, with no OneDrive needed. For every report and every period:

  1. Its spreadsheet, PDF and slides exist (the files the site's Export menu links to).
  2. The PDF and the slides contain the site's answer, word for word, every headline figure as the site shows it,
     and the period. (Text pulled out of the files; spacing and line breaks ignored.)
  3. The spreadsheet's headline figures, recalculated from its formulas, equal the site's numbers.
  4. No export file is left over that no report links to any more (a stale file nobody would notice).

Prints PASS or FAIL for each, with every mismatch, and exits 1 if anything fails.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import json
import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
fails = []


def report(name, problems):
    print(("PASS " if not problems else "FAIL ") + name + ("" if not problems else f" ({len(problems)}):\n  " + "\n  ".join(problems[:25])))
    if problems:
        fails.append(name)


def every_period():
    """Every report at every period, from data/reports/<report>.json (cards.json is the cards' cut-down copy)."""
    for f in sorted((REPO / "data" / "reports").glob("*.json")):
        if f.name != "cards.json":
            yield from json.loads(f.read_text(encoding="utf-8"))["by_period"].values()


def norm(t):
    """Text for comparing: one space between words; curly quotes and dashes as plain ones; no soft hyphens."""
    t = t.replace("­", "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", t).strip()


def pdf_text(p):
    import pymupdf
    with pymupdf.open(p) as doc:
        return norm(" ".join(page.get_text() for page in doc))


def pptx_text(p):
    from pptx import Presentation
    out = []
    def walk(shapes):
        for sh in shapes:
            if sh.has_text_frame:
                out.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                out.extend(c.text for row in sh.table.rows for c in row.cells)
            if sh.shape_type == 6:                          # group
                walk(sh.shapes)
    for slide in Presentation(p).slides:
        walk(slide.shapes)
    return norm(" ".join(out))


def kpis(r):
    """Every headline figure the site shows: (label, value as shown)."""
    out = []
    for b in r["blocks"]:
        for sec in b["sections"]:
            for x in (list(sec["by"].values()) if sec["type"] == "vary" else [sec]):
                if x["type"] == "kpis":
                    out += [(k["label"], k["value"]) for k in x["items"]]
    return out


def shown(value):
    """The number a displayed figure stands for, and how far rounding can move it: "$1,234" -> (1234, 0.5),
    "(42.7%)" -> (-0.427, 0.0005), "1.9 months" -> (1.9, 0.05). None if it isn't a number."""
    v = str(value).strip()
    neg = v.startswith("(") and v.endswith(")")
    m = re.search(r"-?[\d,]*\.?\d+", v)
    if not m:
        return None
    digits = m.group(0).replace(",", "")
    dp = len(digits.split(".")[1]) if "." in digits else 0
    num, tol = float(digits), 0.5 * 10 ** -dp
    if "%" in v:
        num, tol = num / 100, tol / 100
    return (-num if neg else num), tol + 1e-9


import build_reports as br                     # the builder's own rules: which file holds which part of a report

runs = list(every_period())
linked, missing, text_bad, xl_bad = set(), [], [], []
for r in runs:
    slug, per = r["slug"], r["period"]
    folder = (REPO / (r.get("exports") or {}).get("xlsx", f"media/exports/reports/{per}/x")).parent
    for part in br.file_parts(r):                # one set of files per business for a report split by business
        files = {fmt: folder / f"{br.file_name(part)}.{fmt}" for fmt in ("xlsx", "pdf", "pptx")}
        name = br.file_name(part)
        for fmt, f in files.items():
            if not f.exists():
                missing.append(f"{slug} {per}: no {name}.{fmt}")
        linked |= {f.resolve() for f in files.values()}
        want = [norm(part["period_label"])] + [norm(v) for _, v in kpis(part)]
        if br.in_short(part):
            want.append(norm(br.in_short(part)))
        for fmt, read in (("pdf", pdf_text), ("pptx", pptx_text)):
            if files[fmt].exists():
                text = read(files[fmt])
                gone = [w for w in want if w and w not in text]
                if gone:
                    text_bad.append(f"{name} {per} {fmt}: not in the file: " + "; ".join(f"'{g[:70]}'" for g in gone[:4]))
        f = files["xlsx"]
        if f.exists():
            try:
                from pycel import ExcelCompiler
                import openpyxl
                xc, wb = ExcelCompiler(filename=str(f)), openpyxl.load_workbook(f)
                cells = norm(" ".join(str(c.value) for w in wb.worksheets for row in w.iter_rows() for c in row if isinstance(c.value, str)))
                if br.in_short(part) and norm(br.in_short(part)) not in cells:
                    xl_bad.append(f"{name} {per} xlsx: the answer isn't in it")
                want_n = {}
                for lab, val in kpis(part):
                    if shown(val) is not None:
                        want_n.setdefault(lab, []).append((val, *shown(val)))
                for row in wb["Report"].iter_rows(min_col=1, max_col=2):
                    lab, cell = row[0].value, row[1]
                    if lab in want_n and want_n[lab] and isinstance(cell.value, str) and cell.value.startswith("="):
                        got, (val, exp, tol) = xc.evaluate(f"Report!{cell.coordinate}"), want_n[lab].pop(0)
                        if not isinstance(got, (int, float)) or abs(got - exp) > tol:
                            xl_bad.append(f"{name} {per} xlsx: {lab}: file {got}, site {val}")
                left = [f"{lab} ({v[0][0]})" for lab, v in want_n.items() if v]
                if left:
                    xl_bad.append(f"{name} {per} xlsx: headline figures not linked to their workings: {'; '.join(left[:3])}")
            except Exception as e:                   # a workbook that won't open is a mismatch too
                xl_bad.append(f"{name} {per} xlsx: couldn't read it ({e})")

# the home page's sample statements (September): each business's PDF and slides carry its headline figures and statement totals
dash = json.loads((REPO / "data" / "dashboard.json").read_text(encoding="utf-8"))
for o in dash["orgs"]:
    files = {fmt: REPO / href for fmt, href in (o.get("exports") or {}).items()}
    acct = lambda v: f"({-v:,})" if v < 0 else f"{v:,}"
    want = [norm(k["value"]) for k in o["fourth"]["kpis"]]
    want += [acct(rw["values"][0]) for st in ("pnl", "bs", "cf") for rw in o["statements"][st].get("rows", [])
             if rw.get("values") and rw["level"] in ("total", "key")]
    for fmt in ("xlsx", "pdf", "pptx"):
        if fmt not in files or not files[fmt].exists():
            missing.append(f"home sample statements {o['id']}: no {fmt}")
    for fmt, read in (("pdf", pdf_text), ("pptx", pptx_text)):
        if fmt in files and files[fmt].exists():
            text = read(files[fmt])
            gone = [w for w in want if w not in text]
            if gone:
                text_bad.append(f"{o['id']}-sample-statements {fmt}: not in the file: " + "; ".join(gone[:4]))

report(f"1. every report's spreadsheet, PDF and slides exist ({len(runs)} report runs)", missing)
report("2. every PDF and slide deck says what the site says (its answer, every headline figure, the period)", text_bad)
report("3. every spreadsheet's headline figures, recalculated from its workings, equal the site's (and it has the answer)", xl_bad)
leftover = sorted(str(p.relative_to(REPO)) for p in (REPO / "media" / "exports" / "reports").rglob("*")
                  if p.is_file() and p.suffix in (".xlsx", ".pdf", ".pptx") and p.resolve() not in linked)
report("4. no export file is left over that no report links to", leftover)
print("PROBLEMS:", fails)
sys.exit(1 if fails else 0)
