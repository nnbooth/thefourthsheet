"""
dashboard_months.py — the home page's sample dashboard for every month, not just September.

The September dashboard comes from the driver-based model (financial_model.py, via publish_dashboard.py): full
profit and loss, balance sheet and cash flow, September against August. This builds the same dashboard for every
other month the data has (November 2024 to October 2026 to date), straight from the daily ledger and the operational
tables, using the model's own definitions for every headline number:

  - Profit and loss (income and expenditure): every month, from the ledger. Same lines and totals as September;
    lines that only exist in history (finished grants) are added in their section. The bottom line must equal the
    ledger for the month, or the build stops.
  - The fourth sheet: the same three headline numbers per organisation and the same chart, for that month against
    the month before. Where a number needs month-end balances (the not-for-profit's runway; the services firm's
    unbilled work) it is only shown from the opening balance, 31 July 2026, and says so before that.
  - Balance sheet and cash flow: the full statements exist for September 2026 (the month modelled end to end).
    Other months say so rather than invent balance-sheet history.

CHECKED: September built this way equals the model's September (every profit-and-loss line and every headline
number), so the two routes can't drift apart.

Writes data/dashboard-months.js (the list of months) and data/dashboard/<yyyy-mm>.js (one file per month, loaded
when someone picks it).
"""

import json
import re
from datetime import date
from pathlib import Path

import data_status as ds
import financial_model as fm
from financial_model import FMT, calc, half_up, inp, money, support, round_half_up

from . import catalogue as C
from .period import CURRENT, Period, add_months, mdate

REPO = Path(__file__).resolve().parents[3]
BASE = "2026-09"               # the model's month: its dashboard is the full one (dashboard-data.js)
OPENING = "2026-07"            # month-end balances start at the opening balance, 31 July 2026
GRANT = " grant"


def base_payload():
    js = (REPO / "data" / "dashboard-data.js").read_text(encoding="utf-8")
    return json.loads(js[js.index("{"): js.rindex("}") + 1])


def months_for(D):
    ms = D["trades"].months
    return [m for m in ms[1:] if m <= CURRENT]          # each month needs the one before it to compare


def lab(m):
    return mdate(m).strftime("%b %Y")


def chg(cur, prev, fmt, better, prev_name):
    """The model's change line ("▲ from 35.5% in Aug"), for any pair of months."""
    if cur is None or prev is None:
        return ("no figure for the month before" if prev is None else ""), ""
    if fmt(cur) == fmt(prev):
        return f"■ same as {prev_name} ({fmt(prev)})", ""
    up = cur > prev
    good = up == (better == "up")
    return f"{'▲' if up else '▼'} from {fmt(prev)} in {prev_name}", "good" if good else "bad"


# ------------------------------------------------------------------ profit and loss from the ledger

def statement_template(o, base_rows):
    """The September statement's lines, plus any ledger line that only exists in other months, in its section."""
    rows = [dict(r) for r in base_rows]
    have = {r["label"] for r in rows}
    extra = sorted({l for m in o.months for l in o.by_line(m) if l not in have})
    for label in extra:
        sec = o.sections.get(label, "")
        h = next((i for i, r in enumerate(rows) if r["level"] == "heading" and r["label"].lower() == sec.lower()), None)
        if h is None:
            raise SystemExit(f"dashboard months: no section '{sec}' for ledger line '{label}'")
        i = h + 1
        while i < len(rows) and rows[i]["level"] == "detail":
            i += 1
        rows.insert(i, {"label": label, "level": "detail", "values": [0, 0], "note": None})
    return rows


def profit_and_loss(D, org, template, spec, mo, prev, title):
    o = D[org]
    rows = []
    for r, sp in zip(template, spec):
        if sp is None:
            rows.append({"label": r["label"], "level": r["level"], "values": None, "note": None})
            continue
        if sp == "input":
            vals = [o.line(mo, r["label"]), o.line(prev, r["label"])]
        else:
            vals = None
        rows.append({"label": r["label"], "level": r["level"], "values": vals, "note": None})
    for i, sp in enumerate(spec):             # subtotals and totals: the same formulas as the September statement
        if isinstance(sp, tuple):
            kind, refs = sp
            if kind == "sum":
                rows[i]["values"] = [sum(rows[j]["values"][c] for j in refs) for c in range(2)]
            else:
                rows[i]["values"] = [sum(sg * rows[j]["values"][c] for j, sg in refs) for c in range(2)]
    for c, m in enumerate((mo, prev)):        # the bottom line ties to the ledger
        ledger = sum(o.by_line(m).values())
        if round_half_up(rows[-1]["values"][c]) != round_half_up(ledger):
            raise SystemExit(f"dashboard months: {org} {m} bottom line {rows[-1]['values'][c]} doesn't tie to the ledger {ledger}")
    # a count in a line's name ("Maintenance contracts (14)") is the count for that month
    for r in rows:
        mt = re.match(r"^(Maintenance contracts) \(\d+\)$", r["label"])
        if mt and org == "trades":
            n = sum(1 for j in D["_jobs"] if j["month"] == mo and j["type"] == "Maintenance contract")
            r["label"] = f"{mt.group(1)} ({n})"
    rows = [r for r in rows if r["level"] != "detail" or any(r["values"])]         # lines with nothing in either month
    return {"tab": "Income & exp." if org == "nfp" else "P&L", "title": title, "rows": rows}


def total(stmt, label):
    r = next((r for r in stmt["rows"] if r["label"] == label), None)
    return r["values"] if r else [0, 0]


def working_days(D, mo):
    dd = D["_src"].table(None, "dim_date")
    end = int(min(ds.month_end(mo), ds.AS_AT.date()).strftime("%Y%m%d"))
    return sum(1 for r in dd if r["month_key"] == mo and r["is_working_day"] == 1 and r["date_key"] <= end)


def hours(D, org, mo):
    k = "job_id" if org == "trades" else "engagement_id"
    return sum(r["hours"] for r in D["_src"].table(org, "fact_timesheet_daily") if str(r["date_key"])[:6] == mo.replace("-", "") and r.get(k))


# ------------------------------------------------------------------ the fourth sheet, per organisation

def fourth_trades(D, P, pnl, prev_name):
    o, mo, pv = D["trades"], P.mo, P.prev
    S = lambda f: [f(mo), f(pv)]
    cols = (lab(mo), lab(pv))
    rev = total(pnl, "Total revenue")
    s_gm = support("Gross margin (P&L)", "Gross profit ÷ revenue. All technician wages and on-costs included; overheads are not.", [
        inp("Revenue (every job invoiced in the month)", "money", rev), inp("Materials", "money", S(lambda m: o.line(m, "Materials"))),
        inp("Subcontractors", "money", S(lambda m: o.line(m, "Subcontractors"))), inp("Technician wages", "money", S(lambda m: o.line(m, "Technician wages (incl. on-costs)"))),
        calc("Gross profit", "money", "r0+r1+r2+r3"), calc("Gross margin (P&L)", "pct", "r4/r0")],
        "Gross margin is before overheads (office wages, marketing, vehicles, rent and so on): it is not profit. Wages include their on-costs: super (12%) and leave as it's earned. No payroll tax: wages are under Queensland's $1.3 million threshold."
        + (f" {P.part_note}" if P.incomplete else ""), cols=cols)
    nc = o.drivers["New customers (first job ever)"]
    have_nc = mo in nc and pv in nc
    s_cac = support("Cost to win a customer", "Marketing spend ÷ new customers", [
        inp("Marketing spend", "money", S(lambda m: -o.line(m, "Marketing"))), inp("New customers (first job ever)", "int", S(lambda m: nc.get(m, 0))),
        calc("Cost per new customer", "money", "r0/r1")], None if have_nc else "New customers are counted at month end, so the month in progress has no figure yet.", cols=cols)
    techs = o.drivers["Technicians"]
    s_ut = support("Technician time on jobs", "Hours charged to jobs ÷ hours available", [
        inp("Hours charged to jobs (timesheets)", "hours", S(lambda m: hours(D, "trades", m))), inp("Technicians", "int", S(lambda m: techs[m])),
        inp("Working days", "int", S(lambda m: working_days(D, m))), inp("Hours per day", "hours", S(lambda m: fm.HOURS_PER_DAY)),
        calc("Hours available", "hours", "r1*r2*r3"), calc("Time on jobs", "pct", "r0/r4")], "The rest is travel, training, quoting and waiting time.", cols=cols)
    v = lambda sp: sp["xl"]["rows"][-1]["values"]
    gm, cac, ut = v(s_gm), v(s_cac), v(s_ut)
    k1, c1 = chg(gm[0], gm[1], FMT["pct"], "up", prev_name)
    k2, c2 = chg(cac[0], cac[1], FMT["money"], "down", prev_name) if have_nc else ("counted at month end", "")
    k3, c3 = chg(ut[0], ut[1], FMT["pct"], "up", prev_name)
    rate, tgt = o.rates["Technician cost rate"], 100 * o.targets["Installation job margin"]
    inst = sorted([j for j in D["_jobs"] if j["month"] == mo and j["type"] == "Installation"], key=lambda j: -j["gross_profit"] / j["revenue"])
    chart = C.margin_chart(f"Job gross margin on each installation invoiced in {P.label}",
                           f"Whole job, recognised when invoiced: revenue less materials, subcontractors and technician time at ${rate}/hour. Before overheads: not profit. One {tgt:.1f}% target for every job for now.",
                           [j["description"] for j in inst], [j["revenue"] for j in inst], [j["gross_profit"] for j in inst], tgt, [C.job_support(j, rate) for j in inst])
    chart.pop("breakeven", None)
    chart["what"] = "job margin"
    return {"kpis": [{"label": f"Gross margin (P&L), {P.when}", "value": FMT["pct"](gm[0]), "sub": k1, "cls": c1, "spine": True, "support": s_gm},
                     {"label": "Cost to win a customer", "value": FMT["money"](cac[0]) if have_nc else "–", "sub": k2, "cls": c2, "good_when": "lower", "support": s_cac},
                     {"label": "Technician time on jobs", "value": FMT["pct"](ut[0]), "sub": k3, "cls": c3, "support": s_ut}],
            "chart": chart}


def fourth_services(D, P, pnl, prev_name):
    o, mo, pv, src = D["services"], P.mo, P.prev, D["_src"]
    S = lambda f: [f(mo), f(pv)]
    cols = (lab(mo), lab(pv))
    cons = o.drivers["Consultants"]
    s_ut = support("Consultant utilisation", "Billable hours ÷ hours available", [
        inp("Billable hours (timesheets)", "hours", S(lambda m: hours(D, "services", m))), inp("Consultants", "int", S(lambda m: cons[m])),
        inp("Working days", "int", S(lambda m: working_days(D, m))), inp("Hours per day", "hours", S(lambda m: fm.HOURS_PER_DAY)),
        calc("Hours available", "hours", "r1*r2*r3"), calc("Utilisation", "pct", "r0/r4")], P.part_note or None, cols=cols)
    s_rate = support("Revenue per billable hour", "Revenue ÷ billable hours", [
        inp("Revenue", "money", total(pnl, "Total revenue")), inp("Billable hours", "hours", S(lambda m: hours(D, "services", m))),
        calc("Revenue per hour", "money", "r0/r1")], ("Retainers are billed on the first of the month, so the month in progress has no fair hourly figure yet. It's counted at month end."
                                                     if P.incomplete else "Retainers and training are fixed fees, so fewer hours on them raises the hourly figure."), cols=cols)
    em = src.table("services", "fact_engagement_month")
    wip = lambda m: (sum(r["wip_closing"] or 0 for r in em if r["month_key"] == m) if m >= "2026-08" else None)
    inv = [i for i in src.table("services", "fact_invoice") if i["org_id"] == "services"]
    debt = lambda m: sum(i["amount"] for i in inv if i["invoice_date"] <= min(ds.month_end(m), ds.AS_AT.date()).isoformat()
                         and (not i["paid_date"] or i["paid_date"] > min(ds.month_end(m), ds.AS_AT.date()).isoformat()))
    full = wip(mo) is not None and wip(pv) is not None
    if full:
        s_lock = support("Cash tied up in work", "Work in progress + unpaid invoices at month end", [
            inp("Work in progress (project time not yet billed)", "money", S(wip)), inp("Unpaid client invoices", "money", S(debt)),
            calc("Total tied up", "money", "r0+r1")], P.part_note or None, cols=cols)
    else:
        s_lock = support("Unpaid client invoices", "Invoices raised and not yet paid, at month end", [inp("Unpaid client invoices", "money", S(debt))],
                         "Unbilled work (work in progress) is only in the data from August 2026, so this month shows unpaid invoices alone.", cols=cols)
    v = lambda sp: sp["xl"]["rows"][-1]["values"]
    ut, rt, lk = v(s_ut), v(s_rate), v(s_lock)
    k1, c1 = chg(ut[0], ut[1], FMT["pct"], "up", prev_name)
    k2, c2 = ("counted at month end", "") if P.incomplete else chg(rt[0], rt[1], FMT["money"], "up", prev_name)
    k3, c3 = chg(lk[0], lk[1], FMT["money"], "down", prev_name)
    rate, tgt = o.rates["Consultant cost rate"], 100 * o.targets["Engagement margin"]
    eng = sorted([x for x in D["_engagements"] if x["month"] == mo and x["revenue"]], key=lambda x: -x["contribution"] / x["revenue"])
    details = [support(x["description"], "Gross margin ÷ revenue for this engagement (before overheads)", [
        inp("Revenue", "money", [x["revenue"]]), inp("Contractors", "money", [-x["contractors"]]),
        inp("Consultant hours", "hours", [x["hours"]]), inp("Consultant cost rate ($/hour, wages and all on-costs)", "money", [rate]),
        calc("Consultant time", "money", "-r2*r3"), calc("Gross margin", "money", "r0+r1+r4"), calc("Gross margin %", "pct", "r5/r0")],
        cols=("This engagement",)) for x in eng]
    chart = C.margin_chart(f"Gross margin on each client engagement, {P.label} work only",
                           f"{P.month}'s revenue less contractors and consultant time at ${rate}/hour. Before overheads: not profit. Not the whole engagement to date. One {tgt:.1f}% target for every engagement for now.",
                           [x["description"] for x in eng], [x["revenue"] for x in eng], [x["contribution"] for x in eng], tgt, details)
    chart.pop("breakeven", None)
    chart["what"] = "engagement margin"
    return {"kpis": [{"label": f"Consultant utilisation, {P.when}", "value": FMT["pct"](ut[0]), "sub": k1, "cls": c1, "spine": True, "support": s_ut},
                     {"label": "Revenue per billable hour", "value": "–" if P.incomplete else FMT["money"](rt[0]), "sub": k2, "cls": c2, "support": s_rate},
                     {"label": "Unbilled work + unpaid invoices" if full else "Unpaid client invoices", "value": FMT["money"](lk[0]), "sub": k3, "cls": c3,
                      "good_when": "lower", "support": s_lock}],
            "chart": chart}


def fourth_nfp(D, P, pnl, prev_name):
    o, mo, pv = D["nfp"], P.mo, P.prev
    S = lambda f: [f(mo), f(pv)]
    cols = (lab(mo), lab(pv))
    fund = ["Grant writing and reporting", "Donor campaigns", "Event costs"]
    rows = [inp(k, "money", S(lambda m, k=k: -o.line(m, k))) for k in fund]
    nf = len(rows)
    grants_in = lambda m: sum(v for k, v in o.by_line(m).items() if k.endswith(GRANT))
    s_ctr = support("Cost to raise a dollar", "Fundraising costs ÷ money raised (grants, donations, events), in cents", rows + [
        calc("Fundraising costs", "money", "+".join(f"r{i}" for i in range(nf))),
        inp("Grant income", "money", S(grants_in)), inp("Donations", "money", S(lambda m: o.line(m, "Donations"))),
        inp("Fundraising events", "money", S(lambda m: o.line(m, "Fundraising events"))),
        calc("Money raised", "money", f"r{nf + 1}+r{nf + 2}+r{nf + 3}"), calc("Cost per dollar raised", "cents", f"r{nf}/r{nf + 4}*100")],
        P.part_note or None, cols=cols)
    tgt = D["_targets"]["Reserves (unrestricted cash runway)"]
    has_cash = pv >= OPENING
    if has_cash:
        def rn(m):
            Q = Period(m, o.months)
            cash, adv, spend, _, ato = C.runway_numbers(D, Q, m)
            return cash, adv, spend, ato
        a, b = rn(mo), rn(pv)
        s_run = support("Unrestricted cash runway", C.RUNWAY_FORMULA, [
            inp("Cash at bank", "money", [a[0], b[0]]), inp("Less unspent grant money (belongs to funders' programs)", "money", [-a[1], -b[1]]),
            inp("Less GST and PAYG withheld owed to the ATO (paid with the BAS)", "money", [-a[3], -b[3]]),
            calc("Unrestricted cash", "money", "r0+r1+r2"), inp("Cash spending in the month (expenses less depreciation)", "money", [a[2], b[2]]),
            calc("Runway", "months", "r3/r4")], f"Reserves target: {FMT['months'](tgt)}." + (f" {P.part_note}" if P.incomplete else ""), cols=cols)
    else:
        s_run = support("Unrestricted cash runway", C.RUNWAY_FORMULA, [inp("Not in the data for this month", "text", ["–"])],
                        "Cash and grant balances start at the opening balance, 31 July 2026, so runway can be worked out from July 2026.", cols=(lab(mo),))
    ending_window = D["_targets"]["Grants ending soon: window"]
    G = C.grant_positions(D, P)
    live = [g for g in G if g["active"]]
    ending = sorted([g for g in live if g["months_left"] <= ending_window], key=lambda g: g["months_left"])
    s_end = support(f"Grants ending in the next {ending_window} months", "Grant total − spent to date, for each grant ending soon",
                    [inp(f"{g['program']} (ends {ds.strf(date.fromisoformat(g['end']), '%-d %b %Y')})", "money", [g["unspent"]]) for g in ending]
                    + ([calc("Total still to spend", "money", "+".join(f"r{i}" for i in range(len(ending))))] if ending else [inp("No grant ends within the window", "money", [0])]),
                    "Unspent money usually has to be returned, or an extension negotiated, so plan the spending now.", cols=("Still to spend",))
    ctr = s_ctr["xl"]["rows"][-1]["values"]
    k1, c1 = chg(ctr[0], ctr[1], FMT["cents"], "down", prev_name)
    if has_cash:
        run = s_run["xl"]["rows"][-1]["values"]
        k2, c2 = chg(run[0], run[1], FMT["months"], "up", prev_name)
        run_v = FMT["months"](run[0])
    else:
        k2, c2, run_v = "cash data starts 31 Jul 2026", "", "–"
    GS = sorted(live, key=lambda g: -g["total"])
    mname = lambda m: date(int(m[:4]), int(m[5:]), 1).strftime("%b %y")
    details = [support(g["program"], f"{g['funder']} · {money(g['total'])} · {date.fromisoformat(g['start']).strftime('%b %Y')} to {date.fromisoformat(g['end']).strftime('%b %Y')}", [
        inp("Grant total", "money", [g["total"]]), inp("Received from the funder", "money", [g["received"]]),
        inp("Spent to date", "money", [g["spent_to_date"]]), inp("Budget to date", "money", [g["budget_to_date"]]),
        inp("Months left", "int", [g["months_left"]]), calc("Still to spend", "money", "r0-r2"),
        calc("Over (under) budget to date", "money", "r2-r3"), calc("Over (under) budget, % of budget to date", "pct", "r2/r3-1")], None,
        {"title": "Spend by month against budget", "labels": [mname(x[0]) for x in g["monthly"]],
         "values": [x[1] for x in g["monthly"]], "budget": [x[2] for x in g["monthly"]], "format": "money0"}, cols=("This grant",)) for g in GS]
    pcts = [round_half_up(d["xl"]["rows"][-1]["values"][0] * 100, 1) for d in details]
    var_d = [d["xl"]["rows"][-2]["values"][0] for d in details]
    end_l = ds.strf(min(ds.month_end(mo), ds.AS_AT.date()), "%-d %B %Y")
    return {"kpis": [{"label": f"Cost to raise a dollar, {P.when}", "value": FMT["cents"](ctr[0]), "sub": k1, "cls": c1, "good_when": "lower", "spine": True, "support": s_ctr},
                     {"label": "Unrestricted cash runway", "value": run_v, "sub": k2, "cls": c2, "support": s_run},
                     {"label": f"Grants ending in {ending_window} months", "value": money(sum(g["unspent"] for g in ending)),
                      "sub": f"to spend in {ending_window} months · {len(ending)} grant{'s' if len(ending) != 1 else ''} ending", "cls": "bad" if ending else "", "good_when": "lower", "support": s_end}],
            "chart": {"title": f"Each grant: over or under budget to {end_l}",
                      "subtitle": "Spending to date against budget to date (the grant spread evenly over its months). Over budget in red, under budget in green; within 1% in amber.",
                      "labels": [g["program"] for g in GS], "values": pcts, "format": "pct_var", "what": "grant", "variance": True,
                      "views": [{"id": "pct", "label": "% of budget", "values": pcts, "format": "pct_var"},
                                {"id": "dollars", "label": "$", "values": var_d, "format": "money_var"}],
                      "details": details}}


FOURTH = {"trades": fourth_trades, "services": fourth_services, "nfp": fourth_nfp}


def month_payload(D, base, mo, templates):
    from publish_dashboard import statement_spec
    P = Period(mo, D["trades"].months)
    prev_name = mdate(P.prev).strftime("%b")
    orgs = []
    for bo in base["orgs"]:
        org = bo["id"]
        tpl, spec = templates[org]
        title = re.sub(r"(Profit and loss|Income and expenditure), .*", lambda m_: f"{m_.group(1)}, {P.label}", bo["statements"]["pnl"]["title"])
        pnl = profit_and_loss(D, org, tpl, spec, mo, P.prev, title)
        note = ("The balance sheet and cash flow are built in full for September 2026, the month-end modelled end to end. "
                "Pick September 2026 to see them; the profit and loss and the fourth sheet are here for every month.")
        orgs.append({**{k: bo[k] for k in ("id", "toggle", "name", "about", "unit")},
                     "columns": [lab(mo), lab(P.prev)],
                     "statements": {"pnl": pnl, "bs": {"tab": "Balance sheet", "title": "Balance sheet", "unavailable": note},
                                    "cf": {"tab": "Cash flow", "title": "Cash flow", "unavailable": note}},
                     "fourth": FOURTH[org](D, P, pnl, prev_name),
                     "checks": ["Every subtotal and total adds up", "The bottom line ties to the ledger for the month", "Every headline number shows its workings"],
                     "assumptions": [[g, [[a, (P.label if a == "Reporting month" else b)] for a, b in items]] for g, items in bo["assumptions"]],
                     "exports": {}, "exports_meta": {"unavailable": "The monthly pack is built for September 2026. Every report page has downloads for each month."}})
    status = [{"month": m, "label": lab(m), "status": ds.month_status(m)[0], "note": ds.month_status(m)[1]}
              for m in [mo, P.prev] + ([CURRENT] if CURRENT > mo else [])]
    return {"generated": base.get("generated"), "as_at": base.get("as_at"), "month": mo, "label": P.label, "status": status, "orgs": orgs}


def build(D):
    from publish_dashboard import statement_spec
    base = base_payload()
    templates = {}
    for bo in base["orgs"]:
        tpl = statement_template(D[bo["id"]], bo["statements"]["pnl"]["rows"])
        templates[bo["id"]] = (tpl, statement_spec(tpl))
    # the safety net: September built from the ledger must equal the model's September
    sep = month_payload(D, base, BASE, templates)
    for bo, so in zip(base["orgs"], sep["orgs"]):
        want = {r["label"]: r["values"] for r in bo["statements"]["pnl"]["rows"] if r["values"] is not None}
        for r in so["statements"]["pnl"]["rows"]:
            if r["values"] is not None and r["label"] in want and [round_half_up(x) for x in r["values"]] != [round_half_up(x) for x in want[r["label"]]]:
                raise SystemExit(f"dashboard months: {bo['id']} September '{r['label']}' {r['values']} isn't the model's {want[r['label']]}")
        for kb, ks in zip(bo["fourth"]["kpis"], so["fourth"]["kpis"]):
            if kb["value"] != ks["value"]:
                raise SystemExit(f"dashboard months: {bo['id']} September '{kb['label']}' {ks['value']} isn't the model's {kb['value']}")
    out_dir = REPO / "data" / "dashboard"
    out_dir.mkdir(parents=True, exist_ok=True)
    listing = []
    for mo in months_for(D):
        st = ds.month_status(mo)[0]
        P = Period(mo, D["trades"].months)
        listing.append({"value": mo, "label": P.label, "status": st})
        if mo == BASE:
            continue                          # September is the full dashboard (dashboard-data.js)
        p = month_payload(D, base, mo, templates)
        js = (f"/* GENERATED by tools/3_publish_site/fourthsheet/dashboard_months.py for {P.label}. Sample data. */\n"
              f"(window.FOURTH_SHEET_DASHBOARD_MONTHS = window.FOURTH_SHEET_DASHBOARD_MONTHS || {{}})[{json.dumps(mo)}] = "
              + json.dumps(p, ensure_ascii=False, separators=(",", ":")) + ";\n")
        f = out_dir / f"{mo}.js"
        if not f.exists() or f.read_text(encoding="utf-8") != js:
            f.write_text(js, encoding="utf-8")
    listing.reverse()                         # newest first, like the report pages
    (REPO / "data" / "dashboard-months.js").write_text(listing_js(BASE, listing), encoding="utf-8")
    return len(listing)


def listing_js(default, listing):
    """The list of months, one month to a line so it reads as a table."""
    rows = ",\n".join("    " + json.dumps(m, ensure_ascii=False) for m in listing)
    return ("/* GENERATED by tools/3_publish_site/fourthsheet/dashboard_months.py: the months the home dashboard can show (newest first). */\n"
            "window.FOURTH_SHEET_DASHBOARD_LIST = {\n"
            f"  \"default\": {json.dumps(default)},\n"
            "  \"months\": [\n" + rows + "\n  ]\n};\n")
