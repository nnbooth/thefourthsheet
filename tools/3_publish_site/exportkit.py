#!/usr/bin/env python3
"""
exportkit.py — shared look for every Excel and PDF export, so they print
properly and look the same.

  hbar_svg(chart)          horizontal bar chart as vector SVG (for PDFs):
                           categories down the left, value labels on the
                           bars' ends, the target line ON TOP, and a label
                           that would hit the target line moves past it
  status_box_html(...)     the "how final is this data" panel for page 1
  pdf_footer(...)          footer on every PDF page: page X of Y, status
  xl_print(ws, ...)        Excel print setup: orientation, fit to width,
                           repeated header rows, footer, no gridlines

Palette (muted, and still distinct when printed in black and white):
  sage #0E9F6E on target · sand #b28a92 below target · brick #8f4a3e very
  late / overdue · slate #8e9cab on its way · near-black #2f2f2f targets.
"""

from datetime import date

GOOD, SOME, BAD, OPEN, INK, MUTED, LINE = "#0E9F6E", "#7D8790", "#b42318", "#8e9cab", "#2f2f2f", "#5f6f63", "#dce8dc"
NEG = "#B42318"     # negative numbers: always red, in brackets
NEG_CSS = ".neg {{ color: #B42318; }}"


def tone(value, good_when="higher", target=None, warn_within=0):
    """Colour by meaning, not by sign (the same rule as script.js tone()): 'good', 'warn' or 'bad' against a target,
    where good_when is 'higher' (more is better: margin, runway) or 'lower' (less is better: cost to win, cents per $1).
    Returns '' when there's nothing to judge against."""
    if value is None or target is None:
        return ""
    gap = (target - value) if good_when == "lower" else (value - target)
    if gap >= 0:
        return "good"
    return "warn" if -gap <= warn_within else "bad"


TONE_HEX = {"good": "2F7A5D", "warn": "8A6D3B", "bad": "B42318", "": None}   # text colours (good = brand green: readable on white)


def neg_html(text):
    """Wrap a formatted number in a red span if it's negative (brackets or a minus sign)."""
    t = str(text).strip()
    return f'<span class="neg">{esc(t)}</span>' if (t.startswith("(") or t.startswith("-")) and any(ch.isdigit() for ch in t) else esc(t)


STATUS_COLOUR = {"Locked": "#2f5d4a", "Provisional": "#8a6d3b", "Incomplete": "#8f4a3e", "Future": MUTED}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def shown(value):
    """The number a displayed figure stands for, and how far rounding can move it: "$1,234" -> (1234, 0.5),
    "(42.7%)" -> (-0.427, 0.0005), "1.9 months" -> (1.9, 0.05), "20¢" -> (20, 0.5). None if it isn't a number."""
    import re
    v = str(value).strip()
    neg = v.startswith("(") and v.endswith(")")
    m = re.search(r"\d[\d,]*\.?\d*|\.\d+", v)
    if not m:
        return None
    digits = m.group(0).replace(",", "").rstrip(".")
    dp = len(digits.split(".")[1]) if "." in digits else 0
    num, tol = float(digits), 0.5 * 10 ** -dp
    if "%" in v:
        num, tol = num / 100, tol / 100
    return (-num if neg else num), tol + 1e-9


def matching_cell(rows, num, tol):
    """The workings cell that produced a figure: (row, column) of the last row whose value is that figure, as rounded on
    screen, looking in this period's column first and then the others (a figure for the month before sits in column 2).
    None if no cell is. Never 'the last row': two figures can share one set of workings."""
    ncol = max((len(row["values"]) for row in rows), default=0)
    for c in range(ncol):
        hits = [j for j, row in enumerate(rows) if c < len(row["values"]) and isinstance(row["values"][c], (int, float))
                and abs(row["values"][c] - num) <= tol]
        if hits:
            return hits[-1], c
    return None


def fmt_value(v, f):
    from financial_model import round_half_up as hu        # one rounding rule everywhere: halves away from zero
    if f == "pct_var":        # over (+) or under (-) budget: said in words, so an underspend isn't a red negative
        return "on budget" if hu(v, 1) == 0 else f"{hu(abs(v), 1):.1f}% {'over' if v > 0 else 'under'}"
    if f == "money_var":
        return "on budget" if hu(v) == 0 else f"${hu(abs(v)):,} {'over' if v > 0 else 'under'}"
    if f == "pct1":
        return f"({hu(-v, 1):.1f}%)" if v < 0 else f"{hu(v, 1):.1f}%"
    if f == "pct0":
        return f"{hu(v)}%"
    if f == "money_k":
        return f"${hu(v / 1000):,}k" if abs(v) >= 1000 else f"${v}"
    if f == "money0":
        return f"(${hu(-v):,})" if v < 0 else f"${hu(v):,}"
    if f == "cents_int":
        return f"{hu(v)}¢"
    if f == "int":
        return f"{hu(v):,}"
    return str(v)


def hbar_svg(ch, width=640):
    """Horizontal bars, sorted as given. Same rules as the website chart."""
    f = ch.get("format", "pct0")
    labels, values = ch["labels"], ch["values"]
    marks, target, plain = ch.get("marks"), ch.get("target"), ch.get("plain")
    char = 6.2
    left = min(230, 12 + max(len(str(l)) for l in labels) * char)
    right = width - (170 if ch.get("notes") and any(ch["notes"]) else 60)
    row, bh, top = 24, 14, 8
    plot_h = len(values) * row
    below_marks = ch.get("below_marks")
    flags = ch.get("below_flags")
    below = lambda v, i: not plain and ((target is not None and v < target) or bool(below_marks and marks and v < marks[i]) or bool(flags and flags[i]))
    any_below = any(below(v, i) for i, v in enumerate(values))
    be = ch.get("breakeven")               # break-even gross margin: a second, dotted red line labelled on its own row
    height = top + plot_h + (14 if be is not None else 0) + (36 if (any_below or marks) else 22 if target is not None else 8)
    variance = ch.get("variance")          # over/under budget, around zero: over red, under green, within 1% amber
    mx = max(values + ([target] if target is not None else []) + ([be] if be is not None else []) + (marks or []) + [0]) * 1.08
    lo = min(values + [0]) * 1.08
    if variance:
        right = width - 90
    x = lambda v: left + (v - lo) / ((mx - lo) or 1) * (right - left)
    x0 = x(0)
    tx = x(target) if target is not None else None
    g = [f'<line x1="{x0:.1f}" x2="{x0:.1f}" y1="{top - 3}" y2="{top + plot_h}" stroke="{LINE}" stroke-width="1.5"/>']
    by = ch.get("order_by") or values
    order = list(range(len(values))) if ch.get("keep_order") else sorted(range(len(values)), key=lambda i: -by[i])     # order set by the first view; times of day keep clock order
    for pos, i in enumerate(order):
        lab, v = labels[i], values[i]
        y = top + pos * row + (row - bh) / 2
        g.append(f'<text x="{left - 8}" y="{y + bh - 3}" text-anchor="end" font-size="11" fill="{MUTED}">{esc(lab)}</text>')
        vs = (ch.get("variance_pct") or values)[i] if variance else 0          # judged on % of budget
        vp = abs(vs)
        fill = (("#8A6D3B" if vp < 1 else NEG if vs > 0 else GOOD) if vp >= 0.05 else SOME) if variance else (NEG if v < 0 else SOME if below(v, i) else GOOD)
        g.append(f'<rect x="{min(x(v), x0):.1f}" y="{y}" width="{abs(x(v) - x0):.1f}" height="{bh}" rx="2" fill="{fill}"/>')
        text = fmt_value(v, f)
        lx = max(x(v), x0) + 5
        if marks:
            mxp = x(marks[i])
            g.append(f'<line x1="{mxp:.1f}" x2="{mxp:.1f}" y1="{y - 3}" y2="{y + bh + 3}" stroke="{INK}" stroke-width="2"/>')
            if x(v) - 1 <= mxp < lx + len(text) * char + 4:    # marker in the way: label goes after it
                lx = mxp + 5
        if be is not None and lx - 4 < x(be) < lx + len(text) * char + 4:
            lx = x(be) + 5
        if tx is not None and lx - 4 < tx < lx + len(text) * char + 4:   # the label would sit on the target line
            lx = tx + 5
        note_ = (ch.get("notes") or [None] * len(values))[i]
        tail = f'<tspan fill="{NEG}" font-weight="600">  {esc(note_)}</tspan>' if note_ else ""
        tcol = (NEG if vp >= 1 and vs > 0 else "#2F7A5D" if vp >= 1 else INK) if variance else (NEG if v < 0 else INK)
        g.append(f'<text x="{lx:.1f}" y="{y + bh - 3}" font-size="10" fill="{tcol}">{esc(text)}{tail}</text>')
    if target is not None:
        g.append(f'<line x1="{tx:.1f}" x2="{tx:.1f}" y1="{top - 4}" y2="{top + plot_h + 2}" stroke="{INK}" stroke-width="1.2" stroke-dasharray="4 3"/>')
        g.append(f'<text x="{tx:.1f}" y="{top + plot_h + 15}" text-anchor="middle" font-size="10" font-weight="600" fill="{INK}">Target {fmt_value(target, f)}</text>')
    if be is not None:
        bx = x(be)
        g.append(f'<line x1="{bx:.1f}" x2="{bx:.1f}" y1="{top - 4}" y2="{top + plot_h + 18}" stroke="{NEG}" stroke-width="1.2" stroke-dasharray="1.5 2.5"/>')
        g.append(f'<text x="{bx:.1f}" y="{top + plot_h + 29}" text-anchor="middle" font-size="10" font-weight="600" fill="{NEG}">Break-even {fmt_value(be, f)}</text>')
    ky = height - 6
    if variance:
        height += 14
        ky = height - 6
        g.append(f'<rect x="{left}" y="{ky - 9}" width="10" height="10" rx="2" fill="{NEG}"/><text x="{left + 15}" y="{ky}" font-size="10" fill="{MUTED}">Over budget</text>'
                 f'<rect x="{left + 100}" y="{ky - 9}" width="10" height="10" rx="2" fill="{GOOD}"/><text x="{left + 115}" y="{ky}" font-size="10" fill="{MUTED}">Under budget</text>'
                 f'<rect x="{left + 205}" y="{ky - 9}" width="10" height="10" rx="2" fill="#8A6D3B"/><text x="{left + 220}" y="{ky}" font-size="10" fill="{MUTED}">Within 1%</text>')
    elif any_below and not marks:
        g.append(f'<rect x="{left}" y="{ky - 9}" width="10" height="10" rx="2" fill="{SOME}"/><text x="{left + 15}" y="{ky}" font-size="10" fill="{MUTED}">Below target</text>')
    if marks:
        g.append(f'<line x1="{left + 4}" x2="{left + 4}" y1="{ky - 11}" y2="{ky + 1}" stroke="{INK}" stroke-width="2"/><text x="{left + 12}" y="{ky}" font-size="10" fill="{MUTED}">{esc(ch.get("mark_label", ""))}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" '
            f'style="font-family:Roboto,Arial,sans-serif" role="img">{"".join(g)}</svg>')


def col_svg(labels, values, status, f, width=700, height=230, target=None):
    """Month-by-month columns (time series). Incomplete or provisional periods are lighter and marked;
    every column carries a small value; quarter labels along the bottom."""
    vals = [v for v in values if v is not None]
    mx = max(vals + ([target] if target is not None else []) + [0]) * 1.12 or 1
    mn = min(vals + [0])
    left, right, top, base = 8, width - 8, 30, height - 36
    span = mx - mn
    y = lambda v: base - (v - mn) / span * (base - top)
    slot = (right - left) / len(values)
    bw = slot * 0.66
    zero = y(0)
    idx = [i for i, v in enumerate(values) if v is not None]
    done = [i for i in idx if status[i] != "Incomplete"]
    keep = {max(idx, key=lambda i: values[i]), min(idx, key=lambda i: values[i]), idx[-1]} | ({done[-1]} if done else set())
    g = [f'<line x1="{left}" x2="{right}" y1="{zero:.1f}" y2="{zero:.1f}" stroke="{LINE}" stroke-width="1.5"/>']
    for i, (lab, v, st) in enumerate(zip(labels, values, status)):
        x0 = left + i * slot + (slot - bw) / 2
        cx = x0 + bw / 2
        if v is not None:
            yy = y(v)
            top_, h_ = min(yy, zero), abs(zero - yy)
            light = st in ("Incomplete", "Provisional")
            extra = f' fill-opacity="0.35" stroke="{GOOD}" stroke-dasharray="3 2"' if light else ""
            g.append(f'<rect x="{x0:.1f}" y="{top_:.1f}" width="{bw:.1f}" height="{h_:.1f}" rx="1.5" fill="{GOOD}"{extra}/>')
            if i in keep:      # latest, highest and lowest only; every month is in the Excel download
                anchor, lx = ("end", x0 + bw) if i == len(values) - 1 else ("start", x0) if i == 0 else ("middle", cx)
                g.append(f'<text x="{lx:.1f}" y="{top_ - 4:.1f}" text-anchor="{anchor}" font-size="8" fill="{INK}">{esc(fmt_value(v, f))}</text>')
        if i % 3 == 0 or i == len(labels) - 1:
            g.append(f'<text x="{cx:.1f}" y="{base + 14}" text-anchor="middle" font-size="9" fill="{MUTED}">{esc(lab)}</text>')
        if st == "Incomplete":
            g.append(f'<text x="{cx:.1f}" y="{base + 26}" text-anchor="middle" font-size="8" fill="{BAD}">to date</text>')
    if target is not None:
        ty = y(target)
        g.append(f'<line x1="{left}" x2="{right}" y1="{ty:.1f}" y2="{ty:.1f}" stroke="{INK}" stroke-width="1.2" stroke-dasharray="4 3"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" '
            f'style="font-family:Roboto,Arial,sans-serif" role="img">{"".join(g)}</svg>')


def area_svg(labels, values, status, f, width=700, height=240):
    """Time series as an area (Google Sheets style fade), labelled y-axis with light gridlines, latest / highest /
    lowest labelled, incomplete or provisional months dashed. Mirrors renderArea() on the website."""
    import math
    idx = [i for i, v in enumerate(values) if v is not None]
    vals = [values[i] for i in idx]
    lo_, hi_ = min(vals + [0]), max(vals + [0])
    span = hi_ - lo_ or abs(hi_) or 1
    step0 = span / 4
    mag = 10 ** math.floor(math.log10(step0))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= step0)
    t0, t1 = math.floor(lo_ / step) * step, math.ceil(hi_ / step) * step
    ticks = [t0 + k * step for k in range(int(round((t1 - t0) / step)) + 1)]
    left, right, top, base = 64, width - 16, 18, height - 34
    n = len(values)
    x = lambda i: left + i * (right - left) / max(1, n - 1)
    y = lambda v: base - (v - t0) / (t1 - t0 or 1) * (base - top)
    done = lambda i: status[i] not in ("Incomplete", "Provisional")
    g = ['<defs><linearGradient id="fade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0E9F6E" stop-opacity="0.30"/>'
         '<stop offset="1" stop-color="#0E9F6E" stop-opacity="0.03"/></linearGradient></defs>']
    for t in ticks:
        g.append(f'<line x1="{left}" x2="{right}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="#e3ebe4"/>'
                 f'<text x="{left - 6}" y="{y(t) + 3:.1f}" text-anchor="end" font-size="9" fill="{MUTED}">{esc(fmt_value(t, f))}</text>')
    zero = y(max(t0, min(0, t1)))
    firm = [i for i in idx if done(i)]
    def pth(ii):   # straight segments between months (no rounding)
        return " ".join(f"{'M' if k == 0 else 'L'}{x(i):.1f},{y(values[i]):.1f}" for k, i in enumerate(ii))
    if firm:
        g.append(f'<path d="{pth(firm)} L{x(firm[-1]):.1f},{zero:.1f} L{x(firm[0]):.1f},{zero:.1f} Z" fill="url(#fade)"/>')
        g.append(f'<path d="{pth(firm)}" fill="none" stroke="{GOOD}" stroke-width="2"/>')
    tail = [i for i in idx if firm and i >= firm[-1]]
    if len(tail) > 1:
        g.append(f'<path d="{pth(tail)}" fill="none" stroke="{GOOD}" stroke-width="2" stroke-dasharray="4 3" stroke-opacity="0.6"/>')
    hi_i, lo_i = max(idx, key=lambda i: values[i]), min(idx, key=lambda i: values[i])
    keep = {hi_i, lo_i}          # the y-axis carries the rest: mark only the highest and lowest
    for i in idx:
        faint = "" if done(i) else ' stroke-opacity="0.5"'
        g.append(f'<circle cx="{x(i):.1f}" cy="{y(values[i]):.1f}" r="2.4" fill="#fff" stroke="{GOOD}" stroke-width="1.3"{faint}/>')
        if i in keep:
            anchor = "end" if i == n - 1 else "start" if i == 0 else "middle"
            ty = y(values[i]) + 15 if (i == lo_i and i != hi_i) else y(values[i]) - 8
            g.append(f'<circle cx="{x(i):.1f}" cy="{y(values[i]):.1f}" r="4.2" fill="{GOOD}" stroke="#fff" stroke-width="1.4"/>'
                     f'<text x="{x(i):.1f}" y="{ty:.1f}" text-anchor="{anchor}" font-size="9" fill="{NEG if values[i] < 0 else INK}">{esc(fmt_value(values[i], f))}</text>')
    for i in range(n):
        if i % 3 == 0 or i == n - 1:
            anchor = "start" if i == 0 else "end" if i == n - 1 else "middle"
            g.append(f'<text x="{x(i):.1f}" y="{base + 14}" text-anchor="{anchor}" font-size="9" fill="{MUTED}">{esc(labels[i])}</text>')
        if status[i] == "Incomplete":
            g.append(f'<text x="{x(i):.1f}" y="{base + 25}" text-anchor="end" font-size="8" fill="{BAD}">to date</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" '
            f'style="font-family:Roboto,Arial,sans-serif" role="img">{"".join(g)}</svg>')


def status_box_html(items):
    """items: [(label, status, note)] -> a small 'how final is this data' panel."""
    rows = "".join(f'<tr><td><b>{esc(lab)}</b></td><td><span class="st" style="color:{STATUS_COLOUR.get(st, MUTED)};border-color:{STATUS_COLOUR.get(st, MUTED)}">{esc(st)}</span></td><td>{esc(note)}</td></tr>'
                   for lab, st, note in items)
    return f'<div class="statusbox"><h3>How final is this data?</h3><table>{rows}</table></div>'


STATUS_CSS = """
.statusbox { border: 1px solid #dce8dc; border-radius: 6px; padding: 6px 10px; margin: 8px 0; page-break-inside: avoid; }
.statusbox h3 { margin: 0 0 4px; font-size: 9.5pt; color: #25342a; }
.statusbox table { width: 100%; border-collapse: collapse; } .statusbox td { padding: 2px 6px 2px 0; border: 0; font-size: 8.5pt; vertical-align: top; }
.statusbox td:first-child { white-space: nowrap; width: 1%; } .statusbox td:nth-child(2) { width: 1%; }
.st { display: inline-block; padding: 0 6px; border: 1px solid; border-radius: 999px; font-size: 7.5pt; font-weight: 700; white-space: nowrap; }
"""


# Chrome draws PDF headers and footers separately and only with fonts installed on the computer (web fonts don't load
# there), so setup_machine.py installs Roboto for the user; Arial is the fallback.
HEADER_FONT = "Roboto,Arial,sans-serif"


def _band(left, right):
    return (f'<div style="width:100%;font-family:{HEADER_FONT};font-size:7.5px;color:#5f6f63;padding:0 12mm;display:flex;justify-content:space-between;gap:8px">'
            f'<span>{left}</span><span>{right}</span></div>')


def pdf_options(business, report_name, filename, retrieved, landscape=False):
    """Every PDF page: header = business and report name; footer = file name, date retrieved, page X of Y."""
    footer = (f'<div style="width:100%;font-family:{HEADER_FONT};font-size:7.5px;color:#5f6f63;padding:0 12mm;display:flex;justify-content:space-between;gap:8px">'
              f'<span>{esc(filename)}</span><span>Data retrieved {esc(retrieved)} · {esc(generated_text())}</span>'
              f'<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>')
    return dict(format="A4", landscape=landscape, print_background=True, display_header_footer=True,
                header_template=_band(esc(business), esc(report_name)), footer_template=footer,
                margin={"top": "16mm", "bottom": "16mm", "left": "12mm", "right": "12mm"})


# Excel number formats: ONE per kind, negatives in red brackets
XL_FMT = {"pts": '+0.0" pts";(0.0" pts");"-"', "chg_money": '+#,##0;(#,##0);"-"', "chg_pct": '+0.0%;(0.0%);"-"',
          "chg_cents": '+0"¢";(0"¢");"-"', "chg_months": '+0.0" months";(0.0" months");"-"',
          "money": '#,##0;[Red](#,##0);"-"', "pct": '0.0%;[Red](0.0%);"-"', "hours": '#,##0.0;[Red](#,##0.0);"-"',
          "int": '#,##0;[Red](#,##0);"-"', "months": '0.0" months";[Red](0.0" months")', "cents": '0"¢";[Red](0"¢")',
          "date": 'd mmm yyyy', "text": '@'}


# ---- print layout: landscape A4, fitted to width. Page breaks are worked out and CHECKED here,
# before the file is saved, so nobody has to fix them at the printer.
PAGE_W_PT = (11.69 - 1.0) * 72          # A4 landscape less 0.5" side margins
PAGE_H_PT = (8.27 - 1.5) * 72           # less 0.75" top and bottom margins (header and footer sit in them)
DEFAULT_ROW_PT = 15.0


def _col_width_pt(ws, c):
    from openpyxl.utils import get_column_letter
    w = ws.column_dimensions[get_column_letter(c)].width or 8.43
    return w * 7 * 0.75 + 4                # Excel width units -> points (approx.)


def xl_scale(ws):
    """Fit-to-width shrink factor for this sheet (1.0 = actual size)."""
    width = sum(_col_width_pt(ws, c) for c in range(1, ws.max_column + 1))
    return min(1.0, PAGE_W_PT / width) if width else 1.0


def row_height(ws, r):
    """Explicit height, or an estimate from wrapped text and font size."""
    import math
    if ws.row_dimensions[r].height:
        return ws.row_dimensions[r].height
    lines, size = 1, 11
    for cell in ws[r]:
        if cell.value is None:
            continue
        if cell.font and cell.font.sz:
            size = max(size, cell.font.sz)
        if cell.alignment and cell.alignment.wrap_text and isinstance(cell.value, str) and not str(cell.value).startswith("="):
            chars = max(1, (ws.column_dimensions[cell.column_letter].width or 8.43) * 1.1)
            lines = max(lines, math.ceil(len(cell.value) / chars))
    return max(DEFAULT_ROW_PT, lines * size * 1.36)


def xl_breaks(ws, block_starts, last_row, header_row=None):
    """Place page breaks only at block boundaries (a block = a statement section, a workings panel,
    a month of a list); split a block only if it is longer than a whole page. Returns the page plan."""
    from openpyxl.worksheet.pagebreak import Break, RowBreak
    ws.row_breaks = RowBreak()
    scale = xl_scale(ws)
    cap = PAGE_H_PT / scale
    rep = row_height(ws, header_row) if header_row else 0
    starts = sorted(set(b for b in block_starts if 1 < b <= last_row))
    pages, top, used = [], 1, 0.0
    block_of = {}
    cur = 1
    for r in range(1, last_row + 1):
        if r in starts:
            cur = r
        block_of[r] = cur
    r = 1
    while r <= last_row:
        h = row_height(ws, r)
        if used + h > cap:
            # break before the start of this row's block, if that keeps the block whole and the page isn't empty
            b = block_of[r]
            brk = b if (b > top and b in starts) else r
            ws.row_breaks.append(Break(id=brk - 1))
            pages.append((top, brk - 1))
            top = brk
            used = rep + sum(row_height(ws, x) for x in range(brk, r))
            if header_row and top <= header_row:
                used -= rep
        used += h
        r += 1
    pages.append((top, last_row))
    return {"scale": scale, "capacity": cap, "pages": pages, "starts": starts, "header": rep}


def xl_review(ws, plan, header_row=None):
    """Check the page plan before saving: every page fits, no block is split unless it is
    longer than a page, and the header row repeats. Returns a one-line summary; raises on a problem."""
    problems = []
    for i, (a, b) in enumerate(plan["pages"], 1):
        h = sum(row_height(ws, r) for r in range(a, b + 1)) + (plan["header"] if (header_row and a > header_row) else 0)
        if h > plan["capacity"] + 0.5:
            problems.append(f"page {i} (rows {a}-{b}) is too tall")
        if i > 1:
            inside = [s for s in plan["starts"] if a < s <= b]
            prev_block = max([s for s in plan["starts"] if s <= a] or [1])
            nxt = min([s for s in plan["starts"] if s > a] or [b + 1])
            block_len = sum(row_height(ws, r) for r in range(prev_block, nxt))
            if a not in plan["starts"] and block_len <= plan["capacity"] and prev_block != 1:
                problems.append(f"page {i} starts part-way through a block (row {a})")
    if header_row and len(plan["pages"]) > 1 and ws.print_title_rows is None:
        problems.append("header row doesn't repeat")
    if problems:
        raise SystemExit(f"Print check FAILED on sheet '{ws.title}': " + "; ".join(problems))
    n = len(plan["pages"])
    return f"{ws.title}: {n} page{'s' if n > 1 else ''}, {round(plan['scale'] * 100)}% scale, no block split"


# What made each hand-built download (Nathan: every hand-built chart or report says what tools made it)
MADE_WITH = {"xlsx": "Made with Python (openpyxl)", "pptx": "Made with Python (python-pptx)",
             "pdf": "Made with Python: laid out in HTML and CSS, printed to PDF in Chromium"}
MADE_WITH_CSS = ".madewith { margin: 10px 0 0; font-size: 7.5pt; color: #5f6f63; }"
XL_FONT = "Roboto"     # Excel and PowerPoint downloads use Roboto, like the site and the business cards


def xl_font(**kw):
    """openpyxl Font with Roboto unless a font is named."""
    from openpyxl.styles import Font
    kw.setdefault("name", XL_FONT)
    return Font(**kw)


def xl_default_font(wb, size=11):
    """Make Roboto the workbook's default font (every cell without its own font, and new cells)."""
    from openpyxl.styles import Font
    for st in wb._named_styles:
        if st.name == "Normal":
            st.font = Font(name=XL_FONT, size=size)
    wb._fonts[0] = Font(name=XL_FONT, size=size)
    return wb


def xl_print(ws, business, filename, retrieved, landscape=True, header_row=None, gridlines=False):
    """Make a worksheet print like a report. Header: business and sheet name.
    Footer: file name, date retrieved (fixed text) and page X of Y."""
    from openpyxl.utils import get_column_letter as _gcl
    ws.print_area = f"A1:{_gcl(max(1, ws.max_column))}{max(1, ws.max_row)}"     # the cells: charts beside a table are for the screen
    amp = lambda t: t.replace("&", "&&")          # & starts a code in Excel headers
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.5
    ws.page_margins.top, ws.page_margins.bottom = 0.75, 0.75
    if header_row:
        ws.print_title_rows = f"{header_row}:{header_row}"
    ws.sheet_view.showGridLines = gridlines
    for part, text in [(ws.oddHeader.left, amp(business)), (ws.oddHeader.right, "&A"),
                       (ws.oddFooter.left, amp(filename)), (ws.oddFooter.center, amp(f"Data retrieved {retrieved} · {generated_text()}")),
                       (ws.oddFooter.right, "Page &P of &N")]:
        part.text = text
        part.size = 8
        part.font = f"{XL_FONT},Regular"


# ---- When each download was generated. Every file says it inside ("Generated 8 Oct 2026, 2:35pm") and the site names the
# download with it. A rebuild that changes nothing keeps the old file and its stamp: the comparison leaves the stamp out,
# and media/exports/generated.json records each file's content fingerprint and when that content was generated.
from datetime import datetime as _dt

def _now_brisbane():
    """Brisbane time (AEST, no daylight saving), whatever clock the build machine is on: a PC or a cloud build set to
    UTC still stamps the files in Nathan's time. Falls back to the machine's own time if the time zone data is missing."""
    try:
        from zoneinfo import ZoneInfo
        return _dt.now(ZoneInfo("Australia/Brisbane")).replace(tzinfo=None)
    except Exception:
        return _dt.now()


GENERATED = _now_brisbane().replace(second=0, microsecond=0)
_STAMP_RE = rb"Generated \d{1,2} [A-Z][a-z]{2} \d{4}, \d{1,2}:\d{2}[ap]m"


def generated_text(when=None):
    w = when or GENERATED
    return "Generated " + f"{w.day} {w.strftime('%b %Y')}, {(w.hour % 12) or 12}:{w.strftime('%M')}{'am' if w.hour < 12 else 'pm'}"


def _manifest_path():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent.parent / "media" / "exports" / "generated.json"


def _manifest():
    import json
    if not hasattr(_manifest, "data"):
        p = _manifest_path()
        _manifest.data = json.loads(p.read_text()) if p.exists() else {}
    return _manifest.data


def _rel(dest):
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent.parent
    try:
        return str(Path(dest).resolve().relative_to(repo))
    except ValueError:
        return None              # outside the repo (e.g. a test render): not recorded


def _unchanged(dest, key):
    """True if dest exists and its recorded content fingerprint matches (so the file and its stamp are kept)."""
    from pathlib import Path
    rel = _rel(dest)
    m = _manifest().get(rel) if rel else None
    return bool(m and m.get("key") == key and Path(dest).exists())


def _record(dest, key):
    import json
    rel = _rel(dest)
    if not rel:
        return
    _manifest()[rel] = {"key": key, "generated": GENERATED.isoformat(timespec="minutes")}
    p = _manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(sorted(_manifest().items())), indent=1) + "\n")


def generated_of(path):
    """When the file's content was generated (from the record; the file's own stamp says the same)."""
    m = _manifest().get(_rel(path) or "")
    return _dt.fromisoformat(m["generated"]) if m else None


def _key(blobs):
    import hashlib
    import re
    h = hashlib.sha256()
    for name, data in sorted(blobs.items()):
        h.update(name.encode())
        h.update(re.sub(_STAMP_RE, b"Generated <stamp>", data))
    return h.hexdigest()


def download_name(business, title, period, fmt, when):
    """e.g. 'Sample Electrical & Air Pty Ltd - Job margins - September 2026 - generated 2026-10-08 1435.xlsx'."""
    import re
    clean = lambda t: re.sub(r'[\\/:*?"<>|]', "", str(t)).strip()
    stamp = when.strftime("%Y-%m-%d %H%M") if when else "undated"
    return f"{clean(business)} - {clean(title)} - {clean(period)} - generated {stamp}.{fmt}"


def period_name(month, incomplete):
    """The period in a file name: a closed month in full ('September 2026'), the month in progress by name ('October')."""
    from datetime import date
    d = date.fromisoformat(month + "-01")
    return d.strftime("%B") if incomplete else d.strftime("%B %Y")


def export_meta(paths, business=None, title=None, period=None):
    """What the Export menu says about each download: PDF page count and PowerPoint slide count, read from the files
    the build just wrote (so nothing is typed in). paths: {"pdf": "media/...", "pptx": "media/..."} relative to the repo."""
    import re
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent.parent
    meta = {}
    pdf = repo / paths.get("pdf", "") if paths.get("pdf") else None
    if pdf and pdf.is_file():
        meta["pdf_pages"] = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", pdf.read_bytes()))
    pptx = repo / paths.get("pptx", "") if paths.get("pptx") else None
    if pptx and pptx.is_file():
        from pptx import Presentation
        meta["pptx_slides"] = len(Presentation(str(pptx)).slides)
    if business and title and period:      # the name each download is saved under: business, report, period, when generated
        meta["names"] = {fmt: download_name(business, title, period, fmt, generated_of(repo / pth)) for fmt, pth in paths.items() if pth}
    return meta


def same_office_file(a, b):
    """True if two .xlsx/.pptx files differ only in their saved-at timestamps (docProps/core.xml), including
    the small workbooks embedded behind PowerPoint charts."""
    import io
    import zipfile
    from pathlib import Path

    def parts(z):
        out = {}
        for n in z.namelist():
            if n.endswith("docProps/core.xml"):
                continue
            data = z.read(n)
            if n.endswith(".xlsx"):
                with zipfile.ZipFile(io.BytesIO(data)) as inner:
                    for k, v in parts(inner).items():
                        out[f"{n}/{k}"] = v
            else:
                out[n] = data
        return out
    if not (Path(a).exists() and Path(b).exists()):
        return False
    try:
        with zipfile.ZipFile(a) as za, zipfile.ZipFile(b) as zb:
            return parts(za) == parts(zb)
    except zipfile.BadZipFile:
        return False


def _office_parts(path):
    import io
    import zipfile

    def parts(z):
        out = {}
        for n in z.namelist():
            if n.endswith("docProps/core.xml"):
                continue
            data = z.read(n)
            if n.endswith(".xlsx"):
                with zipfile.ZipFile(io.BytesIO(data)) as inner:
                    for k, v in parts(inner).items():
                        out[f"{n}/{k}"] = v
            else:
                out[n] = data
        return out
    with zipfile.ZipFile(path) as z:
        return parts(z)


def save_if_changed(save, dest):
    """Save via save(path) to a temporary file, and only replace dest if the content changed (keeps git quiet, and keeps
    the file's 'Generated' stamp when nothing in it changed)."""
    import shutil
    import tempfile
    from pathlib import Path
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t) / dest.name
        save(str(tmp))
        # pictures (e.g. map screenshots, which differ by a pixel run to run) are left out: real changes show in the numbers
        key = _key({n: v for n, v in _office_parts(tmp).items() if "/media/" not in "/" + n})
        if not _unchanged(dest, key):
            shutil.copy(tmp, dest)
            _record(dest, key)


def same_pdf(a, b):
    """True if two PDFs differ only in their creation/modification dates."""
    import re
    from pathlib import Path
    if not (Path(a).exists() and Path(b).exists()):
        return False
    norm = lambda p: re.sub(rb"/(CreationDate|ModDate) \(D:[^)]*\)", b"", Path(p).read_bytes())
    return norm(a) == norm(b)


def pdf_if_changed(page, dest, **options):
    """Print the page to dest only if its content changed: the page's HTML and the print settings are fingerprinted
    (stamp left out) and compared with the record, so an unchanged PDF isn't even printed, and keeps its stamp."""
    import json
    from pathlib import Path
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    key = _key({"html": page.content().encode("utf-8"), "options": json.dumps(options, sort_keys=True, default=str).encode("utf-8")})
    if not _unchanged(dest, key):
        page.pdf(path=str(dest), **options)
        _record(dest, key)


# ---- Excel finishing: one font on every cell, tables, named headline numbers, native charts, changes by direction

XL_GREEN, XL_GREY, XL_RED, XL_INK = "0E9F6E", "7D8790", "B42318", "25342A"


def xl_finish(wb):
    """Roboto set explicitly on every cell that has a value (headings included), keeping each cell's own size, weight
    and colour: without a name, a font falls back to the app's default (serif in LibreOffice)."""
    import copy as _copy
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None and c.font.name != XL_FONT:
                    f = _copy.copy(c.font)
                    f.name = XL_FONT
                    c.font = f
    return wb


def xl_table(ws, name, first_row, last_row, ncols, first_col=1):
    """An Excel Table over a header row and its data (sortable, filterable, refers by column name). Header cells
    must be unique text. Replaces a plain auto-filter on the same range."""
    import re as _re
    from openpyxl.utils import get_column_letter as _gcl
    from openpyxl.worksheet.table import Table, TableStyleInfo
    if last_row <= first_row:
        return None
    seen = {}
    for c in range(first_col, first_col + ncols):
        cell = ws.cell(first_row, c)
        h = str(cell.value or f"Column {c}").strip() or f"Column {c}"
        seen[h] = seen.get(h, 0) + 1
        cell.value = h if seen[h] == 1 else f"{h} ({seen[h]})"
    ws.auto_filter.ref = None
    nm = _re.sub(r"\W", "_", name)
    nm = ("T_" + nm) if not nm[:1].isalpha() else nm
    existing = {t for w in ws.parent.worksheets for t in w.tables}
    base, k = nm[:240], 2
    while nm in existing:
        nm = f"{base}_{k}"; k += 1
    t = Table(displayName=nm, ref=f"{_gcl(first_col)}{first_row}:{_gcl(first_col + ncols - 1)}{last_row}")
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    ws.add_table(t)
    return t


def xl_name(wb, label, sheet, cell_ref, used=None):
    """A workbook-level name for a headline number, e.g. Job_gross_margin_September -> 'Report'!$B$8."""
    import re as _re
    from openpyxl.workbook.defined_name import DefinedName
    nm = _re.sub(r"_+", "_", _re.sub(r"[^A-Za-z0-9_]", "_", label)).strip("_")[:60] or "Headline"
    if not nm[:1].isalpha():
        nm = "N_" + nm
    used = used if used is not None else set()
    base, k = nm, 2
    while nm in used or nm in wb.defined_names:
        nm = f"{base}_{k}"; k += 1
    used.add(nm)
    col, row = _re.match(r"([A-Z]+)(\d+)", cell_ref).groups()
    wb.defined_names[nm] = DefinedName(nm, attr_text=f"'{sheet}'!${col}${row}")
    return nm


def _xl_style_chart(ch, title):
    from openpyxl.chart.text import RichText, Text
    from openpyxl.chart.title import Title
    from openpyxl.drawing.text import CharacterProperties, Font as DFont, Paragraph, ParagraphProperties, RegularTextRun
    tp = CharacterProperties(latin=DFont(typeface=XL_FONT), sz=1100, b=True, solidFill=XL_INK)
    ch.title = Title(tx=Text(rich=RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=tp), r=[RegularTextRun(rPr=tp, t=title)])])), overlay=False)
    ch.legend = None
    ch.style = 2
    cp = CharacterProperties(latin=DFont(typeface=XL_FONT), sz=900, solidFill=XL_INK)
    ch.txPr = RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=cp), endParaRPr=cp)])
    return ch


def _xl_line_cells(wb, name, x):
    """Two points for a vertical line at x (x, 0) and (x, 1), on a hidden 'Chart lines' sheet. Returns (ws, first row)."""
    ws = wb["Chart lines"] if "Chart lines" in wb.sheetnames else wb.create_sheet("Chart lines")
    if ws.max_row == 1 and ws["A1"].value is None:
        ws["A1"] = "Points for the target and break-even lines drawn on the charts (hidden sheet; edit the values on the chart's own sheet)."
        ws.sheet_state = "hidden"
    r = ws.max_row + 2
    ws.cell(r, 1, name)
    for k, y in enumerate((0, 1)):
        ws.cell(r + 1 + k, 2, x)
        ws.cell(r + 1 + k, 3, y)
    return ws, r + 1


def xl_bar_chart(ws, anchor, title, cats_ref, vals_ref, n, number_format="General", series_name=None, target=None, fmt_target=None, below=None, bad=None,
                 values=None, lines=None, warn=None):
    """A native horizontal bar chart (brand green), one bar per category, values labelled; no gridline clutter.
    lines = [(label, x, colour, dash)] in the cells' own units (e.g. 0.35 for 35%): each is drawn as a vertical line
    across the bars, the standard Excel combo: an XY scatter series from (x, 0) to (x, 1) on hidden secondary axes,
    scaled exactly like the bars' value axis so the line sits at its value. values (the bars' numbers, cell units)
    fix that scale."""
    from openpyxl.chart import BarChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.chart.series import SeriesLabel
    ch = BarChart()
    ch.type = "bar"
    ch.varyColors = False
    ws_, c1, r1, c2, r2 = vals_ref
    data = Reference(ws_, min_col=c1, min_row=r1, max_col=c2, max_row=r2)
    ch.add_data(data, titles_from_data=False)
    wc, cc1, cr1, cc2, cr2 = cats_ref
    ch.set_categories(Reference(wc, min_col=cc1, min_row=cr1, max_col=cc2, max_row=cr2))
    s_ = ch.series[0]
    s_.tx = SeriesLabel(v=series_name or title)
    s_.graphicalProperties.solidFill = XL_GREEN
    s_.graphicalProperties.line.solidFill = XL_GREEN
    s_.invertIfNegative = False
    from openpyxl.chart.marker import DataPoint
    for i in range(n):               # grey below target, red losing money / off budget: the same colours as the website
        colour = XL_RED if (bad and bad[i]) else "8A6D3B" if (warn and warn[i]) else XL_GREY if (below and below[i]) else None
        if colour:
            pt = DataPoint(idx=i)
            pt.graphicalProperties.solidFill = colour
            pt.graphicalProperties.line.solidFill = colour
            s_.dPt.append(pt)
    s_.dLbls = DataLabelList()
    s_.dLbls.showVal = True
    s_.dLbls.numFmt = number_format
    for k in ("showSerName", "showCatName", "showLegendKey", "showPercent"):
        setattr(s_.dLbls, k, False)
    ch.y_axis.numFmt = number_format
    ch.y_axis.majorGridlines = None
    ch.y_axis.delete = True
    ch.x_axis.scaling.orientation = "maxMin"        # first row at the top, like the table
    ch.gapWidth = 60
    lines = [ln for ln in (lines or []) if ln[1] is not None]
    if lines and values:
        from openpyxl.chart import ScatterChart, Series
        from openpyxl.chart.axis import NumericAxis
        lo = min(0, *values) * 1.15
        hi = max(0, *values, *(ln[1] for ln in lines)) * 1.15 or 1
        ch.y_axis.scaling.min, ch.y_axis.scaling.max = lo, hi
        sc = ScatterChart()
        sc.style = 2
        for k_line, (label, x, colour, dash) in enumerate(lines):
            hw, r0 = _xl_line_cells(ws.parent, f"{ws.title}: {title}: {label}", x)
            se = Series(Reference(hw, min_col=3, min_row=r0, max_row=r0 + 1), Reference(hw, min_col=2, min_row=r0, max_row=r0 + 1), title=label)
            se.marker.symbol = "none"
            se.smooth = False
            se.graphicalProperties.line.solidFill = colour
            se.graphicalProperties.line.width = 19050          # 1.5 pt
            se.graphicalProperties.line.dashStyle = dash
            # the line's name at its top end, in its own colour (no key needed)
            from openpyxl.chart.label import DataLabel, DataLabelList
            from openpyxl.chart.text import RichText
            from openpyxl.drawing.text import CharacterProperties, Font as DFont, Paragraph, ParagraphProperties
            cp = CharacterProperties(latin=DFont(typeface=XL_FONT), sz=900, b=True, solidFill=colour)
            top = DataLabel(idx=1, showSerName=True, showVal=False, showCatName=False, showLegendKey=False, showPercent=False,
                            dLblPos="r" if k_line == 0 else "l")      # first line's name to its right, the next to its left: never on top of each other
            top.txPr = RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=cp), endParaRPr=cp)])
            se.dLbls = DataLabelList(dLbl=[top], showVal=False, showSerName=False, showCatName=False, showLegendKey=False, showPercent=False)
            sc.series.append(se)
        # secondary axes, hidden: horizontal scaled like the bars, vertical 0 to 1 (the full height of the plot)
        sc.x_axis = NumericAxis(axId=500, crossAx=600)
        sc.x_axis.scaling.min, sc.x_axis.scaling.max = lo, hi
        sc.x_axis.delete = True
        sc.x_axis.majorGridlines = None
        sc.x_axis.axPos = "t"
        sc.y_axis = NumericAxis(axId=600, crossAx=500)
        sc.y_axis.scaling.min, sc.y_axis.scaling.max = 0, 1
        sc.y_axis.delete = True
        sc.y_axis.majorGridlines = None
        sc.y_axis.scaling.max = 1.08          # room above the bars for the lines' labels
        sc.y_axis.axPos = "r"
        sc.y_axis.crosses = "max"
        ch += sc
    _xl_style_chart(ch, title)
    ch.x_axis.majorGridlines = None
    ch.width, ch.height = 15, max(5.5, 0.75 * n + 2) + (0.6 if lines else 0)
    ws.add_chart(ch, anchor)
    return ch


def xl_line_chart(ws, anchor, title, cats_ref, series, number_format="General"):
    """A native line chart: series = [(name, (ws, col, first_row, last_row))], categories along the bottom."""
    from openpyxl.chart import LineChart, Reference
    from openpyxl.chart.series import SeriesLabel
    ch = LineChart()
    palette = [XL_GREEN, "2F7A5D", "8A6D3B", "5F6F63", "8E9CAB", "1F5A43", "B42318"]
    for k, (nm, (w, col, r1, r2)) in enumerate(series):
        ch.add_data(Reference(w, min_col=col, min_row=r1, max_row=r2), titles_from_data=False)
        s_ = ch.series[-1]
        s_.tx = SeriesLabel(v=nm)
        s_.graphicalProperties.line.solidFill = palette[k % len(palette)]
        s_.graphicalProperties.line.width = 22000
        s_.smooth = False
        s_.marker.symbol = "none"
    wc, c, r1, r2 = cats_ref
    ch.set_categories(Reference(wc, min_col=c, min_row=r1, max_row=r2))
    ch.y_axis.numFmt = number_format
    ch.y_axis.majorGridlines.spPr = None
    ch.x_axis.number_format = "@"
    ch.x_axis.tickLblSkip = max(1, (r2 - r1 + 1) // 12)
    _xl_style_chart(ch, title)
    if len(series) > 1:
        from openpyxl.chart.legend import Legend
        ch.legend = Legend()
        ch.legend.position = "b"
    ch.width, ch.height = 18, 8
    ws.add_chart(ch, anchor)
    return ch


def xl_change(ws, cell, good_when="higher"):
    """Colour a change cell by meaning, not sign: green when it moved the good way, red when it moved the bad way."""
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Font as XFont
    good, bad = XFont(name=XL_FONT, color="2F7A5D", bold=True), XFont(name=XL_FONT, color=XL_RED, bold=True)
    up, down = (good, bad) if good_when == "higher" else (bad, good)
    ws.conditional_formatting.add(cell, CellIsRule(operator="greaterThan", formula=["0"], font=up))
    ws.conditional_formatting.add(cell, CellIsRule(operator="lessThan", formula=["0"], font=down))


def bar_spec(ch, vw, views):
    """One view of a chart, ready for hbar_svg. A $ view with a per-bar target mark (e.g. 35% of each job's revenue)
    shows how far each bar is short of it, in dollars, instead of a tick per bar (unreadable when bars differ a lot)."""
    spec = {**ch, **{k: vw.get(k) for k in ("values", "format", "target", "breakeven", "marks", "mark_label", "below_marks")},
            "order_by": views[0]["values"], "variance_pct": views[0]["values"]}
    if vw.get("marks") and vw.get("below_marks"):
        t0 = views[0].get("target", ch.get("target"))
        spec["notes"] = [f"{fmt_value(m - v, 'money0')} short of {t0:.1f}%" if v < m else "" for v, m in zip(vw["values"], vw["marks"])]
        spec["below_flags"] = [v < m for v, m in zip(vw["values"], vw["marks"])]
        spec["marks"], spec["below_marks"] = None, None
    return spec
