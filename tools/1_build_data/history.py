#!/usr/bin/env python3
"""
history.py — 24 months of history (Oct 2024 to Sep 2026) and October 2026 to
date, for the three sample organisations, at transaction level.

August and September 2026 are LOCKED: they come from financial_model.py and
are never changed here. Everything else is generated from its own random
seeds, so adding history can't move a locked number.

  Months before August  Oct 2024 to Jul 2026: jobs, engagements, grants and
                        every P&L line, posted to the daily ledger
  October 2026          1 to 6 October (as at 2pm on 6 Oct): what has actually
                        happened so far. Incomplete.

The business grows the way a real one does: trades adds maintenance contracts
and technicians, call-outs peak with summer air-con, prices rise in July 2025;
services wins and loses retainers and projects; the not-for-profit's older
grants finish as new ones start, donations peak in June and December, and a
gala runs each September.

Used by warehouse.py (daily tables) and drivers.py (supporting tables).
"""

import random
from datetime import date, timedelta

import data_status as ds
import financial_model as fm
import tax_payroll as tp
from ids import callout_no, contract_no
from warehouse import allocate, days, key, pattern, spread, wdays, working

HIST = [f"{y}-{m:02d}" for y, m in [(2024, 10), (2024, 11), (2024, 12)] + [(2025, k) for k in range(1, 13)] + [(2026, k) for k in range(1, 8)]]
OCT = "2026-10"
AS_AT = ds.AS_AT.date()                       # 6 Oct 2026
MODEL_MONTHS = ["2026-05", "2026-06", "2026-07"]  # the model already has these months' trades jobs (for debtors)
SUBURBS = ["Albion", "Ashgrove", "Aspley", "Bulimba", "Capalaba", "Carindale", "Chermside", "Coorparoo", "Darra", "Everton Park",
           "Fortitude Valley", "Hamilton", "Indooroopilly", "Kedron", "Logan Central", "Milton", "Mitchelton", "Morningside",
           "Mount Gravatt", "Newstead", "Northgate", "Paddington", "Red Hill", "Rocklea", "Salisbury", "Sunnybank", "Taringa",
           "Toowong", "Wacol", "West End", "Windsor", "Wynnum"]
INSTALL_TYPES = [("switchboard upgrade", 0.42, 0.10), ("LED lighting", 0.36, 0.0), ("solar and battery", 0.50, 0.11),
                 ("air-con install", 0.40, 0.07), ("EV chargers", 0.37, 0.0), ("data cabling", 0.28, 0.12),
                 ("office fit-out wiring", 0.33, 0.06)]
SITES = ["warehouse", "office", "house", "cafe", "clinic", "school", "townhouses", "factory", "gym", "shop"]


def idx(mo):
    return (HIST + ["2026-08", "2026-09", OCT]).index(mo)


def month_days_to_date(mo):
    """Every day of the month, or only up to today for October."""
    return [d for d in days(mo) if mo != OCT or d <= AS_AT]


def season(mo, table):
    return table.get(int(mo[5:]), 1.0)


# ======================================================================= TRADES

CONTRACT_START = {i: "2024-10" for i in range(9)} | {9: "2025-02", 10: "2025-06", 11: "2025-10", 12: "2026-02", 13: "2026-06"}
CALLOUT_SEASON = {12: 1.30, 1: 1.40, 2: 1.30, 11: 1.15, 3: 1.05, 6: 0.85, 7: 0.85, 8: 0.95}


def trades_techs(mo):
    # sized to the work: technicians' time on jobs stays in a believable range (about 55% to 85%) every month
    return 6 if mo < "2026-01" else 7


def trades_jobs(m):
    """Jobs for Oct 2024 to Apr 2026 (May to Sep come from the model) and October to date."""
    rng = random.Random(1310)
    jobs, n_inst = [], 2300
    for mo in [x for x in HIST if x not in MODEL_MONTHS] + [OCT]:
        start, i = fm.month_start(mo), idx(mo)
        price = 0.96 if mo < "2025-07" else 1.0          # 4% price rise from July 2025
        for c, (cust, fee, hrs, mat) in enumerate(m["contracts"]):
            if mo < CONTRACT_START[c]:
                continue
            jobs.append(dict(month=mo, job=contract_no(c), type="Maintenance contract", description=cust,
                             revenue=round(fee * price / 10) * 10, materials=mat, subcontractors=0, hours=hrs,
                             invoice_date=start, days_to_pay=m["contract_pay_days"] + rng.choice([-5, 0, 0, 3, 8])))
        n_i = rng.choice([3, 4, 4, 5, 5, 6]) if mo != OCT else 1
        for k in range(n_i):
            kind, mat_share, sub_share = rng.choice(INSTALL_TYPES)
            rev = round(rng.uniform(8000, 44000) * (0.72 + 0.28 * i / 24) / 100) * 100
            margin_noise = rng.uniform(-0.12, 0.08)
            mat_ = round(rev * (mat_share + margin_noise / 2) / 100) * 100
            sub_ = round(rev * sub_share / 100) * 100
            hrs = round(rev / rng.uniform(230, 300) * 2) / 2
            rev = round(rev * fm.INSTALL_PRICE / 100) * 100   # the price: costs above come from the base
            day = 2 if mo == OCT else rng.randrange(1, 27)
            n_inst += 1
            jobs.append(dict(month=mo, job=f"J-{n_inst}", type="Installation",
                             description=f"{rng.choice(SUBURBS)} {rng.choice(SITES)} {kind}", revenue=rev, materials=mat_,
                             subcontractors=sub_, hours=hrs, invoice_date=start + timedelta(days=day - 1),
                             days_to_pay=rng.choice([14, 21, 30, 30, 45])))
        n_c = round(46 * season(mo, CALLOUT_SEASON) * (0.88 + 0.12 * i / 24))
        for k in range(n_c):
            hrs = rng.choice([1, 1.5, 2, 2, 2.5, 3, 3, 4])
            mat_ = rng.randrange(20, 240, 10)
            d = start + timedelta(days=rng.randrange(0, 28))
            if mo == OCT and d > AS_AT:
                continue                                   # hasn't happened yet
            rev_ = round(hrs * m["callout_rate"] * price + mat_ * m["materials_markup"])
            mrev = fm.half_up(mat_ * m["materials_markup"])      # materials charged: cost + the mark-up
            jobs.append(dict(month=mo, job=callout_no(mo, k), type="Call-out", description=f"Call-out {callout_no(mo, k)}",
                             revenue=rev_, labour_revenue=rev_ - mrev, materials_revenue=mrev, materials=mat_,
                             subcontractors=0, hours=hrs, invoice_date=d, days_to_pay=rng.choice([0, 0, 0, 2, 7, 7, 14, 30])))
    for j in jobs:
        j.setdefault("labour_revenue", None)      # only call-outs bill time and materials separately
        j.setdefault("materials_revenue", None)
        j["paid_date"] = tp.next_banking_day(j["invoice_date"] + timedelta(days=j["days_to_pay"]))   # money moves on banking days
        j["labour_cost"] = fm.half_up(j["hours"] * m["tech_cost_rate"])
        j["gross_profit"] = j["revenue"] - j["materials"] - j["subcontractors"] - j["labour_cost"]
        j["gst"] = tp.gst_on(j["revenue"])
        j["amount"] = j["revenue"] + j["gst"]     # the invoice, incl. GST
    return jobs


def trades_lines(m, mo):
    """Every non-job P&L line for a month (full month; October is cut to date when posted)."""
    i = idx(mo)
    grow = 0.86 + 0.14 * i / 24
    t = trades_techs(mo)
    office = 14600 if mo < "2025-07" else 21900
    lines = {"Technician wages (incl. on-costs)": -fm.loaded_wages(t, len(wdays(mo)), m["tech_cost_rate"]), "Office and admin wages": -office,
             "Marketing": -round(7600 * (0.85 + 0.25 * season(mo, {9: 1.1, 10: 1.1, 2: 1.1, 12: 0.7, 1: 0.8})) / 100) * 100,
             "Vehicles and fuel": -round(7900 * t / 7 / 100) * 100, "Rent and occupancy": -(6400 if mo < "2025-07" else 7000),
             "Insurance": -(2700 if mo < "2025-07" else 3000), "IT and software": -round(2300 * grow / 100) * 100,
             "Other overheads": -round(3600 * grow / 100) * 100, "Depreciation": -round(3500 + 900 * i / 24, -2),
             "Interest": -round(1450 - 350 * i / 24, -1)}
    return lines


def trades_new_customers(mo):
    rng = random.Random(f"nc-{mo}")
    return round(36 * (0.88 + 0.18 * idx(mo) / 24) * season(mo, {12: 1.2, 1: 1.25, 2: 1.15, 7: 0.85})) + rng.randint(-3, 3)


# ===================================================================== SERVICES

# history engagements: [code, type, name, rate or fee, first month, last month, hours a month, contractors a month]
SERVICES_HISTORY = [
    ["R-095", "Retainer", "Retail chain reporting", 6100, "2024-10", "2025-06", 30, 0],
    ["R-102", "Retainer", "Construction firm finance", 10400, "2024-10", "2026-07", 55, 0],
    ["R-105", "Retainer", "Dental group reporting", 7500, "2025-03", "2026-07", 42, 0],
    ["R-108", "Retainer", "Agribusiness CFO support", 13200, "2025-11", "2026-07", 66, 0],
    ["R-110", "Retainer", "Hospitality payroll", 4600, "2026-06", "2026-07", 34, 0],
    ["E-198", "Project", "Month-end process redesign, distributor", 175, "2024-10", "2025-02", 100, 0],
    ["E-203", "Project", "Cash flow model, childcare group", 175, "2024-10", "2024-12", 80, 0],
    ["E-201", "Project", "Inventory costing review, wholesaler", 175, "2024-10", "2025-01", 90, 1500],
    ["E-205", "Project", "Budget model, aged care provider", 180, "2024-11", "2025-03", 70, 0],
    ["E-214", "Project", "ERP data migration, engineering firm", 185, "2025-02", "2025-07", 140, 3800],
    ["E-226", "Project", "Pricing review, food manufacturer", 195, "2025-05", "2025-09", 85, 0],
    ["E-233", "Project", "Board pack redesign, sports club", 175, "2025-08", "2025-11", 60, 0],
    ["E-241", "Project", "Cost-to-serve model, freight company", 200, "2025-10", "2026-03", 110, 2400],
    ["E-252", "Project", "Forecasting tool, builder", 195, "2026-01", "2026-05", 95, 0],
    ["E-260", "Project", "Systems review, accounting practice", 185, "2026-03", "2026-06", 75, 1200],
    ["E-311", "Project", "Logistics systems rollout", 195, "2026-06", "2026-07", 150, 3600],
    ["E-316", "Project", "Distributor cost-to-serve", 200, "2026-06", "2026-07", 70, 0],
    ["E-320", "Project", "Manufacturer process mapping", 185, "2026-07", "2026-07", 60, 1500],
]
COURSES = [("Budgeting workshop", 7000, 20), ("Excel for managers", 9700, 30), ("Power BI basics", 5100, 14),
           ("Cash flow for owners", 5700, 16), ("Reading your P&L", 4300, 12)]


def services_consultants(mo):
    # sized to the work: billable hours never exceed the hours the consultants have
    return 5 if mo < "2026-03" else 6


def services_engagements(m):
    rng = random.Random(4242)
    rows, invoices = [], []
    for mo in HIST + [OCT]:
        start = fm.month_start(mo)
        to_date = 3 / 22 if mo == OCT else 1.0          # 3 of October's 22 working days have happened
        live = [e for e in SERVICES_HISTORY if e[4] <= mo <= e[5]] if mo != OCT else \
            [[c[0], c[1], c[2], c[3], OCT, OCT, {"E-311": 200, "E-314": 90, "E-318": 70, "E-320": 110}.get(c[0], {"R-102": 56, "R-105": 42, "R-108": 68, "R-110": 34}.get(c[0], 0)), 0]
             for c in m["engagements"] if c[0] in ("E-311", "E-314", "E-318", "E-320", "R-102", "R-105", "R-108", "R-110")]
        for code, typ, name, rate, _, _, hrs, contr in live:
            h = round(hrs * (1.6 if typ == "Project" and mo != OCT else 1.0) * rng.uniform(0.85, 1.15) * to_date)
            if typ == "Project":
                revenue, billed = h * rate, (h * rate if (mo != OCT and rng.random() < 0.5) else 0)
            else:
                revenue = billed = rate                     # retainers invoiced on the 1st, in full
            c_ = round(contr * rng.uniform(0.8, 1.2) * to_date / 100) * 100
            rows.append(dict(month=mo, code=code, type=typ, description=name, hours=h, revenue=revenue, billed=billed,
                             contractors=c_, allocated_cost=h * m["cost_rate"], contribution=revenue - c_ - h * m["cost_rate"]))
        courses = rng.sample(COURSES, rng.choice([1, 1, 2])) if mo != OCT else []
        for n, (cname, fee, hrs) in enumerate(courses):
            code = f"T-{mo[2:4]}{mo[5:]}{n}"
            rows.append(dict(month=mo, code=code, type="Training", description=cname, hours=hrs, revenue=fee, billed=fee,
                             contractors=900 if hrs >= 20 else 0, allocated_cost=hrs * m["cost_rate"],
                             contribution=fee - (900 if hrs >= 20 else 0) - hrs * m["cost_rate"]))
    for x in rows:
        if x["billed"]:
            d = fm.month_start(x["month"]) + timedelta(days=(0 if x["type"] == "Retainer" else 26 if x["month"] != OCT else 0))
            pay = 14 if x["type"] == "Retainer" else 30
            invoices.append({"invoice": f"INV-{x['month'][2:4]}{x['month'][5:]}{x['code']}", "code": x["code"], "ex_gst": x["billed"],
                             "gst": tp.gst_on(x["billed"]), "amount": tp.with_gst(x["billed"]),
                             "invoice_date": d, "paid_date": tp.next_banking_day(d + timedelta(days=pay + rng.choice([-3, 0, 0, 5, 12])))})
    return rows, invoices


def services_lines(m, mo):
    i = idx(mo)
    grow = 0.85 + 0.15 * i / 24
    return {"Consultant salaries (incl. on-costs)": -fm.loaded_wages(services_consultants(mo), len(wdays(mo)), m["cost_rate"]),
            "Management and admin wages": -(18000 if mo < "2025-07" else 24000),
            "Marketing and business development": -round(5800 * grow / 100) * 100,
            "Rent and occupancy": -(7200 if mo < "2025-07" else 8000), "IT and software": -round(4500 * grow / 100) * 100,
            "Professional indemnity insurance": -(2300 if mo < "2025-07" else 2500), "Travel": -round(2000 * grow / 100) * 100,
            "Other overheads": -round(3300 * grow / 100) * 100, "Depreciation": -round(1700 + 300 * i / 24, -2),
            "Interest": -round(300 - 60 * i / 24, -1)}


def services_new_clients(mo):
    return random.Random(f"ncl-{mo}").choice([1, 2, 2, 3, 3, 4])


# ========================================================================== NFP

# grants that finished before the current six (code, short, program, funder, total, start, end)
NFP_PAST_GRANTS = [
    ["G-091", "Youth (2023)", "Youth outreach (2023-25 round)", "State Department of Families", 456000, date(2023, 7, 1), date(2025, 6, 30)],
    ["G-093", "Relief", "Emergency relief", "Federal community grant", 288000, date(2024, 1, 1), date(2025, 12, 31)],
    ["G-095", "Housing (2025)", "Housing support (2025)", "State Housing Program", 336000, date(2025, 1, 1), date(2025, 12, 31)],
    ["G-097", "Meals (2025)", "Community meals (2025-26)", "Local council community grant", 44000, date(2025, 7, 1), date(2026, 6, 30)],
]
DONATION_SEASON = {6: 2.4, 12: 1.6, 11: 1.15, 1: 0.8, 7: 0.85}


def grant_months(start, end):
    out, d = [], start
    while d <= end:
        out.append(d.strftime("%Y-%m"))
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def nfp_grant_spend(mo):
    """{grant code: spend} for a history month or October to date (current grants' history comes from the model)."""
    out = {}
    rng = random.Random(f"g-{mo}")
    for code, _, _, _, total, s, e in NFP_PAST_GRANTS:
        ms = grant_months(s, e)
        if mo in ms:
            out[code] = round(total / len(ms) * rng.uniform(0.85, 1.15) / 100) * 100
    return out


def nfp_lines(m, mo, grant_spend):
    i = idx(mo)
    grow = 0.9 + 0.1 * i / 24
    gi = sum(grant_spend.values())
    gw = fm.half_up(gi * m["grant_wage_share"])
    gala = mo.endswith("-09")
    xmas = mo.endswith("-12")
    lines = {"Donations": round(17000 * grow * season(mo, DONATION_SEASON) / 100) * 100,
             "Fundraising events": (36800 if gala else 6200 if xmas else 0),
             "Program fees": round(24500 * grow / 100) * 100, "Interest": round(1300 * grow, -1),
             "Grant-funded program wages": -gw, "Grant-funded program costs": -(gi - gw),
             "Program delivery wages (untied)": -round(12500 * grow / 100) * 100,
             "Program costs (untied)": -round(5200 * grow / 100) * 100,
             "Grant writing and reporting": -(6500 if mo < "2025-07" else 7100),
             "Donor campaigns": -round(2200 * season(mo, {6: 2.5, 12: 2.0, 11: 1.4}) / 100) * 100,
             "Event costs": -(15200 if gala else 2600 if xmas else 0),
             "Administration wages": -(16800 if mo < "2025-07" else 18300), "Occupancy": -(9400 if mo < "2025-07" else 10000),
             "Other administration": -round(7400 * grow / 100) * 100, "Depreciation": -round(2600 + 300 * i / 24, -2)}
    return lines


# ===================================================================== build

def gala_date(mo):
    """Third Saturday of September."""
    d = date(int(mo[:4]), 9, 15)
    while d.weekday() != 5:
        d += timedelta(days=1)
    return d


def post_month(org, mo, lines, post):
    """Post a month's non-transaction lines on their usual days (October only up to today)."""
    for label, amt in lines.items():
        amt = int(round(amt))                 # whole dollars
        if not amt:
            continue
        dates = pattern(org, label, mo)
        if label in ("Fundraising events", "Event costs") and mo.endswith("-09"):
            dates = [gala_date(mo)]
        elif label in ("Depreciation", "Interest") or label.startswith("Income tax"):
            dates = [ds.month_end(mo)]
        for d, a in spread(amt, dates):
            if mo != OCT or d <= AS_AT:
                post(d, org, label, a)


def build(res):
    """Returns the extra rows for every daily table, plus fact_line_month and the history drivers."""
    out = {"gl": [], "jobs": [], "eng": [], "eng_inv": [], "ts": [], "grant_month": [], "past_grants": [], "cash": [], "bal": [],
           "lines": [], "drivers": [], "extra_accounts": []}
    def post(d, org, label, amount, job=None, eng=None, grant=None):
        if amount:
            out["gl"].append((d, org, label, amount, job, eng, grant))

    # ---------------- trades
    T, tout = fm.TRADES, res["trades"]["out"]
    rev_line = {"Maintenance contract": f"Maintenance contracts ({len(T['contracts'])})", "Installation": "Installations (jobs)", "Call-out": "Call-outs and repairs"}
    hist_jobs = trades_jobs(T)
    model_hist = [j for j in tout["jobs"] if j["month"] in MODEL_MONTHS]
    all_hist = hist_jobs + model_hist
    out["jobs"] = hist_jobs
    for mo in HIST + [OCT]:
        mj = [j for j in all_hist if j["month"] == mo]
        for j in mj:
            if mo == OCT and j["invoice_date"] > AS_AT:
                continue
            if j["type"] == "Call-out":
                post(j["invoice_date"], "trades", "Call-outs: technician time", j["labour_revenue"], job=j["job"])
                post(j["invoice_date"], "trades", "Call-outs: materials charged", j["materials_revenue"], job=j["job"])
            else:
                post(j["invoice_date"], "trades", rev_line[j["type"]], j["revenue"], job=j["job"])
            post(j["invoice_date"], "trades", "Materials", -j["materials"], job=j["job"])
            post(j["invoice_date"], "trades", "Subcontractors", -j["subcontractors"], job=j["job"])
        lines = trades_lines(T, mo)
        if mo != OCT:          # income tax on the month's profit (October's is provided at month end)
            rev = sum(j["revenue"] - j["materials"] - j["subcontractors"] for j in mj) + sum(lines.values())
            lines[f"Income tax provision ({T['tax_rate']}%)"] = -fm.half_up(rev * T["tax_rate"] / 100)
        post_month("trades", mo, lines, post)
        out["drivers"] += [["trades", mo, "Technicians", trades_techs(mo), "people"],
                           ["trades", mo, "New customers (first job ever)", trades_new_customers(mo) if mo != OCT else None, "customers"],
                           ["trades", mo, "Marketing spend", -lines["Marketing"], "$"]]
        # timesheets (history months and October to date)
        for j in mj:
            if j["type"] == "Call-out":
                if mo != OCT or j["invoice_date"] <= AS_AT:
                    out["ts"].append((j["invoice_date"], "trades", j["job"], None, j["hours"]))
                continue
            ds_ = [d for d in wdays(mo) if (j["type"] == "Maintenance contract" or d <= j["invoice_date"])]
            if j["type"] == "Installation":
                if mo == OCT:     # the five working days before the invoice reach back into September (locked): only October's share is posted
                    ds_ = [d for d in wdays("2026-09") + wdays(mo) if d <= j["invoice_date"]]
                ds_ = ds_[-5:] or wdays(mo)[:1]
            for d, h in zip(ds_, allocate(int(j["hours"] * 2), [1] * len(ds_))):
                if h and (mo != OCT or (d.strftime("%Y-%m") == OCT and d <= AS_AT)):
                    out["ts"].append((d, "trades", j["job"], None, h / 2))

    # ---------------- services
    S = fm.SERVICES
    eng, inv = services_engagements(S)
    out["eng"], out["eng_inv"] = eng, inv
    for mo in HIST + [OCT]:
        me = [x for x in eng if x["month"] == mo]
        for x in me:
            if x["type"] == "Project":
                ds_ = [d for d in wdays(mo) if mo != OCT or d <= AS_AT]
                for d, a in zip(ds_, allocate(x["revenue"], [1] * len(ds_))):
                    post(d, "services", "Projects (hours worked)", a, eng=x["code"])
            elif x["type"] == "Retainer":
                post(fm.month_start(mo), "services", "Retainers", x["revenue"], eng=x["code"])
            else:
                post(wdays(mo)[min(10, len(wdays(mo)) - 1)], "services", "Training", x["revenue"], eng=x["code"])
            if x["contractors"]:
                cd = wdays(mo)[-1] if mo != OCT else AS_AT
                post(cd, "services", "Contractors", -x["contractors"], eng=x["code"])
            ds_ = [d for d in wdays(mo) if mo != OCT or d <= AS_AT]
            for d, h in zip(ds_, allocate(int(x["hours"] * 2), [1] * len(ds_))):
                if h:
                    out["ts"].append((d, "services", None, x["code"], h / 2))
        lines = services_lines(S, mo)
        if mo != OCT:
            pbt = sum(x["revenue"] - x["contractors"] for x in me) + sum(lines.values())
            lines[f"Income tax provision ({S['tax_rate']}%)"] = -fm.half_up(pbt * S["tax_rate"] / 100)
        post_month("services", mo, lines, post)
        out["drivers"] += [["services", mo, "Consultants", services_consultants(mo), "people"],
                           ["services", mo, "New clients", services_new_clients(mo) if mo != OCT else None, "clients"]]

    # ---------------- not-for-profit
    N, nout = fm.NFP, res["nfp"]["out"]
    cur = {gr["code"]: {x["month"]: x["spend"] for x in gr["monthly"]} for gr in nout["grants"]}
    gname = {g[0]: g[2] for g in N["grants"]} | {g[0]: g[2] for g in NFP_PAST_GRANTS}
    out["past_grants"] = NFP_PAST_GRANTS
    for g in NFP_PAST_GRANTS:
        out["extra_accounts"].append(("nfp", f"{g[2]} grant"))
    for mo in HIST + [OCT]:
        spend = nfp_grant_spend(mo)
        for code, months in cur.items():
            if mo in months:
                spend[code] = months[mo]
            elif mo == OCT:
                gr = next(g for g in N["grants"] if g[0] == code)
                if gr[6] >= date(2026, 10, 1):
                    spend[code] = gr[10]                   # October planned at September's rate, posted to date only
        for code, amt in spend.items():
            label = f"{gname[code]} grant"
            for d, a in spread(amt, wdays(mo)):
                if mo != OCT or d <= AS_AT:
                    post(d, "nfp", label, a, grant=code)
                    if mo == OCT:
                        out["grant_month"].append((code, OCT, a))
            if mo != OCT:
                out["grant_month"].append((code, mo, amt))
        lines = nfp_lines(N, mo, spend)
        post_month("nfp", mo, lines, post)

    # ---------------- October cash and balances (1 to 6 October)
    for org in ("trades", "services", "nfp"):
        o = res[org]["out"]
        bs_sep = o["bs"]["2026-09"]
        if org == "trades":
            invoices = o["jobs"] + [j for j in hist_jobs if j["month"] == OCT and j["invoice_date"] <= AS_AT]
        elif org == "services":
            invoices = o["invoices"] + [i for i in inv if i["invoice_date"].strftime("%Y-%m") == OCT]
        else:
            invoices = []
        pay_run = o["payroll"]["cash"]                     # net pay + super on pay day (PAYG withheld goes with the BAS)
        flows = {}
        def flow(d, label, amt):
            if amt:
                out["cash"].append((d, org, label, amt))
                flows[d] = flows.get(d, 0) + amt
        for d in month_days_to_date(OCT):
            if org != "nfp":
                flow(d, "Receipts from customers (invoices paid)", sum(i["amount"] for i in invoices if i["paid_date"] == d))
            if d in tp.pay_days_in(OCT):
                flow(d, "Payments to employees", -pay_run)
        if org == "nfp":                                   # money moves on banking days only; program fees include GST
            don = round(17000 * season(OCT, DONATION_SEASON) / 100) * 100
            for d, a in spread(don, wdays(OCT)):
                if d <= AS_AT:
                    flow(d, "Donations and fundraising received", a)
            for d, a in spread(tp.with_gst(26000), wdays(OCT)):
                if d <= AS_AT:
                    flow(d, "Program fees received", a)
        cash = bs_sep["cash"]
        for d in month_days_to_date(OCT):
            cash += flows.get(d, 0)
            debt = fm.unpaid_at(invoices, d) if invoices else None
            out["bal"].append((d, org, cash, debt))
            if cash < 0:
                raise SystemExit(f"history: {org} cash goes negative on {d}")

    # ---------------- revenue, cost and margin by line, by month (24 months + October to date)
    status = {mo: ds.month_status(mo)[0] for mo in HIST + ["2026-08", "2026-09", OCT]}
    for mo in HIST + ["2026-08", "2026-09", OCT]:
        tj = [j for j in (tout["jobs"] if mo in ("2026-05", "2026-06", "2026-07", "2026-08", "2026-09") else hist_jobs)
              if j["month"] == mo and (mo != OCT or j["invoice_date"] <= AS_AT)]
        for typ, label in (("Maintenance contract", "Maintenance contracts"), ("Installation", "Installations"), ("Call-out", "Call-outs and repairs")):
            js = [j for j in tj if j["type"] == typ]
            r_, c_ = sum(j["revenue"] for j in js), sum(j["materials"] + j["subcontractors"] + j["labour_cost"] for j in js)
            out["lines"].append(["trades", mo, status[mo], label, len(js), r_, c_, r_ - c_])
        se = res["services"]["out"]["engagements"] if mo in ("2026-08", "2026-09") else eng
        me = [x for x in se if x["month"] == mo]
        for typ, label in (("Project", "Projects"), ("Retainer", "Retainers"), ("Training", "Training")):
            xs = [x for x in me if x["type"] == typ]
            r_, c_ = sum(x["revenue"] for x in xs), sum(x["contractors"] + x["allocated_cost"] for x in xs)
            out["lines"].append(["services", mo, status[mo], label, len(xs), r_, c_, r_ - c_])
    return out


def nfp_line_month(gl_by_month_label, months):
    """NFP income by source with the cost of raising it (from the posted ledger)."""
    rows = []
    for mo in months:
        g = gl_by_month_label.get(mo, {})
        grants = sum(v for k, v in g.items() if k.endswith(" grant"))
        for label, amt, cost in (("Grants", grants, g.get("Grant writing and reporting", 0)),
                                 ("Donations", g.get("Donations", 0), g.get("Donor campaigns", 0)),
                                 ("Fundraising events", g.get("Fundraising events", 0), g.get("Event costs", 0)),
                                 ("Program fees", g.get("Program fees", 0), 0)):
            rows.append(["nfp", mo, ds.month_status(mo)[0], label, None, amt, -cost, amt + cost])
    return rows
