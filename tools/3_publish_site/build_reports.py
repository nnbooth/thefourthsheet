#!/usr/bin/env python3
"""
build_reports.py — one page per question on the SME and not-for-profit pages.

The writers for the reports worked out by tools/3_publish_site/fourthsheet (from the data, for any period). Every file
is built from scratch in code, no templates:
  report-<slug>.html                          the page (header, nav, contact and footer copied from sme.html;
                                              the report itself is drawn by script.js, with a Period dropdown)
  media/exports/reports/<period>/<slug>.xlsx  data as values, every calculation a formula, print-checked
  media/exports/reports/<period>/<slug>.pdf   A4, vector charts, header and footer on every page
  media/exports/reports/<period>/<slug>.pptx  the PDF's sections as slides, native charts

Run via tools/1_build_data/sample_data.py, or one report and period with tools/3_publish_site/report.py.
"""

import copy
import json
import re
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill
from openpyxl.utils import get_column_letter

import data_status as ds
import exportkit as ek

Font = ek.xl_font       # every Excel font is Roboto (exportkit.XL_FONT)
import publish_dashboard as pd

REPO = Path(__file__).resolve().parent.parent.parent
OUT = REPO / "media" / "exports" / "reports"
AUDIENCE = {"sme": ("sme.html", "SMEs"), "nfp": ("not-for-profit.html", "Not-for-profits")}


# ------------------------------------------------------------------ page data

def strip(o):
    """Drop the Excel-only parts of every set of workings."""
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if k != "xl"}
    if isinstance(o, list):
        return [strip(v) for v in o]
    return o


# A live report (Power BI "Publish to web", or any iframe) in place of a report's charts, in the same shell: Period picker,
# Export menu, headline numbers and notes stay; the charts become the embed. {period} is replaced with YYYY-MM.
# e.g. EMBEDS = {"job-margins": "https://app.powerbi.com/view?r=...&pageName=...&filter=Period/Month eq '{period}'"}
EMBEDS = {}


def share_matches_description(h):
    """A page's og:description and twitter:description say what its own meta description says."""
    d = re.search(r'<meta name="description" content="([^"]*)"', h).group(1)
    for k in (r'(<meta property="og:description" content=")[^"]*', r'(<meta name="twitter:description" content=")[^"]*'):
        h = re.sub(k, lambda m: m.group(1) + d, h, count=1)
    return h


def file_parts(r):
    """The downloads for a report: one set per business. A report that shows two separate businesses (growth: trades and
    services) gives each its own Excel, PDF and PowerPoint, holding that business only: they're never in one file."""
    if len(r["blocks"]) < 2 or not all(b.get("org") for b in r["blocks"]):
        return [r]
    return [{**r, "blocks": [b], "business": b["business"], "org": b["org"], "file": f"{r['slug']}-{b['org']}"} for b in r["blocks"]]


SHORT = {"cost-to-win": "Cost to win a customer", "job-margins": "Job margins", "growth": "Growth by line", "cash-payroll": "Cash cover for payroll",
         "cost-to-raise": "Cost to raise a dollar", "program-cost": "Program cost", "runway": "Runway", "funding": "Funding worth chasing",
         "board": "Board summary", "callbacks": "Callbacks", "overtime": "Overtime", "people-helped": "People helped",
         "calls": "Calls for help", "volunteers": "Volunteer hours"}       # the report's name in a download's file name (a question mark can't go in a file name)


def file_name(r):
    return r.get("file", r["slug"])


def in_short(r):
    """The report's one-line answer, as the site shows it, for the top of every download. Not for a report split into one
    file per business: its answer speaks for both, and the businesses never share a file."""
    return None if r.get("file") else r.get("answer")


def page_payload(reports):
    out = {}
    for r in reports:
        r = copy.deepcopy(r)
        for b in r["blocks"]:
            for sec in b["sections"]:
                if sec["type"] == "series":
                    sups = {}
                    for vid, v in sec["views"].items():
                        line = vid.split("|")[0]
                        if v.get("supports") and line not in sups:
                            sups[line] = v["supports"]
                        v.pop("supports", None)
                    sec["supports"] = sups
        r.pop("data", None)
        for b in r["blocks"]:
            b.pop("data", None)
            b.pop("table_xl", None)
        parts = r.pop("_parts", None) or [{"file": r["slug"], "label": None, "meta": r.get("exports_meta") or {}}]
        paths = lambda f: {k: f"media/exports/reports/{r['period']}/{f}.{k}" for k in ("xlsx", "pdf", "pptx")}
        r["exports"], r["exports_meta"] = paths(parts[0]["file"]), parts[0]["meta"]
        if len(parts) > 1:          # separate businesses: the Export menu hands out the files of the business on screen
            r["exports_by_business"] = {p_["label"]: {"exports": paths(p_["file"]), "meta": p_["meta"]} for p_ in parts}
        if EMBEDS.get(r["slug"]):
            r["embed_url"] = EMBEDS[r["slug"]].replace("{period}", r["period"])
        r["status"] = [{"label": date.fromisoformat(m + "-01").strftime("%B %Y"), "status": ds.month_status(m)[0], "note": ds.month_status(m)[1]}
                       for m in r["status_months"][1:]]
        out[r["slug"]] = strip(r)
    return out


# ---------------------------------------------------------------------- pages

PRELOAD = re.compile(r'\n[ \t]*<link rel="preload" href="data/[^"]*" as="fetch" crossorigin>')


def data_preloads(head, paths, v):
    """A page's <head> asks for its data files (data/*.json) straight away, so script.js's fetch of them is already
    under way. Replaces whichever ones the head copied from had."""
    links = "".join(f'\n    <link rel="preload" href="{p}?v={v}" as="fetch" crossorigin>' for p in paths)
    return PRELOAD.sub("", head).replace("\n  </head>", links + "\n  </head>", 1)


def write_pages(reports):
    sme = (REPO / "sme.html").read_text()
    head, rest = sme.split("<main id=\"main\">", 1)
    main, tail = rest.split("</main>", 1)
    contact = main[main.index("      <!-- CONTACT -->"):]
    dialog = ('''      <dialog class="assumptions" id="support-dialog" aria-labelledby="support-title">
        <div class="assumptions-head">
          <h2 id="support-title">How it's worked out</h2>
          <button type="button" class="assumptions-close" id="support-close" aria-label="Close">&times;</button>
        </div>
        <div class="assumptions-body" id="support-body"></div>
      </dialog>
''')
    v = re.search(r'script\.js\?v=([\w-]+)', sme).group(1)
    for r in reports:
        page, label = AUDIENCE[r["audience"]]
        dl = f"media/exports/reports/{r['period']}/{r['slug']}"
        h = head.replace("<title>SMEs | The Fourth Sheet</title>", f"<title>{r['question']} | The Fourth Sheet</title>")
        h = re.sub(r'(<meta name="description" content=")[^"]*', lambda m: m.group(1) + r["intro"].replace('"', "'"), h, count=1)
        h = share_matches_description(h)
        h = h.replace("/sme.html", f"/report-{r['slug']}.html").replace("SMEs | The Fourth Sheet", f"{r['question']} | The Fourth Sheet")
        if r["audience"] == "nfp":
            h = h.replace('<a href="sme.html" aria-current="page">Businesses</a>', '<a href="sme.html">Businesses</a>')
            h = h.replace('<a href="not-for-profit.html">Not-for-profits</a>', '<a href="not-for-profit.html" aria-current="page">Not-for-profits</a>')
        body = f'''<main id="main">
      <!-- REPORT: generated by tools/3_publish_site/build_reports.py from tools/reports.py ({r['slug']}). Sample data. -->
      <section class="section page-top report-page" id="report" data-report="{r['slug']}">
        <div class="container">
          <p class="eyebrow report-crumb"><a href="{page}">{label}</a> · Example report</p>
          <h1>{r['question']}</h1>
          <p class="lead">{r['intro']}</p>
          <div class="report-head-row">
          <div class="report-period"><label for="report-period">Period</label>
            <select id="report-period">{''.join(f'<option value="{o["value"]}"{" selected" if o["value"] == r["period"] else ""}>{o["label"]}{" (incomplete)" if o["status"] == "Incomplete" else ""}</option>' for o in r["periods"])}</select>
            <span class="report-period-note" id="report-period-note"></span></div>
          <div class="report-export" id="report-export"><noscript><a href="{dl}.xlsx" download>Spreadsheet</a> · <a href="{dl}.pdf" download>PDF</a> · <a href="{dl}.pptx" download>Slides</a></noscript></div>
          </div>
          <p class="report-meta" id="report-meta"><span class="dash-sample">Sample data</span> {r['business']}</p>
          <div id="report-root"><noscript><p>Turn on JavaScript to see this report, or download it:
            <a href="{dl}.pdf">PDF</a> · <a href="{dl}.xlsx">spreadsheet</a> · <a href="{dl}.pptx">slides</a>.</p></noscript></div>
          <p class="report-back-line"><a class="report-back" href="{page}#reports">&larr; Back to {label}</a></p>
        </div>
{dialog}      </section>
{contact}    </main>'''
        h = data_preloads(h, [f"data/reports/{r['slug']}.json"], v)      # its own data file, every period
        (REPO / f"report-{r['slug']}.html").write_text(h + body + tail)


# ------------------------------------------------------------- filters in exports

SHOW_DEFINITIONS = True    # False = leave the "gross margin, not profit" boxes out of the Excel, PDF and PowerPoint versions


def flat_sections(b):
    """A printout can't be filtered: give each filter value its own run of sections (headline numbers,
    chart, notes), then the sections that show every value at once (month charts, tables)."""
    secs = [x for x in b["sections"] if SHOW_DEFINITIONS or x["type"] != "definition"]
    if not b.get("filter"):
        return secs
    out = [sec for sec in secs if sec["type"] in ("definition", "insight")]     # what the numbers mean, first
    for opt, lab in b["filter"]["options"]:
        out.append({"type": "heading", "text": f"{b['filter']['label']}: {lab}"})
        for sec in secs:
            if sec["type"] == "vary" and opt in sec["by"]:
                out.append(sec["by"][opt])
            elif sec["type"] == "bars" and sec.get("highlight_filter") and opt == b["filter"]["options"][0][0]:
                out.append(sec)
    out.append({"type": "heading", "text": "Every " + b["filter"]["label"].lower() + " at once"})
    out += [sec for sec in secs if sec["type"] not in ("vary", "definition", "insight") and not (sec["type"] == "bars" and sec.get("highlight_filter"))]
    return out


# ---------------------------------------------------------------------- Excel

def months_status(r, sep=" · "):
    return [(date.fromisoformat(m + "-01").strftime("%B %Y"), *ds.month_status(m)) for m in r["status_months"]]


RANK = {"kpis": 0, "bars": 1, "series": 2, "table": 3, "insight": 4, "text": 5, "list": 6, "definition": 7}


def report_order(secs):
    """The Report sheet reads top down: headline numbers, then the chart, then tables, then the notes.
    Headings (one per filter value) keep their own run of sections together."""
    out, run = [], []
    for x in secs + [{"type": "heading", "_end": True}]:
        if x["type"] == "heading":
            out += sorted(run, key=lambda y: RANK.get(y["type"], 9))
            run = []
            if not x.get("_end"):
                out.append(x)
        else:
            run.append(x)
    return out


def write_xlsx(r, out=OUT):
    wb = ek.xl_default_font(Workbook())
    filename = f"{file_name(r)}.xlsx"
    retrieved = ds.as_at_text()
    sub = f"{r['business']} · SAMPLE DATA (invented) · The Fourth Sheet · {ek.MADE_WITH['xlsx']}"
    status = (f"Period: {r['period_label']} · Data status: " + " · ".join(f"{date.fromisoformat(m + '-01').strftime('%b %Y')} {ds.month_status(m)[0].lower()}"
                                           for m in r["status_months"]) + f" (data retrieved {retrieved}) · {ek.generated_text()}")
    pages = {}
    ws = wb.active
    ws.title = "Report"
    wk = wb.create_sheet("Workings")
    pd.title_block(ws, r["question"], sub, status)
    pd.title_block(wk, "How each number is worked out", sub, status)
    rr, wr, wstarts, starts = 5, 5, [], []
    if in_short(r):
        ws.cell(rr, 1, f"In short: {in_short(r)}").font = Font(bold=True, color=pd.INK)
        ws.cell(rr, 1).alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=rr, start_column=1, end_row=rr, end_column=4)
        ws.row_dimensions[rr].height = 32
        rr += 1
    ws.cell(rr, 1, r["intro"]).alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=rr, start_column=1, end_row=rr, end_column=4)
    ws.row_dimensions[rr].height = 32
    rr += 2
    blocks = r["blocks"]
    used_names = set()
    for b in blocks:
        if b.get("label"):
            starts.append(rr)
            ws.cell(rr, 1, b["label"]).font = Font(bold=True, size=13, color=pd.GREEN)
            rr += 1
        for sec in report_order(flat_sections(b)):
            t = sec["type"]
            if t == "heading":
                starts.append(rr)
                ws.cell(rr, 1, sec["text"]).font = Font(bold=True, size=12, color=pd.GREEN)
                rr += 1
            elif t == "kpis":
                starts.append(rr)
                pd.head_cells(ws, rr, ["Headline number", "Value", "Compared with"])
                for it in sec["items"]:
                    rr += 1
                    wr, rowmap, st = pd.xl_support(wk, wr, it["support"])
                    wstarts.append(st)
                    xrows = it["support"]["xl"]["rows"]
                    ws.cell(rr, 1, it["label"])
                    target = ek.shown(it["value"])
                    hit = ek.matching_cell(xrows, *target) if target else None
                    if target and hit is None:    # a headline figure with no working that produces it: stop, never publish a guess
                        raise SystemExit(f"{r['slug']} {r['period']}: '{it['label']}' shows {it['value']} but no line of its workings is that number")
                    if hit is None:               # not a number (e.g. "–"): the text, as shown
                        c = ws.cell(rr, 2, it["value"])
                    else:
                        j, col = hit
                        c = ws.cell(rr, 2, f"=Workings!{get_column_letter(2 + col)}{rowmap[j]}")
                        c.number_format = pd.F[xrows[j]["kind"]]
                    ek.xl_name(wb, (b.get("label") + " " if b.get("label") else "") + it["label"], "Report", f"B{rr}", used_names)
                    cc = ws.cell(rr, 3, it.get("sub", ""))
                    cc.font = Font(color=pd.MUTED)
                    cc.alignment = Alignment(indent=1)
                rr += 2
            elif t == "bars":
                ch = sec["chart"]
                starts.append(rr)
                ws.cell(rr, 1, ch["title"]).font = Font(bold=True, color=pd.INK)
                rr += 1
                views = ch.get("views") or [{"label": ch.get("series_name") or ch["title"].split(",")[0], "values": ch["values"], "format": ch["format"]}]
                pd.head_cells(ws, rr, ["", *[vw["label"] for vw in views]])
                bars_hr = rr
                det = ch.get("details") or []
                for i, lab in enumerate(ch["labels"]):
                    rr += 1
                    ws.cell(rr, 1, lab)
                    if det:
                        wr, rowmap, st = pd.xl_support(wk, wr, det[i])
                        wstarts.append(st)
                        n = len(det[i]["xl"]["rows"])
                    for c, vw in enumerate(views, 2):
                        pc = vw["format"].startswith("pct")
                        kind = "pct" if pc else "cents" if vw["format"] == "cents_int" else "int" if vw["format"] == "int" else "money"
                        val = vw["values"][i]
                        num, tol = (val / 100, 0.0005 + 1e-9) if pc else (val, 0.5 + 1e-9)
                        hit = ek.matching_cell(det[i]["xl"]["rows"], num, tol) if det and val is not None else None
                        if hit is not None:  # linked to the working that produced it (the cell whose value is this bar)
                            j, col = hit
                            ws.cell(rr, c, f"=Workings!{get_column_letter(2 + col)}{rowmap[j]}").number_format = pd.F[det[i]["xl"]["rows"][j]["kind"]]
                        else:              # nothing produces it on its own (e.g. a count): the value itself
                            ws.cell(rr, c, val / 100 if pc and val is not None else val).number_format = pd.F[kind]
                if sec.get("support"):
                    wr, rowmap, st = pd.xl_support(wk, wr, sec["support"])
                    wstarts.append(st)
                v0 = views[0]
                pc0 = v0["format"].startswith("pct")
                tgt = v0.get("target", ch.get("target"))
                ek.xl_bar_chart(ws, f"F{bars_hr}", ch["title"], (ws, 1, bars_hr + 1, 1, rr), (ws, 2, bars_hr + 1, 2, rr), len(ch["labels"]),
                                "0.0%" if pc0 else '0"¢"' if v0["format"] == "cents_int" else "#,##0;(#,##0)", v0["label"],
                                tgt, (f"{tgt:.1f}%" if pc0 else str(tgt)) if tgt is not None else None,
                                below=None if ch.get("plain") else [tgt is not None and v < tgt for v in v0["values"]],
                                bad=[x >= 1 for x in v0["values"]] if ch.get("variance") else [v < 0 for v in v0["values"]],
                                warn=[0.05 <= abs(x) < 1 for x in v0["values"]] if ch.get("variance") else None,
                                values=[v / 100 if pc0 else v for v in v0["values"]],          # the cells' own units
                                lines=[(f"Target {tgt:.1f}%" if pc0 else f"Target {tgt}", (tgt / 100 if pc0 else tgt) if tgt is not None else None, "25342A", "dash"),
                                       (f"Break-even {be_:.1f}%" if (be_ := v0.get("breakeven", ch.get("breakeven"))) is not None else "", (be_ / 100) if be_ is not None and pc0 else None, "B42318", "sysDot")])
                rr = max(rr, bars_hr + int(max(5.5, 0.75 * len(ch["labels"]) + 2) / 0.53) + 1)     # the next chart starts below this one
                rr += 2
            elif t in ("text", "list", "definition", "insight"):
                starts.append(rr)
                if t == "insight":
                    wr, rowmap, st = pd.xl_support(wk, wr, sec["support"])
                    wstarts.append(st)
                items = ([("What it shows", sec["shows"]), ("What you'd do about it", sec["action"])] if t == "text" else
                         [(sec["title"], "\n".join("• " + x for x in sec["items"]))] if t == "list" else
                         [(sec["title"], sec["text"] + (" (Workings sheet: \"From gross margin to profit\".)" if t == "insight" else ""))])
                for head, body in items:
                    ws.cell(rr, 1, head).font = Font(bold=True, color=pd.GREEN)
                    c = ws.cell(rr + 1, 1, body)
                    c.alignment = Alignment(wrap_text=True, vertical="top")
                    ws.merge_cells(start_row=rr + 1, start_column=1, end_row=rr + 1, end_column=4)
                    ws.row_dimensions[rr + 1].height = 15 * max(2, len(body) // 95 + body.count("\n") + 1)
                    rr += 3
            elif t == "table":
                if b.get("table_xl"):
                    continue          # written with formulas on the block's own sheet
                starts.append(rr)
                ws.cell(rr, 1, sec["title"]).font = Font(bold=True, color=pd.INK)
                rr += 1
                pd.head_cells(ws, rr, sec["head"])
                for row_ in sec["rows"]:
                    rr += 1
                    for c, v in enumerate(row_, 1):
                        ws.cell(rr, c, v).alignment = Alignment(horizontal="left" if c == 1 else "right")
                rr += 2
            elif t == "series":
                ws.cell(rr, 1, f"{sec['title']}: every month is on the Data sheet{'s' if len(blocks) > 1 else ''}.").font = Font(italic=True, color=pd.MUTED)
                rr += 2
    for col, wdt in zip("ABCD", (52, 20, 44, 18)):
        ws.column_dimensions[col].width = wdt
    wk.column_dimensions["A"].width = 58
    for col in "BCD":
        wk.column_dimensions[col].width = 20
    pages["Report"] = (None, starts, rr)
    pages["Workings"] = (None, wstarts, wr)

    # data sheets: values as data, calculations as formulas
    datas = [(r.get("data"), "Data")] if r.get("data") else []
    for b in blocks:
        if b.get("data"):
            datas.append((b["data"], f"Data {b['label']}"[:31]))
        if b.get("table_xl"):
            datas.append((b["table_xl"], f"Year to date {b['label']}"[:31]))
    for d, name in datas:
        w = wb.create_sheet(name)
        pd.title_block(w, name, sub, status)
        r0 = 5
        refs = {}
        for key_, lab, val, kind in d.get("inputs", []):
            w.cell(r0, 1, lab)
            c = w.cell(r0, 2, val)
            c.number_format = pd.F[kind]
            refs[key_] = f"$B${r0}"
            r0 += 1
        hr = r0 + (1 if d.get("inputs") else 0)
        pd.head_cells(w, hr, d["head"])
        grp_starts = []
        prev = None
        for i, row_ in enumerate(d["rows"]):
            rw = hr + 1 + i
            if prev is not None and row_[0] != prev and name.startswith("Data") and len(d["rows"]) > 30:
                grp_starts.append(rw)
            prev = row_[0]
            for c, (v, kind) in enumerate(zip(row_, d["kinds"]), 1):
                if isinstance(v, str) and v.startswith("="):
                    v = v.replace("{r}", str(rw))
                    for k_, ref in refs.items():
                        v = v.replace("{" + k_ + "}", ref)
                cell = w.cell(rw, c, v)
                cell.number_format = pd.F[kind]
                if kind != "text":
                    cell.alignment = Alignment(horizontal="right")
        for c in range(1, len(d["head"]) + 1):
            w.column_dimensions[get_column_letter(c)].width = 34 if c == 1 else 16
        w.freeze_panes = f"B{hr + 1}"
        last_r = hr + len(d["rows"])
        ek.xl_table(w, f"{r['slug']} {name}", hr, last_r, len(d["head"]))
        # a native line chart beside the data: each line's first money column by month, or the daily cash
        head = d["head"]
        xcol = head.index("Month") + 1 if "Month" in head else head.index("Date") + 1 if "Date" in head else None
        money_cols = [i + 1 for i, k in enumerate(d["kinds"]) if k == "money"]
        if xcol and money_cols and len(d["rows"]) > 2:
            vcol = money_cols[-1] if "Date" in head else money_cols[0]
            groups, g0 = [], 0
            if "Month" in head and head[0] != "Month":
                for i in range(1, len(d["rows"]) + 1):
                    if i == len(d["rows"]) or d["rows"][i][0] != d["rows"][g0][0]:
                        groups.append((str(d["rows"][g0][0]), hr + 1 + g0, hr + i)); g0 = i
            else:
                groups = [(head[vcol - 1], hr + 1, last_r)]
            n0 = groups[0][2] - groups[0][1]
            groups = [g for g in groups if g[2] - g[1] == n0][:7]           # same months for every line
            ek.xl_line_chart(w, f"{get_column_letter(len(head) + 2)}{hr}", f"{head[vcol - 1]} by {head[xcol - 1].lower()}",
                             (w, xcol, groups[0][1], groups[0][2]), [(g[0], (w, vcol, g[1], g[2])) for g in groups], "#,##0;(#,##0)")
        pages[name] = (hr, grp_starts, last_r)
    review = []
    for w in wb.worksheets:
        if w.title not in pages:
            continue                  # the hidden 'Chart lines' sheet (points for target lines)
        hr, st, last = pages[w.title]
        ek.xl_print(w, r["business"], filename, retrieved, landscape=True, header_row=hr)
        review.append(ek.xl_review(w, ek.xl_breaks(w, st, last, hr), hr))
    ek.xl_finish(wb)
    ek.save_if_changed(wb.save, Path(out) / filename)
    return review


# ------------------------------------------------------------------------ PDF

def html_report(r):
    esc = ek.esc
    parts = [f'<p style="font-size:13px;font-weight:700;margin:0 0 10px">In short: {esc(in_short(r))}</p>'] if in_short(r) else []
    for b in r["blocks"]:
        if b.get("label"):
            parts.append(f"<h2 class=block>{esc(b['label'])}</h2>")
        for sec in flat_sections(b):
            t = sec["type"]
            if t == "heading":
                parts.append(f"<h2 class=sub>{esc(sec['text'])}</h2>")
            elif t == "kpis":
                parts.append("<div class=kpis>" + "".join(f"<div class=kpi><span>{esc(i['label'])}</span><b>{ek.neg_html(i['value'])}</b><em>{esc(i.get('sub', ''))}</em></div>" for i in sec["items"]) + "</div>")
            elif t == "bars":
                ch = sec["chart"]
                views = ch.get("views") or [{"label": "", "values": ch["values"], "format": ch["format"], "target": ch.get("target")}]
                parts.append(f"<h3>{esc(ch['title'])}</h3>")
                for vw in views:
                    lab = f"<p class=viewlabel>{esc(vw['label'])}</p>" if len(views) > 1 else ""
                    spec = ek.bar_spec(ch, vw, views)
                    parts.append("<div class=chart>" + lab + ek.hbar_svg(spec) + "</div>")
            elif t == "series":
                dims = sec.get("dims") or {}
                line = (dims.get("line") or ["All"])[0]
                parts.append(f"<h3>{esc(sec['title'])}</h3>")
                for mid, mlab in (dims.get("measure") or [])[:2]:
                    vw = sec["views"].get(f"{line}|{mid}")
                    if not vw:
                        continue
                    s0 = next(i for i, v in enumerate(vw["values"]) if v is not None)      # growth starts once there's a year to compare
                    f = {"money0": "money0", "pct1": "pct1", "cents_int": "cents_int", "int": "int"}.get(vw["format"], "money0")
                    parts.append(f"<div class=chart><p class=viewlabel>{esc(line if line != 'All' else 'All')} · {esc(mlab)}</p>" + ek.area_svg(sec["labels"][s0:], vw["values"][s0:], sec["status"][s0:], f) + "</div>")
                if sec.get("note"):
                    parts.append(f"<p class=note>{esc(sec['note'].replace(' Tap a month for its workings.', ''))} Every month, by line, is in the spreadsheet download.</p>")
            elif t == "table":
                small = " class=small" if len(sec["rows"]) <= 15 else ""
                parts.append(f"<h3>{esc(sec['title'])}</h3><table{small}><thead><tr>" + "".join(f"<th{' class=n' if i else ''}>{esc(h)}</th>" for i, h in enumerate(sec["head"])) + "</tr></thead><tbody>"
                             + "".join("<tr>" + "".join(f"<td{' class=n' if i else ''}>{ek.neg_html(c) if i else esc(c)}</td>" for i, c in enumerate(row_)) + "</tr>" for row_ in sec["rows"]) + "</tbody></table>"
                             + (f"<p class=note>{esc(sec['note'])}</p>" if sec.get("note") else ""))
            elif t == "text":
                parts.append(f"<div class=two><div class=box><h4>What it shows</h4><p>{esc(sec['shows'])}</p></div><div class='box act'><h4>What you'd do about it</h4><p>{esc(sec['action'])}</p></div></div>")
            elif t == "list":
                parts.append(f"<h3>{esc(sec['title'])}</h3><ul>" + "".join(f"<li>{esc(x)}</li>" for x in sec["items"]) + "</ul>")
            elif t == "definition":
                parts.append(f"<div class=def><b>{esc(sec['title'])}</b><p>{esc(sec['text'])}</p></div>")
            elif t == "insight":
                xr = sec["support"]["rows"]
                parts.append(f"<div class=insight><b>{esc(sec['title'])}</b><p>{esc(sec['text'])}</p><table class=bridge>"
                             + "".join(f"<tr><td>{esc(r_[0])}</td><td class=n>{ek.neg_html(r_[1])}</td></tr>" for r_ in xr) + "</table></div>")
    status = ek.status_box_html(months_status(r))
    return f"""<!doctype html><html><head><meta charset=utf-8>
<link rel=stylesheet href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap">
<style>
@page {{ size: A4; }} body {{ font-family: Roboto, Arial, sans-serif; color: #25342a; font-size: 10pt; margin: 0; }}
header {{ display: flex; align-items: center; gap: 10px; border-bottom: 3px solid #2f7a5d; padding-bottom: 6px; margin-bottom: 8px; }}
.mark {{ min-width: 28px; height: 28px; padding: 0 4px; border-radius: 7px; background: #2f7a5d; color: #fff; font-weight: 800; display: flex; align-items: center; justify-content: center; }}
sup {{ font-size: .55em; }} header small {{ margin-left: auto; color: #5f6f63; }}
.sample {{ display: inline-block; background: #f6f1e7; border: 1px solid #c8a77e; color: #6b5532; border-radius: 4px; padding: 1px 7px; font-size: 8pt; font-weight: 700; }}
h1 {{ font-size: 16pt; margin: 6px 0 2px; }} .intro {{ color: #5f6f63; margin: 0 0 6px; }} h2.block {{ font-size: 13pt; color: #2f7a5d; margin: 18px 0 4px; padding-top: 8px; border-top: 3px solid #2f7a5d; page-break-after: avoid; }}
h3 {{ font-size: 10.5pt; margin: 12px 0 4px; }} h2.sub {{ font-size: 11.5pt; color: #2f7a5d; margin: 16px 0 2px; border-top: 1px solid #dce8dc; padding-top: 8px; }} .viewlabel {{ margin: 4px 0 0; font-size: 8.5pt; font-weight: 700; color: #5f6f63; }}
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 6px; margin: 6px 0; }} .kpi {{ border: 1px solid #dce8dc; border-radius: 6px; padding: 6px 8px; page-break-inside: avoid; }}
.kpi span, .kpi em {{ display: block; font-size: 8pt; color: #5f6f63; font-style: normal; }} .kpi b {{ font-size: 14pt; color: #2f7a5d; }}
.chart {{ page-break-inside: avoid; margin: 2px 0 6px; }} .note {{ font-size: 8pt; color: #5f6f63; }}
.two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; page-break-inside: avoid; margin: 8px 0; }} .box {{ border: 1px solid #dce8dc; border-radius: 6px; padding: 6px 10px; }}
.neg {{ color: #B42318; }} .box.act {{ background: #eef5f0; }} .def {{ border-left: 4px solid #8a7a52; background: #fbfaf6; padding: 6px 10px; margin: 8px 0; page-break-inside: avoid; }} .def p, .insight p {{ margin: 2px 0 0; }}
.insight {{ background: #eef5f0; border: 1px solid #cfe2d6; border-radius: 6px; padding: 6px 10px; margin: 8px 0; page-break-inside: avoid; }} .bridge {{ margin-top: 6px; font-size: 8.5pt; }} .bridge tr:last-child td {{ font-weight: 700; }} .box h4 {{ margin: 0 0 3px; font-size: 9.5pt; color: #2f7a5d; }} .box p {{ margin: 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 9pt; }} table.small, table.bridge {{ page-break-inside: avoid; }} tr {{ page-break-inside: avoid; }} thead {{ display: table-header-group; }} h3 {{ page-break-after: avoid; }} th {{ text-align: left; background: #2f7a5d; color: #fff; padding: 3px 6px; }}
td {{ padding: 3px 6px; border-bottom: 1px solid #eef2ee; }} .n {{ text-align: right; font-variant-numeric: tabular-nums; }} ul {{ margin: 4px 0 8px; padding-left: 18px; }} li {{ margin: 3px 0; }}
""" + ek.STATUS_CSS + ek.MADE_WITH_CSS + f"""</style></head><body>
<header><div class=mark>4<sup>th</sup></div><b>The Fourth Sheet</b><small>Example report · {esc(AUDIENCE[r['audience']][1])}</small></header>
<span class=sample>SAMPLE DATA · invented figures for demonstration</span>
<h1>{esc(r['question'])}</h1><p class=intro><b>Period: {esc(r['period_label'])}.</b> {esc(r['intro'])}</p>
{status}
{''.join(parts)}
<p class=madewith>{ek.MADE_WITH['pdf']}.</p>
</body></html>"""


def pptx_bars(ch):
    """A report's bar chart as pptkit chart arguments (the first view: % where there is one)."""
    views = ch.get("views") or [{"label": ch.get("series_name") or ch["title"].split(",")[0], "values": ch["values"], "format": ch["format"], "target": ch.get("target")}]
    vw = views[0]
    tgt, be = vw.get("target", ch.get("target")), vw.get("breakeven", ch.get("breakeven"))
    vals = vw["values"]
    if ch.get("variance"):           # over budget red, under green, within 1% amber (judged on % of budget)
        pcts = views[0]["values"]
        bad, warn, below = [x >= 1 for x in pcts], [0.05 <= abs(x) < 1 for x in pcts], None       # over red; under green (default); within 1% amber
    else:
        below = None if ch.get("plain") else [(tgt is not None and v < tgt) or bool(vw.get("below_marks") and vw.get("marks") and v < vw["marks"][k]) for k, v in enumerate(vals)]
        bad, warn = [v < 0 for v in vals], None
    pc = str(vw["format"]).startswith("pct")
    return {"kind": "bars", "labels": ch["labels"], "values": vals, "fmt": vw["format"], "below": below, "order_by": views[0]["values"], "bad": bad, "warn": warn,
            "series_name": vw["label"], "target": tgt, "breakeven": be,
            "keep_order": bool(ch.get("keep_order")),
            "target_label": (f"Target {tgt:.1f}%" if pc else f"Target {tgt}") if tgt is not None else None,
            "breakeven_label": f"Break-even {be:.1f}%" if be is not None else None}


def pptx_area(sec, line="All"):
    dims = sec.get("dims") or {}
    mid, mlab = (dims.get("measure") or [(next(iter(sec["views"])).split("|")[1], "")])[0]
    vw = sec["views"].get(f"{line}|{mid}") or sec["views"].get(f"All|{mid}")
    if not vw:
        return None
    t = sec.get("target") or {}
    return {"kind": "area", "labels": sec["labels"], "values": vw["values"], "fmt": vw["format"], "series_name": vw["label"],
            "target": t.get("value"), "target_label": t.get("label")}


def write_pptx(r, out=OUT):
    """PowerPoint version of the report: one idea per slide (headline numbers, the chart, what it shows and what you'd do
    about it), then the tables. Native charts with the target and break-even drawn on them; speaker notes on every slide."""
    import pptkit
    status = [f"{lab}: {st}. {note}" for lab, st, note in months_status(r)]
    d = pptkit.Deck(r["business"], r["question"], f"{file_name(r)}.pptx", ds.as_at_text())
    d.title_slide(f"Period: {r['period_label']}. " + (f"In short: {in_short(r)} " if in_short(r) else "") + r["intro"], status)
    definition = None
    for b in r["blocks"]:
        secs = flat_sections(b)
        runs, cur = [], (None, [])
        for x in secs:
            if x["type"] == "heading":
                runs.append(cur); cur = (x["text"], [])
            else:
                cur[1].append(x)
        runs.append(cur)
        shared_series = [x for h, run in runs if h and h.startswith("Every ") for x in run if x["type"] == "series"]
        series_by_line = False          # set once the shared month chart has been shown line by line
        held = [x for h, run in runs if not h for x in run if x["type"] == "insight"] if b.get("filter") else []
        every_tables = [x for h, run in runs if h and h.startswith("Every ") for x in run if x["type"] == "table"]
        for head, run in runs:
            if not run:
                continue
            value = head.split(": ", 1)[1] if head and ": " in head else None          # the filter value this run is about
            every = bool(head and head.startswith("Every "))
            title = " · ".join(x for x in (b.get("label"), value) if x) or r["question"]
            used = set()
            for k, x in enumerate(run):
                if x["type"] == "definition":
                    definition = definition or x["text"]; used.add(k)
            kp = next((k for k, x in enumerate(run) if x["type"] == "kpis"), None)
            br = next((k for k, x in enumerate(run) if x["type"] == "bars"), None)
            tx = next((k for k, x in enumerate(run) if x["type"] == "text"), None)
            lists = [k for k, x in enumerate(run) if x["type"] == "list"]
            sr = next((k for k, x in enumerate(run) if x["type"] == "series"), None)
            if not every and (kp is not None or tx is not None or lists):
                chart, sub = None, None
                if br is not None and (sr is None or br < sr):
                    if len(run[br]["chart"]["labels"]) <= 8:          # more bars than that get a slide of their own
                        chart = pptx_bars(run[br]["chart"]); sub = run[br]["chart"]["title"]; used.add(br)
                elif sr is not None:
                    chart = pptx_area(run[sr]); sub = run[sr]["title"]; used.add(sr)
                elif value and shared_series and br is None:
                    chart = pptx_area(shared_series[0], value); sub = shared_series[0]["title"] + f" · {value}"
                    series_by_line = True
                blocks = []
                if tx is not None:
                    blocks += [("What it shows", run[tx]["shows"]), ("What you'd do about it", run[tx]["action"])]; used.add(tx)
                for k in lists:
                    blocks.append((run[k]["title"], "\n".join(("" if run[k].get("numbered") else "• ") + (f"{n}. " if run[k].get("numbered") else "") + it
                                                              for n, it in enumerate(run[k]["items"], 1)))); used.add(k)
                items = [(it["label"], it["value"], it.get("sub", ""), it.get("tone", "")) for it in run[kp]["items"]] if kp is not None else None
                if kp is not None:
                    used.add(kp)
                if definition and not getattr(d, "_def_shown", False):
                    sub = (sub + ". " if sub else "") + definition.split(". ")[0] + "."
                    d._def_shown = True
                notes = " ".join(x for x in [title + ".", "; ".join(f"{a}: {v_}" for a, v_, *_ in (items or [])) + ("." if items else ""),
                                              run[tx]["shows"] if tx is not None else "", run[tx]["action"] if tx is not None else ""] if x)
                tabs = [k for k, x in enumerate(run) if x["type"] == "table" and k not in used]
                table = None
                if chart is None and len(tabs) == 1 and d.fits_table(d.content_top(title, sub), items, blocks, len(run[tabs[0]]["rows"])):
                    x = run[tabs[0]]
                    table = (x["title"] + (f" · {x['note']}" if x.get("note") else ""), x["head"], x["rows"], x.get("tones")); used.add(tabs[0])
                d.combo_slide(title, items, chart, blocks or None, sub=sub, notes=notes, table=table)
            for k, x in enumerate(run):
                if k in used:
                    continue
                t = x["type"]
                name = f"{x.get('title', '')} · {b['label']}" if b.get("label") else x.get("title", "")
                if t == "insight" and x in held and every_tables:
                    continue            # goes with the year-to-date table below
                if t == "bars":
                    c = pptx_bars(x["chart"]); c.pop("kind")
                    d.bar_slide(f"{x['chart']['title']}" + (f" · {b['label']}" if b.get("label") else ""), c["labels"], c["values"], c["fmt"],
                                None, c["below"], x["chart"].get("subtitle"), c["order_by"], c["bad"], c["warn"], c["series_name"],
                                c["target"], c["breakeven"])
                elif t == "series":
                    if every and series_by_line:
                        continue            # already shown line by line on the slides above
                    c = pptx_area(x); c.pop("kind")
                    d.area_slide(name, c["labels"], c["values"], c["fmt"], (x.get("note") or "").replace(" Tap a month for its workings.", ""),
                                 c["series_name"], c["target"], c["target_label"])
                elif t == "table":
                    ins = held[0] if (held and x is every_tables[0]) else None
                    note_ = " ".join(y for y in (x.get("note"), f"{ins['title']}: {ins['text']}" if ins else None) if y)
                    d.table_slides(name, x["head"], x["rows"], sub=note_ or None)
                elif t == "insight":
                    d.table_slides(x["title"] + (f" · {b['label']}" if b.get("label") else ""), None,
                                   [[r_[0], r_[1]] for r_ in x["support"]["rows"]], sub=x["text"])
                elif t == "text":
                    d.text_slide(title, [("What it shows", x["shows"]), ("What you'd do about it", x["action"])])
                elif t == "list":
                    d.text_slide(x["title"], [(x["title"], "\n".join("• " + it for it in x["items"]))])
                elif t == "kpis":           # headline figures not already on a slide: their own slide, never dropped
                    d.kpi_slide(name or title, [(it["label"], it["value"], it.get("sub", ""), it.get("tone", "")) for it in x["items"]])
    ek.save_if_changed(d.save, Path(out) / f"{file_name(r)}.pptx")


def write_pdfs(reports, out=None):
    """One PDF per report (each into out, or its period's folder). A PDF whose content hasn't changed isn't rewritten,
    so git only sees real changes."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome")
        except Exception:
            browser = pw.chromium.launch()
        page = browser.new_page()
        for r in reports:
            dest = Path(out) if out else OUT / r["period"]
            dest.mkdir(parents=True, exist_ok=True)
            page.set_content(html_report(r), wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            ek.pdf_if_changed(page, dest / f"{file_name(r)}.pdf", **ek.pdf_options(r["business"], r["question"], f"{file_name(r)}.pdf", ds.as_at_text()))
        browser.close()


EXAMPLE_CARDS = ["job-margins", "growth", "program-cost", "runway"]     # the working reports shown on examples.html


def card_html(r, tag=None):
    """One report card: the question, a mini chart, the question answered in one sentence, and the link."""
    import html as H
    first = r.get("answer") or r["intro"]
    t = f'<span class="card-tag">{H.escape(tag)}</span>' if tag else ""
    return (f'            <li>{t}<h3><a href="report-{r["slug"]}.html">{H.escape(r["question"])}</a></h3>'
            f'<div class="card-chart" data-report-card="{r["slug"]}" aria-hidden="true"></div>'
            f'<p>{H.escape(first)}</p><a class="report-open" href="report-{r["slug"]}.html">Open the report &rarr;</a></li>')


def write_cards(reports):
    """The 'Example reports' cards on the SME and not-for-profit pages, and four on examples.html (between the REPORT CARDS markers)."""
    import html as H
    by = {r["slug"]: r for r in reports}
    f = REPO / "examples.html"
    s_ = f.read_text()
    a_, b_ = s_.index("<!-- REPORT CARDS:START -->"), s_.index("<!-- REPORT CARDS:END -->")
    cards = [card_html(by[k], "SMEs" if by[k]["audience"] == "sme" else "Not-for-profits") for k in EXAMPLE_CARDS]
    f.write_text(s_[:a_] + "<!-- REPORT CARDS:START -->\n          <ul class=\"report-cards report-cards--four\">\n" + "\n".join(cards) + "\n          </ul>\n          " + s_[b_:])
    for aud, page in (("sme", "sme.html"), ("nfp", "not-for-profit.html")):
        cards = [card_html(r) for r in reports if r["audience"] == aud]
        soon = ""
        f = REPO / page
        s_ = f.read_text()
        a_, b_ = s_.index("<!-- REPORT CARDS:START -->"), s_.index("<!-- REPORT CARDS:END -->")
        feature = {"sme": ("growth", "Which products and services are growing?", "series"),
                   "nfp": ("program-cost", "What does each program really cost?", "bars")}[aud]
        feat = (f'<div class="report-feature"><p class="eyebrow">Featured: <a href="report-{feature[0]}.html">{H.escape(feature[1])}</a></p>'
                f'<div data-report-feature="{feature[0]}" data-only="{feature[2]}"><noscript><p>Turn on JavaScript to see the chart, or '
                f'<a href="report-{feature[0]}.html">open the report</a>.</p></noscript></div></div>\n          ')
        s_ = s_[:a_] + "<!-- REPORT CARDS:START -->\n          " + feat + "<ul class=\"report-cards\">\n" + "\n".join(cards) + "\n          </ul>\n          " + soon + s_[b_:]
        f.write_text(s_)


EXPLAINED = [
    ("accrual", "Accrual accounting (what these reports assume)", "Income is counted when it's earned (the work is done and invoiced) and costs when they're incurred, "
     "whether or not the money has moved yet. Cash accounting counts income only when it's received and costs only when they're paid. Every report here uses accrual "
     "accounting, which is why profit and cash tell different stories. Many small businesses keep their books on a cash basis for tax (BAS); the numbers here won't match "
     "those, and that's expected."),
    ("revenue", "Revenue", "Everything you invoiced for the work you did in the period, before any costs. Not the same as cash received: you may still be waiting for your customers to pay."),
    ("direct-costs", "Direct costs", "What it cost to do the work itself: materials, subcontractors, and the time of the people doing the job, at a fully loaded hourly cost (wages plus all on-costs)."),
    ("gross-margin", "Gross margin (not profit)", "Revenue less direct costs. Example: a $10,000 job with $6,500 of direct costs makes $3,500 gross margin, or 35%. "
     "It is before overheads, so it is not profit. A business can have a healthy-looking gross margin and still lose money once overheads are paid."),
    ("markup", "Gross margin is not markup", "Markup is profit over cost; gross margin is profit over price. Adding 35% to a $6,500 cost gives a $8,775 price, "
     "which is only a 25.9% gross margin. Pricing with markup when you meant margin is one of the most common ways businesses undercharge."),
    ("wages", "Wages (the full cost of a person)", "In these reports, wages means everything a person costs you, not just their pay: base wage or salary, overtime, penalty "
     "rates and allowances, bonuses and commissions, plus all the on-costs below. Leave them out and every job looks cheaper than it is."),
    ("on-costs", "On-costs", "The costs on top of pay that come with employing someone: superannuation, payroll tax (above the state threshold), workers' compensation "
     "insurance, leave (annual leave, leave loading, personal leave, long service leave) and any other employment costs such as training or uniforms. "
     "A $40 an hour wage can easily cost $50 or more an hour once on-costs are added."),
    ("overheads", "Overheads", "Costs that don't belong to any one job: office and admin wages, rent, vehicles, marketing, insurance, IT, depreciation and interest. "
     "They are paid whether you do ten jobs or a hundred, and they come out of gross margin."),
    ("break-even", "The gross margin you need", "Divide your overheads (and any paid time not charged to jobs) by revenue. That is the gross margin your work needs on average just to "
     "break even. Work below it makes the business smaller in profit as it grows; work above it is what pays for everything else."),
    ("profit", "Profit", "What is left after direct costs and overheads. Profit before tax is what the business earned in the period; net profit is after income tax."),
    ("profit-vs-cash", "Profit is not cash", "Profit counts work when it's invoiced; cash counts money when it lands. Unpaid invoices, stock, loan repayments, tax and equipment "
     "purchases all make cash differ from profit, which is why a profitable business can still run short of cash."),
    ("cash-forecast", "Cash forecast", "Cash at bank today, plus the money expected in (each unpaid invoice on its customer's usual payment date, and new work at its recent rate), "
     "less the money due out (pay runs, supplier bills, the BAS and loan repayments on their due dates), day by day, on banking days only. It's only as good as its assumptions, so a good one is checked "
     "against the bank as the days arrive and says why it was out."),
    ("gst-bas", "GST and BAS", "GST is 10% added to most sales and charged on most bills. Each quarter the business pays the ATO the GST it charged less the GST it paid "
     "(its GST credits), plus the PAYG tax withheld from employees' pay and, for a company, an income tax instalment: that payment is the BAS (business activity statement). "
     "In these reports the P&L leaves GST out, because it isn't the business's money; invoices, bills, unpaid invoices, bills owed and cash include it. GST is counted when "
     "an invoice or bill is issued (the accruals basis), and a quarterly BAS is due on the 28th of the month after the quarter (October to December: 28 February). "
     "Wages, super and bank interest carry no GST; donations to a charity carry none either."),
    ("debtors", "Unpaid invoices (debtors)", "Money customers owe you for work already invoiced. It is yours, but you can't spend it until it's paid."),
    ("wip", "Work in progress", "Work done but not yet invoiced, valued at what you'll bill for it. It turns into an invoice, then into cash, later."),
    ("unrestricted-cash", "Unrestricted cash", "For a not-for-profit: cash at bank less grant money received but not yet spent, and less the GST and PAYG tax "
     "held for the ATO until the next BAS. The unspent grant money belongs to the funder's program and the tax belongs to the ATO, so neither can pay general bills."),
    ("runway", "Runway", "How many months the organisation could keep going on its unrestricted cash at the current rate of spending, with no new money coming in."),
    ("cost-to-raise", "Cost to raise a dollar", "Fundraising costs (grant writing, donor campaigns, events) divided by the money they bring in, in cents. 20¢ means every dollar raised cost 20 cents to raise, "
     "on average. It is an average, not a marginal cost: the next dollar can cost more or less to raise than the last. To judge one more campaign or event, compare its own extra cost with the extra money it brings in."),
    ("year-on-year", "Growth, year on year", "This month against the same month a year earlier, so seasonal ups and downs don't look like growth or decline."),
    ("status", "Locked, provisional, incomplete", "Locked: the month is closed and won't change. Provisional: the month is over but not closed, so late invoices and adjustments can still change it. "
     "Incomplete: still happening, like today or the month so far."),
]


def write_explainer():
    """numbers-explained.html: plain-English definitions, linked from every report's definition box."""
    import html as H
    sme = (REPO / "sme.html").read_text()
    head, rest = sme.split('<main id="main">', 1)
    main, tail = rest.split("</main>", 1)
    contact = main[main.index("      <!-- CONTACT -->"):]
    h = head.replace("<title>SMEs | The Fourth Sheet</title>", "<title>The numbers, explained | The Fourth Sheet</title>")
    h = re.sub(r'(<meta name="description" content=")[^"]*', lambda m: m.group(1) + "Plain-English definitions of the numbers in the reports: gross margin, overheads, profit, cash, runway and more.", h, count=1)
    h = share_matches_description(h)
    h = h.replace("/sme.html", "/numbers-explained.html").replace("SMEs | The Fourth Sheet", "The numbers, explained | The Fourth Sheet")
    h = data_preloads(h, [], "")
    h = h.replace('<a href="sme.html" aria-current="page">Businesses</a>', '<a href="sme.html">Businesses</a>')
    items = "\n".join(f'            <div class="explain" id="{i}"><dt>{H.escape(t)}</dt><dd>{H.escape(d)}</dd></div>' for i, t, d in EXPLAINED)
    opts = "\n".join(f'              <option value="{i}">{H.escape(t)}</option>' for i, t, d in EXPLAINED)
    jumps = "\n".join(f'            <li><a href="#{i}">{H.escape(t)}</a></li>' for i, t, d in EXPLAINED)
    body = f'''<main id="main">
      <!-- THE NUMBERS, EXPLAINED: generated by tools/3_publish_site/build_reports.py (EXPLAINED). Linked from every report's definition box. -->
      <section class="section page-top">
        <div class="container narrow">
          <p class="eyebrow">Plain English</p>
          <h1 data-title-bar>The numbers, explained.</h1>
          <div class="title-bar" id="title-bar"><div class="container narrow title-bar-inner"><strong>The numbers, explained.</strong>
            <select aria-label="Jump to a term"><option value="">Jump to a term…</option>
{opts}
            </select></div></div>
          <p class="lead">The words in the reports, in plain English. The three that catch most businesses out: gross margin is not profit, wages always include on-costs, and profit is not cash. Everything here assumes accrual accounting (explained first).</p>
          <nav class="jump-list" aria-label="Terms on this page"><ul>
{jumps}
          </ul></nav>
          <dl class="explain-list">
{items}
          </dl>
        </div>
      </section>
{contact}    </main>'''
    (REPO / "numbers-explained.html").write_text(h + body + tail)
