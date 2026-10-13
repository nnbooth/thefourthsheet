"""
operations_reports.py — the questions that aren't about money: worked examples built from tools/operations.py's data.

  callbacks       SME trades    How long do customers wait for a callback?
  overtime        SME trades    Where is overtime creeping up, and why?
  people-helped   NFP           How many people did you help this month, and how many couldn't you reach?
  calls           NFP           When do calls for help come in, and are you there to answer?
  volunteers      NFP           How many volunteer hours go into each program?

Same shape as every other report (catalogue.py): headline numbers with workings, a month-by-month chart, a breakdown,
what it shows and what you'd do about it (flags, not instructions), and the data for the Excel download.
Each report is one organisation only.
"""

from collections import defaultdict
from statistics import median

import data_status as ds
import exportkit as ek
from financial_model import FMT, calc, half_up, inp, money, support, round_half_up

from .catalogue import kpi, kpis, report, series, table, text
from .period import mdate, mlabel

pct = FMT["pct"]
TARGET_CB = 0.80          # share of enquiries called back within 2 working hours
TARGET_OT = 0.05          # overtime as a share of ordinary hours
TARGET_REACH = 0.90       # share of people who came to a program and were helped
TARGET_ANSWER = 0.90      # share of calls answered while the line is staffed


def month_of(dk):
    s = str(int(dk))
    return f"{s[:4]}-{s[4:6]}"


def flags_or(items, fallback):
    return " ".join(x for x in items if x) or fallback


# ======================================================================= SME trades

def callbacks(D, P):
    rows = D["_src"].table("trades", "fact_enquiry")
    by = defaultdict(list)
    for r in rows:
        by[month_of(r["date_key"])].append(r)
    W = P.window

    def stats(m):
        e = by.get(m, [])
        done = [r for r in e if r["minutes_to_callback"] is not None]
        within = sum(1 for r in done if r["within_target"] == 1)
        return {"n": len(e), "done": len(done), "within": within, "open": len(e) - len(done),
                "median": half_up(median([r["minutes_to_callback"] for r in done])) if done else None}   # rounded once, half up: tile, headline and workings agree

    S = {m: stats(m) for m in W}

    def sp(m):
        s = S[m]
        return support(f"Callbacks, {mlabel(m)}", "Enquiries called back within 2 working hours ÷ enquiries called back", [
            inp("Enquiries", "int", [s["n"]]), inp("Called back", "int", [s["done"]]), inp("Called back within 2 working hours", "int", [s["within"]]),
            calc("Share within 2 working hours", "pct", "r2/r1"), inp("Median wait (working minutes)", "int", [s["median"] or 0])],
            "Working minutes only: 8:30am to 5pm on working days. The median is the middle wait when every callback is lined up.", cols=(mlabel(m),))
    sups = [sp(m) for m in W]
    c, p = S[P.mo], S[P.prev]
    share = c["within"] / c["done"] if c["done"] else 0
    pshare = p["within"] / p["done"] if p["done"] else 0
    k_share = support(f"Callbacks within 2 working hours, {P.month} and {P.prev_month}", "Within 2 working hours ÷ called back", [
        inp("Called back", "int", [c["done"], p["done"]]), inp("Within 2 working hours", "int", [c["within"], p["within"]]), calc("Share", "pct", "r1/r0")],
        P.part_note or None, cols=(mlabel(P.mo), mlabel(P.prev)))
    k_med = support(f"Median wait for a callback, {P.month} and {P.prev_month}", "The middle wait, in working minutes", [
        inp("Median wait (working minutes)", "int", [c["median"] or 0, p["median"] or 0]), inp("Enquiries called back", "int", [c["done"], p["done"]])],
        "Working minutes: 8:30am to 5pm on working days.", cols=(mlabel(P.mo), mlabel(P.prev)))
    items = [kpi(f"Called back within 2 working hours, {P.when}", pct(share), f"target {pct(TARGET_CB)} · {P.prev_month} {pct(pshare)}", k_share,
                 tone=ek.tone(share, "higher", TARGET_CB, 0.05)),
             kpi(f"Median wait, {P.when}", f"{half_up(c['median'] or 0)} min", f"{P.prev_month} {half_up(p['median'] or 0)} min (working minutes)", k_med),
             kpi(f"Enquiries, {P.when}", f"{c['n']:,}", f"{P.prev_month} {p['n']:,}", sp(P.mo))]
    if P.incomplete and c["open"]:
        items.append(kpi("Still waiting for a callback", f"{c['open']}", f"at {ds.as_at_text()}", sp(P.mo), tone="warn"))
    # by channel, this month
    ch = defaultdict(lambda: [0, 0])
    for r in by.get(P.mo, []):
        if r["minutes_to_callback"] is not None:
            ch[r["channel"]][0] += 1
            ch[r["channel"]][1] += r["within_target"] or 0
    labs = sorted(ch, key=lambda k: -ch[k][0])
    det = [support(f"{k}: callbacks, {P.label}", "Within 2 working hours ÷ called back", [inp("Called back", "int", [ch[k][0]]), inp("Within 2 working hours", "int", [ch[k][1]]),
                                                                                         calc("Share", "pct", "r1/r0")], cols=(P.short,)) for k in labs]
    worst = min(labs, key=lambda k: ch[k][1] / ch[k][0]) if labs else None
    shows = (f"{pct(share)} of the {c['done']} enquiries called back in {P.when} heard back within 2 working hours (target {pct(TARGET_CB)}), "
             f"{'up' if share >= pshare else 'down'} from {pct(pshare)} in {P.prev_month}. The median wait was {half_up(c['median'] or 0)} working minutes.")
    gap = round_half_up(TARGET_CB * c["done"] - c["within"])
    action = flags_or([
        f"{gap} more enquiries would have needed a faster callback to reach the {pct(TARGET_CB)} target." if gap > 0 else None,
        f"{worst} enquiries are the slowest: {pct(ch[worst][1] / ch[worst][0])} within 2 working hours." if worst else None,
        f"{c['open']} enquiries are still waiting at {ds.as_at_text()}." if P.incomplete and c["open"] else None],
        f"Callbacks are on target: {pct(share)} within 2 working hours.")
    answer = f"{pct(share)} called back within 2 working hours in {P.when} (target {pct(TARGET_CB)}); median wait {half_up(c['median'] or 0)} working minutes."
    return report("callbacks", "sme", "How long do customers wait for a callback?", "trades", D, P,
                  "Every customer enquiry (phone, web form, email) and how long until someone first called back, in working minutes. Every call-out job has the enquiry that booked it.",
                  [{"label": None, "sections": [
                      kpis(items),
                      series(P, "Callbacks by month", {
                          "All|share": {"label": "Within 2 working hours %", "values": [round_half_up(100 * S[m]["within"] / S[m]["done"], 1) if S[m]["done"] else None for m in W], "format": "pct1", "supports": sups},
                          "All|median": {"label": "Median wait (min)", "values": [half_up(S[m]["median"]) if S[m]["median"] is not None else None for m in W], "format": "int", "supports": sups},
                          "All|n": {"label": "Enquiries", "values": [S[m]["n"] for m in W], "format": "int", "supports": sups}},
                          note="Working minutes only (8:30am to 5pm, working days). Tap a month for its workings.",
                          dims={"line": ["All"], "measure": [("share", "Within 2 working hours %"), ("median", "Median wait (min)"), ("n", "Enquiries")]}),
                      {"type": "bars", "chart": {"title": f"Called back within 2 working hours, by channel, {P.label}", "subtitle": f"Target {pct(TARGET_CB)}.",
                                                 "labels": labs, "values": [round_half_up(100 * ch[k][1] / ch[k][0], 1) for k in labs], "format": "pct1",
                                                 "target": round_half_up(100 * TARGET_CB, 1), "details": det}},
                      text(shows, action)]}],
                  {"head": ["Month", "Status", "Enquiries", "Called back", "Within 2 working hours", "Share within target", "Median wait (min)"],
                   "kinds": ["text", "text", "int", "int", "int", "pct", "int"],
                   "rows": [[mlabel(m), P.status_of(m), S[m]["n"], S[m]["done"], S[m]["within"], "=IF(D{r}=0,\"\",E{r}/D{r})", half_up(S[m]["median"] or 0)] for m in W]}, answer)


def overtime(D, P):
    rows = D["_src"].table("trades", "fact_shift_daily")
    o_h, ord_h, why, tech = defaultdict(float), defaultdict(float), defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float))
    for r in rows:
        m = month_of(r["date_key"])
        o_h[m] += r["overtime_hours"]
        ord_h[m] += r["ordinary_hours"]
        if r["overtime_hours"]:
            why[m][r["overtime_reason"]] += r["overtime_hours"]
            tech[m][r["technician"]] += r["overtime_hours"]
    W = P.window
    rate = {m: (o_h[m] / ord_h[m] if ord_h[m] else 0) for m in W}

    def sp(m):
        return support(f"Overtime, {mlabel(m)}", "Overtime hours ÷ ordinary hours", [inp("Overtime hours", "hours", [o_h[m]]), inp("Ordinary hours", "hours", [ord_h[m]]),
                                                                                  calc("Overtime as a share of ordinary hours", "pct", "r0/r1")],
                       "From each technician's shifts (fact_shift_daily).", cols=(mlabel(m),))
    sups = [sp(m) for m in W]
    k = support(f"Overtime, {P.month} and {P.prev_month}", "Overtime hours ÷ ordinary hours", [
        inp("Overtime hours", "hours", [o_h[P.mo], o_h[P.prev]]), inp("Ordinary hours", "hours", [ord_h[P.mo], ord_h[P.prev]]), calc("Share", "pct", "r0/r1")],
        P.part_note or None, cols=(mlabel(P.mo), mlabel(P.prev)))
    items = [kpi(f"Overtime, {P.when}", pct(rate[P.mo]), f"of ordinary hours · target under {pct(TARGET_OT)}", k, tone=ek.tone(rate[P.mo], "lower", TARGET_OT, 0.01)),
             kpi(f"Overtime hours, {P.when}", FMT["hours"](o_h[P.mo]), f"{P.prev_month} {FMT['hours'](o_h[P.prev])}", k)]
    if P.ly_ok:
        items.append(kpi(f"{P.month} last year", pct(rate[P.ly]), f"{FMT['hours'](o_h[P.ly])} of overtime", sp(P.ly)))
    rs = sorted(why[P.mo], key=lambda x: -why[P.mo][x])
    ts = sorted(tech[P.mo], key=lambda x: -tech[P.mo][x])
    det_r = [support(f"{x}: overtime, {P.label}", "Overtime hours with this as the main reason", [inp("Overtime hours", "hours", [why[P.mo][x]]),
                                                                                                  inp("All overtime hours", "hours", [o_h[P.mo]]), calc("Share", "pct", "r0/r1")], cols=(P.short,)) for x in rs]
    det_t = [support(f"Technician {x}: overtime, {P.label}", "Overtime hours on this technician's shifts", [inp("Overtime hours", "hours", [tech[P.mo][x]])], cols=(P.short,)) for x in ts]
    top = rs[0] if rs else None
    trend_note = (f" Over the last year it has gone from {pct(rate[P.ly])} to {pct(rate[P.mo])}." if P.ly_ok else "")
    shows = (f"Technicians worked {FMT['hours'](o_h[P.mo])} of overtime in {P.when}, {pct(rate[P.mo])} of ordinary hours "
             f"(target under {pct(TARGET_OT)}), against {pct(rate[P.prev])} in {P.prev_month}.{trend_note}")
    action = flags_or([
        f"{top} is the main reason: {FMT['hours'](why[P.mo][top])}, {pct(why[P.mo][top] / o_h[P.mo])} of the overtime." if top else None,
        f"Technician {ts[0]} carried the most ({FMT['hours'](tech[P.mo][ts[0]])})." if ts else None,
        f"Above target by {FMT['hours'](o_h[P.mo] - TARGET_OT * ord_h[P.mo])}." if rate[P.mo] > TARGET_OT else None],
        "Overtime is within target.")
    answer = f"Overtime was {pct(rate[P.mo])} of ordinary hours in {P.when} (target under {pct(TARGET_OT)})" + (f", up from {pct(rate[P.ly])} a year earlier." if P.ly_ok else ".")
    return report("overtime", "sme", "Where is overtime creeping up, and why?", "trades", D, P,
                  "Each technician's paid hours, day by day: ordinary hours and overtime, with the main reason for the overtime.",
                  [{"label": None, "sections": [
                      kpis(items),
                      series(P, "Overtime by month", {
                          "All|rate": {"label": "Overtime % of ordinary hours", "values": [round_half_up(100 * rate[m], 1) for m in W], "format": "pct1", "supports": sups},
                          "All|hours": {"label": "Overtime hours", "values": [round_half_up(o_h[m], 1) for m in W], "format": "int", "supports": sups}},
                          note="Tap a month for its workings.", dims={"line": ["All"], "measure": [("rate", "Overtime % of ordinary hours"), ("hours", "Overtime hours")]}),
                      {"type": "bars", "chart": {"title": f"Why the overtime, {P.label}", "subtitle": "Overtime hours by main reason.", "labels": rs,
                                                 "values": [round_half_up(why[P.mo][x], 1) for x in rs], "format": "int", "plain": True, "details": det_r}},
                      {"type": "bars", "chart": {"title": f"Overtime by technician, {P.label}", "subtitle": "Technicians are codes, not names.", "labels": [f"Technician {x}" for x in ts],
                                                 "values": [round_half_up(tech[P.mo][x], 1) for x in ts], "format": "int", "plain": True, "details": det_t}},
                      text(shows, action)]}],
                  {"head": ["Month", "Status", "Ordinary hours", "Overtime hours", "Overtime share"], "kinds": ["text", "text", "hours", "hours", "pct"],
                   "rows": [[mlabel(m), P.status_of(m), ord_h[m], o_h[m], "=IF(C{r}=0,\"\",D{r}/C{r})"] for m in W]}, answer)


# ======================================================================= not-for-profit

def people_helped(D, P):
    rows = D["_src"].table("nfp", "fact_service_daily")
    h, nr = defaultdict(float), defaultdict(float)
    ph, pn, reason = defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(int))
    for r in rows:
        m = month_of(r["date_key"])
        h[m] += r["people_helped"]
        nr[m] += r["people_not_reached"]
        ph[m][r["program"]] += r["people_helped"]
        pn[m][r["program"]] += r["people_not_reached"]
        if r["people_not_reached"]:
            reason[m][r["main_reason"]] += r["people_not_reached"]
    W = P.window
    reach = {m: (h[m] / (h[m] + nr[m]) if h[m] + nr[m] else None) for m in W}

    def sp(m):
        return support(f"People helped, {mlabel(m)}", "Helped ÷ (helped + couldn't reach)", [inp("People helped", "int", [h[m]]), inp("People not reached", "int", [nr[m]]),
                                                                                           calc("Share reached", "pct", "r0/(r0+r1)")], cols=(mlabel(m),))
    sups = [sp(m) for m in W]
    k = support(f"People helped, {P.month} and {P.prev_month}", "Helped ÷ (helped + couldn't reach)", [
        inp("People helped", "int", [h[P.mo], h[P.prev]]), inp("People not reached", "int", [nr[P.mo], nr[P.prev]]), calc("Share reached", "pct", "r0/(r0+r1)")],
        P.part_note or None, cols=(mlabel(P.mo), mlabel(P.prev)))
    rc = reach[P.mo] or 0
    items = [kpi(f"People helped, {P.when}", f"{int(h[P.mo]):,}", f"{P.prev_month} {int(h[P.prev]):,}", k),
             kpi(f"Couldn't reach, {P.when}", f"{int(nr[P.mo]):,}", f"{P.prev_month} {int(nr[P.prev]):,}", k, tone="warn" if rc < TARGET_REACH else ""),
             kpi(f"Share reached, {P.when}", pct(rc), f"target {pct(TARGET_REACH)}", k, tone=ek.tone(rc, "higher", TARGET_REACH, 0.03))]
    progs = sorted(ph[P.mo], key=lambda x: -(ph[P.mo][x] + pn[P.mo][x]))
    det = [support(f"{x}, {P.label}", "Helped ÷ (helped + couldn't reach)", [inp("People helped", "int", [ph[P.mo][x]]), inp("Couldn't reach", "int", [pn[P.mo][x]]),
                                                                             calc("Share reached", "pct", "r0/(r0+r1)")], cols=(P.short,)) for x in progs]
    rs = sorted(reason[P.mo], key=lambda x: -reason[P.mo][x])
    worst = min(progs, key=lambda x: ph[P.mo][x] / (ph[P.mo][x] + pn[P.mo][x])) if progs else None
    shows = (f"{int(h[P.mo]):,} people were helped in {P.when}, and {int(nr[P.mo]):,} came to a program but couldn't be helped: {pct(rc)} reached "
             f"(target {pct(TARGET_REACH)}), against {pct(reach[P.prev] or 0)} in {P.prev_month}.")
    action = flags_or([
        f"{worst} reached the smallest share: {pct(ph[P.mo][worst] / (ph[P.mo][worst] + pn[P.mo][worst]))} ({pn[P.mo][worst]} couldn't be helped)." if worst else None,
        f"The main reason: {rs[0].lower()} ({reason[P.mo][rs[0]]} people)." if rs else None],
        "Every program reached its target share.")
    answer = f"{int(h[P.mo]):,} people helped in {P.when}; {int(nr[P.mo]):,} couldn't be reached ({pct(rc)} reached, target {pct(TARGET_REACH)})."
    return report("people-helped", "nfp", "How many people did you help this month, and how many couldn't you reach?", "nfp", D, P,
                  "People helped by each program, day by day, and the people who came to a program but couldn't be helped (and why). People helped are counted against each program's own grant spend.",
                  [{"label": None, "sections": [
                      kpis(items),
                      {"type": "bars", "chart": {"title": f"Share of people reached, by program, {P.label}", "subtitle": f"Target {pct(TARGET_REACH)}.",
                                                 "labels": progs, "values": [round_half_up(100 * ph[P.mo][x] / (ph[P.mo][x] + pn[P.mo][x]), 1) for x in progs], "format": "pct1",
                                                 "target": round_half_up(100 * TARGET_REACH, 1), "details": det,
                                                 "views": [{"id": "share", "label": "Share reached %", "values": [round_half_up(100 * ph[P.mo][x] / (ph[P.mo][x] + pn[P.mo][x]), 1) for x in progs],
                                                            "format": "pct1", "target": round_half_up(100 * TARGET_REACH, 1)},
                                                           {"id": "helped", "label": "People helped", "values": [ph[P.mo][x] for x in progs], "format": "int"}]}},
                      series(P, "People helped by month", {
                          "All|helped": {"label": "People helped", "values": [int(h[m]) for m in W], "format": "int", "supports": sups},
                          "All|reach": {"label": "Share reached %", "values": [round_half_up(100 * reach[m], 1) if reach[m] is not None else None for m in W], "format": "pct1", "supports": sups},
                          "All|missed": {"label": "Couldn't reach", "values": [int(nr[m]) for m in W], "format": "int", "supports": sups}},
                          note="Tap a month for its workings.", dims={"line": ["All"], "measure": [("helped", "People helped"), ("reach", "Share reached %"), ("missed", "Couldn't reach")]}),
                      table(f"Why people couldn't be helped, {P.label}", ["Main reason", "People"], [[x, f"{reason[P.mo][x]:,}"] for x in rs], ["text", "int"]),
                      text(shows, action)]}],
                  {"head": ["Month", "Status", "People helped", "Couldn't reach", "Share reached"], "kinds": ["text", "text", "int", "int", "pct"],
                   "rows": [[mlabel(m), P.status_of(m), int(h[m]), int(nr[m]), "=IF(C{r}+D{r}=0,\"\",C{r}/(C{r}+D{r}))"] for m in W]}, answer)


BLOCKS = [("Before 8:30am", lambda hr: hr < 8.5), ("8:30 to 10am", lambda hr: 8.5 <= hr < 10), ("10am to noon", lambda hr: 10 <= hr < 12),
          ("Noon to 2pm", lambda hr: 12 <= hr < 14), ("2 to 5pm", lambda hr: 14 <= hr < 17), ("5 to 8pm", lambda hr: 17 <= hr < 20), ("After 8pm", lambda hr: hr >= 20)]


def nth(n):
    """1st, 2nd, 3rd, 4th ... 11th, 12th, 13th ... 21st."""
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n:,}{suffix}"


def calls(D, P):
    rows = D["_src"].table("nfp", "fact_call")
    W = P.window
    tot, staffed, ans, waits = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(list)
    blk = defaultdict(lambda: [0, 0])
    for r in rows:
        m = month_of(r["date_key"])
        tot[m] += 1
        t = r["received_at"]
        hr = int(t[11:13]) + int(t[14:16]) / 60
        in_hours = r["outcome"] != "After hours: voicemail"
        if in_hours:
            staffed[m] += 1
            ans[m] += r["answered"]
            if r["answered"]:
                waits[m].append(r["wait_seconds"])
        if m == P.mo:
            for name, test in BLOCKS:
                if test(hr):
                    blk[name][0] += 1
                    blk[name][1] += r["answered"]
    rate = {m: (ans[m] / staffed[m] if staffed[m] else None) for m in W}

    def sp(m):
        return support(f"Calls for help, {mlabel(m)}", "Answered ÷ calls while the line was staffed", [
            inp("Calls", "int", [tot[m]]), inp("Calls while the line was staffed (8:30am to 5pm, working days)", "int", [staffed[m]]),
            inp("Answered", "int", [ans[m]]), calc("Answered while staffed", "pct", "r2/r1"), calc("Calls outside staffed hours", "pct", "(r0-r1)/r0")], cols=(mlabel(m),))
    sups = [sp(m) for m in W]
    k = support(f"Calls for help, {P.month} and {P.prev_month}", "Answered ÷ calls while the line was staffed", [
        inp("Calls", "int", [tot[P.mo], tot[P.prev]]), inp("Calls while staffed", "int", [staffed[P.mo], staffed[P.prev]]), inp("Answered", "int", [ans[P.mo], ans[P.prev]]),
        calc("Answered while staffed", "pct", "r2/r1"), calc("Calls outside staffed hours", "pct", "(r0-r1)/r0")], P.part_note or None, cols=(mlabel(P.mo), mlabel(P.prev)))
    rc = rate[P.mo] or 0
    after = 1 - staffed[P.mo] / tot[P.mo] if tot[P.mo] else 0
    mw = half_up(median(waits[P.mo])) if waits[P.mo] else 0          # rounded once, half up
    mw_p = half_up(median(waits[P.prev])) if waits[P.prev] else 0
    srt = sorted(waits[P.mo])
    mid = len(srt) // 2
    k_wait = support(f"Median wait when answered, {P.month} and {P.prev_month}", "The middle wait when every answered call is lined up from shortest to longest", [
        inp("Answered calls (while staffed)", "int", [len(waits[P.mo]), len(waits[P.prev])]),
        inp("Median wait (seconds, rounded half up)", "int", [mw, mw_p])],
        (f"{P.month}: {len(srt):,} waits in order; the median is "
         + (f"the {nth(mid + 1)}, {srt[mid]} seconds." if len(srt) % 2 else f"halfway between the {nth(mid)} and {nth(mid + 1)} ({srt[mid - 1]} and {srt[mid]} seconds).")
         if srt else "No answered calls.") + " Unanswered calls and calls outside staffed hours have no wait to count. " + (P.part_note or ""),
        cols=(mlabel(P.mo), mlabel(P.prev)))
    items = [kpi(f"Calls for help, {P.when}", f"{tot[P.mo]:,}", f"{P.prev_month} {tot[P.prev]:,}", k),
             kpi(f"Answered while staffed, {P.when}", pct(rc), f"target {pct(TARGET_ANSWER)}", k, tone=ek.tone(rc, "higher", TARGET_ANSWER, 0.03)),
             kpi(f"Calls outside staffed hours, {P.when}", pct(after), f"{tot[P.mo] - staffed[P.mo]:,} calls to voicemail", k),
             kpi(f"Median wait when answered, {P.when}", f"{mw} sec", f"{len(waits[P.mo]):,} answered calls", k_wait)]
    labs = [b for b, _ in BLOCKS]
    det = [support(f"Calls {b.lower()}, {P.label}", "Answered ÷ calls", [inp("Calls", "int", [blk[b][0]]), inp("Answered", "int", [blk[b][1]]), calc("Answered", "pct", "r1/r0")],
                   "Outside 8:30am to 5pm on working days the line goes to voicemail.", cols=(P.short,)) for b in labs]
    busiest = max(labs, key=lambda b: blk[b][0])
    evening = blk["5 to 8pm"][0]
    shows = (f"{tot[P.mo]:,} calls for help came in during {P.when}. While the line was staffed, {pct(rc)} were answered (target {pct(TARGET_ANSWER)}); "
             f"{pct(after)} of all calls came outside staffed hours and went to voicemail. The busiest time was {busiest.lower()} ({blk[busiest][0]:,} calls).")
    action = flags_or([
        f"{evening:,} calls came between 5 and 8pm, when no-one is on the line." if evening else None,
        f"{staffed[P.mo] - ans[P.mo]:,} callers hung up waiting while the line was staffed." if staffed[P.mo] > ans[P.mo] else None],
        "Every staffed-hours call was answered.")
    answer = f"{tot[P.mo]:,} calls in {P.when}: {pct(rc)} answered while staffed (target {pct(TARGET_ANSWER)}); {pct(after)} came outside staffed hours."
    return report("calls", "nfp", "When do calls for help come in, and are you there to answer?", "nfp", D, P,
                  "Every call to the help line: when it came in, whether someone answered, and how long the caller waited. The line is staffed 8:30am to 5pm on working days.",
                  [{"label": None, "sections": [
                      kpis(items),
                      {"type": "bars", "chart": {"title": f"When the calls come in, {P.label}", "subtitle": "Calls by time of day, and the share answered.",
                                                 "labels": labs, "values": [blk[b][0] for b in labs], "format": "int", "plain": True, "details": det, "keep_order": True,
                                                 "views": [{"id": "calls", "label": "Calls", "values": [blk[b][0] for b in labs], "format": "int"},
                                                           {"id": "answered", "label": "Answered %", "values": [round_half_up(100 * blk[b][1] / blk[b][0], 1) if blk[b][0] else 0 for b in labs], "format": "pct1"}]}},
                      series(P, "Calls for help by month", {
                          "All|calls": {"label": "Calls", "values": [tot[m] for m in W], "format": "int", "supports": sups},
                          "All|rate": {"label": "Answered while staffed %", "values": [round_half_up(100 * rate[m], 1) if rate[m] is not None else None for m in W], "format": "pct1", "supports": sups}},
                          note="Tap a month for its workings.", dims={"line": ["All"], "measure": [("calls", "Calls"), ("rate", "Answered while staffed %")]}),
                      text(shows, action)]}],
                  {"head": ["Month", "Status", "Calls", "While staffed", "Answered", "Answered while staffed"], "kinds": ["text", "text", "int", "int", "int", "pct"],
                   "rows": [[mlabel(m), P.status_of(m), tot[m], staffed[m], ans[m], "=IF(D{r}=0,\"\",E{r}/D{r})"] for m in W]}, answer)


def volunteers(D, P):
    rows = D["_src"].table("nfp", "fact_volunteer_shift")
    W = P.window
    hrs, people, prog = defaultdict(float), defaultdict(set), defaultdict(lambda: defaultdict(float))
    for r in rows:
        m = month_of(r["date_key"])
        hrs[m] += r["hours"]
        people[m].add(r["volunteer_id"])
        prog[m][r["program"]] += r["hours"]

    def sp(m):
        return support(f"Volunteer hours, {mlabel(m)}", "Hours from every volunteer shift", [inp("Volunteer hours", "hours", [hrs[m]]), inp("Volunteers who did a shift", "int", [len(people[m])]),
                                                                                           calc("Hours per volunteer", "hours", "r0/r1")], cols=(mlabel(m),))
    sups = [sp(m) for m in W]
    k = support(f"Volunteer hours, {P.month} and {P.prev_month}", "Hours from every volunteer shift", [
        inp("Volunteer hours", "hours", [hrs[P.mo], hrs[P.prev]]), inp("Volunteers who did a shift", "int", [len(people[P.mo]), len(people[P.prev])]),
        calc("Hours per volunteer", "hours", "r0/r1")], P.part_note or None, cols=(mlabel(P.mo), mlabel(P.prev)))
    items = [kpi(f"Volunteer hours, {P.when}", FMT["hours"](hrs[P.mo]), f"{P.prev_month} {FMT['hours'](hrs[P.prev])}", k),
             kpi(f"Volunteers who did a shift, {P.when}", f"{len(people[P.mo])}", f"{P.prev_month} {len(people[P.prev])}", k),
             kpi(f"Hours per volunteer, {P.when}", FMT["hours"](hrs[P.mo] / len(people[P.mo]) if people[P.mo] else 0), "average", k)]
    if P.ly_ok:
        items.append(kpi(f"{P.month} last year", FMT["hours"](hrs[P.ly]), f"{len(people[P.ly])} volunteers", sp(P.ly)))
    ps = sorted(prog[P.mo], key=lambda x: -prog[P.mo][x])
    det = [support(f"{x}: volunteer hours, {P.label}", "Hours from shifts on this program", [inp("Volunteer hours", "hours", [prog[P.mo][x]]), inp("All volunteer hours", "hours", [hrs[P.mo]]),
                                                                                          calc("Share", "pct", "r0/r1")], cols=(P.short,)) for x in ps]
    shows = (f"{len(people[P.mo])} volunteers gave {FMT['hours'](hrs[P.mo])} in {P.when}, against {FMT['hours'](hrs[P.prev])} in {P.prev_month}. "
             + (f"{ps[0]} drew the most ({FMT['hours'](prog[P.mo][ps[0]])}, {pct(prog[P.mo][ps[0]] / hrs[P.mo])})." if ps else ""))
    least = ps[-1] if ps else None
    action = flags_or([
        f"{least} had the fewest volunteer hours ({FMT['hours'](prog[P.mo][least])})." if least else None,
        (f"Hours are {'up' if hrs[P.mo] >= hrs[P.ly] else 'down'} {pct(abs(hrs[P.mo] / hrs[P.ly] - 1))} on {P.month} last year." if P.ly_ok and hrs[P.ly] else None)],
        "Volunteer hours are steady.")
    answer = f"{FMT['hours'](hrs[P.mo])} of volunteer time in {P.when}, from {len(people[P.mo])} volunteers; most went to {ps[0] if ps else 'no program'}."
    return report("volunteers", "nfp", "How many volunteer hours go into each program?", "nfp", D, P,
                  "Every volunteer shift: who (a code, not a name), which program, and how many hours.",
                  [{"label": None, "sections": [
                      kpis(items),
                      {"type": "bars", "chart": {"title": f"Volunteer hours by program, {P.label}", "subtitle": "Hours from every shift.", "labels": ps,
                                                 "values": [round_half_up(prog[P.mo][x], 1) for x in ps], "format": "int", "plain": True, "details": det}},
                      series(P, "Volunteer hours by month", {
                          "All|hours": {"label": "Volunteer hours", "values": [round_half_up(hrs[m], 1) for m in W], "format": "int", "supports": sups},
                          "All|people": {"label": "Volunteers", "values": [len(people[m]) for m in W], "format": "int", "supports": sups}},
                          note="Tap a month for its workings.", dims={"line": ["All"], "measure": [("hours", "Volunteer hours"), ("people", "Volunteers")]}),
                      text(shows, action)]}],
                  {"head": ["Month", "Status", "Volunteer hours", "Volunteers", "Hours per volunteer"], "kinds": ["text", "text", "hours", "int", "hours"],
                   "rows": [[mlabel(m), P.status_of(m), hrs[m], len(people[m]), "=IF(D{r}=0,\"\",C{r}/D{r})"] for m in W]}, answer)
