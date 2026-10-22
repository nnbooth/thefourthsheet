#!/usr/bin/env python3
"""
financial_model.py — month-end sample model behind the home-page dashboard.

MONTH-END REPORTING, BUILT FROM THE TRANSACTIONS UP. We report September 2026
(the last closed month) against the PRIOR MONTH, August 2026. Three invented
organisations, each modelled at the most granular level:

  trades    SME: field/trade services. Every JOB (maintenance contract,
            installation, call-out) with its own revenue, materials,
            subcontractors, technician hours, invoice date and payment date.
  services  SME: professional services. Every client ENGAGEMENT (projects
            billed on milestones, monthly retainers, training) with hours,
            rates, contractors, billing, work in progress and invoices.
  nfp       Not-for-profit: community services charity. Every GRANT (funder,
            program, period, instalments, monthly spend against budget),
            plus donations, events and program fees.

The P&L, balance sheet and cash flow are ADDED UP FROM those records, in
whole dollars, so everything ties. run_checks() proves it before anything is
published (subtotals, balance sheet balances, cash ties, profit rolls into
equity, job/engagement/grant detail ties to the statements, debtors equal the
unpaid invoices, unspent grants equal grants received less income recognised).

Australian financial year: FY2027 runs 1 July 2026 to 30 June 2027. GST,
BAS, pay runs, PAYG withholding and super follow tax_payroll.py: the P&L is
GST-exclusive (an accrual), invoices, bills and cash include GST, and money
only moves on banking days. All data is invented.

Used by tools/3_publish_site/publish_dashboard.py (via tools/1_build_data/sample_data.py).
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import random
import data_status as ds
import tax_payroll as tp
from ids import callout_no, contract_no
from datetime import date, timedelta

PERIODS = ["2026-09", "2026-08"]           # display order: this month, prior month
COLUMNS = ["Sep 2026", "Aug 2026"]
ALL_MONTHS = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]   # generated history (for invoices)
MONTH_END = {"2026-05": date(2026, 5, 31), "2026-06": date(2026, 6, 30), "2026-07": date(2026, 7, 31),
             "2026-08": date(2026, 8, 31), "2026-09": date(2026, 9, 30)}
WORKING_DAYS = {"2026-08": 20, "2026-09": 22}   # Brisbane: Ekka show holiday Wed 12 Aug 2026
HOURS_PER_DAY = 7.6


def loaded_wages(people, working_days, rate):
    """A month's wages incl. on-costs: every available hour (people x working days x 7.6 h) at the loaded hourly cost.
    So the costing rate = wages / available hours, and time charged to the work + time not charged = wages, exactly."""
    return half_up(people * working_days * HOURS_PER_DAY * rate)


def ym(d):
    return d.strftime("%Y-%m")


def month_start(m):
    y, mm = map(int, m.split("-"))
    return date(y, mm, 1)


def prev_month(m):
    i = ALL_MONTHS.index(m)
    return ALL_MONTHS[i - 1]


def half_up(x):
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def round_half_up(v, dp=0):
    """The one rounding rule for every number shown (site, PDF, Excel, slides): halves round away from zero
    (112.5 -> 113, 12.25 -> 12.3), worked in decimal so binary float error can't tip a half the wrong way."""
    from decimal import Decimal, ROUND_HALF_UP
    q = Decimal(repr(float(v))).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP)
    return int(q) if dp <= 0 else float(q)


def split(total, weights):
    """Split an integer total in proportion to weights; the parts always add back exactly."""
    tw = sum(weights)
    raw = [total * w / tw for w in weights]
    parts = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - parts[i], reverse=True)[: total - sum(parts)]:
        parts[i] += 1
    return parts


def row(label, level, values, note=None):
    """level: heading (no numbers) / detail / subtotal / total / key. values = [Sep, Aug]."""
    return {"label": label, "level": level, "values": values, "note": note}


def per(fn):
    return [fn(m) for m in PERIODS]


def unpaid_at(invoices, d):
    return sum(i["amount"] for i in invoices if i["invoice_date"] <= d and (i["paid_date"] is None or i["paid_date"] > d))


def paid_in(invoices, m):
    return sum(i["amount"] for i in invoices if i["paid_date"] is not None and ym(i["paid_date"]) == m)


# ======================================================================= TRADES

TRADES = {
    "name": "SME · trades", "long_name": "Sample Electrical & Air Pty Ltd",
    "about": "An electrical and air-conditioning contractor in Brisbane: maintenance contracts, installations and call-outs. 7 technicians, 3 office staff.",
    # tech_cost_rate: what an hour of a technician costs, wages and all on-costs. Wages are set from it each month
    # (technicians x working days x 7.6 h x rate, see loaded_wages), so time charged to jobs + time not charged = wages.
    "technicians": 7, "tech_cost_rate": 68,
    "callout_rate": 163, "materials_markup": 1.3, "target_margin": 35,
    "contracts": [  # [customer, monthly fee, technician hours a month, materials a month]
        ["Riverside Apartments (strata)", 3600, 18, 60], ["Southbank cafe group", 2000, 10, 40], ["Milton office tower", 4700, 24, 90],
        ["Ashgrove aged care", 4050, 20, 80], ["Newstead gym", 1800, 9, 30], ["Kangaroo Point townhouses", 2700, 14, 50],
        ["Rocklea factory", 4350, 22, 110], ["Wynnum medical centre", 2450, 12, 40], ["Bulimba school", 3150, 16, 60],
        ["Fortitude Valley hotel", 3800, 19, 70], ["Chermside retail centre", 4600, 23, 100], ["West End brewery", 2900, 15, 50],
        ["Carindale vet clinic", 1900, 9, 30], ["Wacol logistics depot", 3350, 17, 70],
    ],
    "contract_pay_days": 30,
    "installs": {  # [job id, job name, completion day, revenue, materials, subcontractors, tech hours, days to pay]
        "2026-08": [["J-2588", "Rocklea factory switchboard", 7, 43100, 15600, 4800, 92, 30],
                    ["J-2591", "Ashgrove hall LED lighting", 14, 23900, 8100, 0, 70, 30],
                    ["J-2594", "Newstead gym air-con", 19, 18800, 6700, 1200, 44, 21],
                    ["J-2597", "Wynnum house solar", 24, 22000, 9400, 2200, 36, 14],
                    ["J-2599", "Valley office cabling", 28, 15000, 3900, 1100, 48, 30]],
        "2026-09": [["J-2604", "Wacol warehouse switchboard", 4, 52400, 22900, 7400, 150, 45],
                    ["J-2607", "Milton office LED lighting", 9, 20800, 6900, 0, 64, 30],
                    ["J-2611", "Carindale solar and battery", 15, 30700, 13800, 3100, 46, 14],
                    ["J-2615", "West End cafe air-con", 18, 14400, 5100, 900, 38, 21],
                    ["J-2618", "Bulimba EV chargers", 23, 11000, 3600, 0, 26, 30],
                    ["J-2620", "Chermside clinic cabling", 29, 17000, 4300, 1800, 52, 30]],
    },
    "callouts": {"2026-05": 55, "2026-06": 57, "2026-07": 54, "2026-08": 58, "2026-09": 64},
    "history_installs": {"2026-05": 4, "2026-06": 5, "2026-07": 4},
    "opex": {"Office and admin wages": {"2026-08": 21900, "2026-09": 21900},
             "Marketing": {"2026-08": 8400, "2026-09": 7600},
             "Vehicles and fuel": {"2026-08": 7900, "2026-09": 8300},
             "Rent and occupancy": {"2026-08": 7000, "2026-09": 7000},
             "Insurance": {"2026-08": 3000, "2026-09": 3000},
             "IT and software": {"2026-08": 2300, "2026-09": 2300},
             "Other overheads": {"2026-08": 3600, "2026-09": 3900}},
    "new_customers": {"2026-08": 41, "2026-09": 47},
    "depreciation": {"2026-08": 4300, "2026-09": 4500}, "interest": {"2026-08": 1100, "2026-09": 1080},
    "loan_repaid": {"2026-08": 5000, "2026-09": 5000}, "capex": {"2026-08": 0, "2026-09": 12000},
    "provision_change": {"2026-08": 1100, "2026-09": 900}, "tax_rate": 25,
    "opening": {"cash": 88000, "stock": 66000, "prepayments": 21000, "fixed_assets": 252000,
                "provisions": 104000, "tax_payable": 31500, "loan": 105000, "share_capital": 10000},
}


TRADES["tech_wages"] = {mo: loaded_wages(TRADES["technicians"], WORKING_DAYS[mo], TRADES["tech_cost_rate"]) for mo in PERIODS}


INSTALL_PRICE = 1.12   # generated installations: price over the base the costs come from (prices set for technicians at $68/hour)


def trades_jobs(m):
    """Every job and invoice for May-Sep (seeded, so it's identical every run)."""
    rng = random.Random(2604)
    jobs = []
    for month in ALL_MONTHS:
        start = month_start(month)
        for i, (cust, fee, hrs, mat) in enumerate(m["contracts"]):
            jobs.append({"month": month, "job": contract_no(i), "type": "Maintenance contract", "description": cust,
                         "revenue": fee, "materials": mat, "subcontractors": 0, "hours": hrs,
                         "invoice_date": start, "days_to_pay": m["contract_pay_days"] + rng.choice([-5, 0, 0, 3, 8])})
        if month in m["installs"]:
            for j, desc, day, rev, mat, sub, hrs, pay in m["installs"][month]:
                jobs.append({"month": month, "job": j, "type": "Installation", "description": desc, "revenue": rev, "materials": mat,
                             "subcontractors": sub, "hours": hrs, "invoice_date": start + timedelta(days=day - 1), "days_to_pay": pay})
        else:
            for k in range(m["history_installs"][month]):
                rev = rng.randrange(9000, 42000, 100)                  # costs are worked out from this; the price is INSTALL_PRICE above it
                jobs.append({"month": month, "job": f"J-{2500 + ALL_MONTHS.index(month) * 20 + k}", "type": "Installation",
                             "description": f"Installation J-{2500 + ALL_MONTHS.index(month) * 20 + k}", "revenue": round(rev * INSTALL_PRICE / 100) * 100, "materials": int(rev * 0.38) // 100 * 100,
                             "subcontractors": int(rev * 0.08) // 100 * 100, "hours": rev // 260,
                             "invoice_date": start + timedelta(days=rng.randrange(0, 27)), "days_to_pay": rng.choice([14, 21, 30, 30, 45])})
        for k in range(m["callouts"][month]):
            hrs = rng.choice([1, 1.5, 2, 2, 2.5, 3, 3, 4])
            mat = rng.randrange(20, 240, 10)
            rev = half_up(hrs * m["callout_rate"] + mat * m["materials_markup"])
            mat_rev = half_up(mat * m["materials_markup"])          # materials charged: cost + the mark-up
            jobs.append({"month": month, "job": callout_no(month, k), "type": "Call-out", "description": f"Call-out {callout_no(month, k)}",
                         "revenue": rev, "labour_revenue": rev - mat_rev, "materials_revenue": mat_rev, "materials": mat, "subcontractors": 0, "hours": hrs,
                         "invoice_date": start + timedelta(days=rng.randrange(0, 28)), "days_to_pay": rng.choice([0, 0, 0, 2, 7, 7, 14, 30])})
    for j in jobs:
        j.setdefault("labour_revenue", None)      # only call-outs bill time and materials separately
        j.setdefault("materials_revenue", None)
        j["paid_date"] = tp.next_banking_day(j["invoice_date"] + timedelta(days=j["days_to_pay"]))   # money moves on banking days
        j["labour_cost"] = half_up(j["hours"] * m["tech_cost_rate"])
        j["gross_profit"] = j["revenue"] - j["materials"] - j["subcontractors"] - j["labour_cost"]
        j["gst"] = tp.gst_on(j["revenue"])
        j["amount"] = j["revenue"] + j["gst"]     # the invoice, incl. GST: what the customer owes and pays
    return jobs


def taxable(label):
    """P&L lines that carry GST on the bill: everything bought in except wages, depreciation, interest and income tax."""
    l = label.lower()
    return not ("wages" in l or "salar" in l or l in ("depreciation", "interest") or l.startswith("income tax"))


def sme_payroll(org, wages_by_month, leave):
    """The fortnightly pay run for FY2027: a 26th of the year's gross wages (wage cost less super and leave)."""
    annual = sum(tp.gross_from_cost(wages_by_month(mo), leave) for mo in tp.fy_months())
    run = tp.pay_run(annual, org)
    run["payroll_tax"] = tp.payroll_tax_check(org, annual)
    if run["payroll_tax"]:
        raise SystemExit(f"{org}: wages are over the Queensland payroll tax threshold; the model doesn't include payroll tax")
    return run


def opening_payroll(run):
    """Wages, super and PAYG owed at 31 July: wages since the last pay run, and PAYG withheld from July's pay runs."""
    july = tp.pay_days(date(2026, 7, 1), MONTH_END["2026-07"])
    last = max(july)
    since = sum(1 for k in range(1, (MONTH_END["2026-07"] - last).days + 1) if ds.working(last + timedelta(days=k)))
    owed = half_up(run["gross"] * since / 10)
    return {"wages_owed": owed, "super_payable": half_up(owed * tp.SUPER_RATE), "paygw_payable": run["payg"] * len(july)}


def month_payroll(run, prev, wage_cost, leave, mo):
    """A month's pay runs against the wage cost: cash paid on pay days (net pay + super), what's still owed, and PAYG for the ATO."""
    gross = tp.gross_from_cost(wage_cost, leave)
    sup = wage_cost - leave - gross
    n = len(tp.pay_days_in(mo))
    return {"gross": gross, "super": sup, "runs": n, "pay_emp": n * run["cash"],
            "wages_owed": prev["wages_owed"] + gross - n * run["gross"],
            "super_payable": prev["super_payable"] + sup - n * run["super"],
            "paygw_payable": prev["paygw_payable"] + n * run["payg"]}


def trades(m):
    import history                                  # July's overheads (for July's GST) come from the history ledger
    jobs = trades_jobs(m)
    inv = jobs
    purchases = {mo: sum(j["materials"] + j["subcontractors"] for j in jobs if j["month"] == mo) for mo in ALL_MONTHS}
    tax_opex = lambda mo: sum(v[mo] for k, v in m["opex"].items() if taxable(k))
    leave = half_up(sum(m["provision_change"].values()) / len(m["provision_change"]))
    office = m["opex"]["Office and admin wages"]
    wage_cost = lambda mo: loaded_wages(m["technicians"], tp.working_days(mo), m["tech_cost_rate"]) + office.get(mo, office["2026-09"])
    run = sme_payroll("trades", wage_cost, leave)
    o = m["opening"]
    jul = history.trades_lines(m, "2026-07")
    jul_gst = (sum(j["gst"] for j in jobs if j["month"] == "2026-07") - tp.gst_on(purchases["2026-07"])
               - tp.gst_on(-sum(v for k, v in jul.items() if taxable(k))))
    bs = {"2026-07": {**o, "debtors": unpaid_at(inv, MONTH_END["2026-07"]), "creditors": tp.with_gst(purchases["2026-07"]),
                      "gst_payable": jul_gst, **opening_payroll(run)}}
    b0 = bs["2026-07"]
    b0["retained"] = (o["cash"] + b0["debtors"] + o["stock"] + o["prepayments"] + o["fixed_assets"]
                      - b0["creditors"] - o["provisions"] - o["tax_payable"] - o["loan"] - o["share_capital"]
                      - b0["gst_payable"] - b0["wages_owed"] - b0["super_payable"] - b0["paygw_payable"])
    r = {}
    for mo in ["2026-08", "2026-09"]:
        mj = [j for j in jobs if j["month"] == mo]
        by = lambda t, k: sum(j[k] for j in mj if j["type"] == t)
        rev = {t: by(t, "revenue") for t in ["Maintenance contract", "Installation", "Call-out"]}
        rev["Call-out time"] = sum(j["labour_revenue"] for j in mj if j["type"] == "Call-out")
        rev["Call-out materials"] = sum(j["materials_revenue"] for j in mj if j["type"] == "Call-out")
        revenue = sum(rev[t] for t in ["Maintenance contract", "Installation", "Call-out"])
        mat, sub = sum(j["materials"] for j in mj), sum(j["subcontractors"] for j in mj)
        techw = m["tech_wages"][mo]
        cos = mat + sub + techw
        gp = revenue - cos
        opex = {k: v[mo] for k, v in m["opex"].items()}
        ebitda = gp - sum(opex.values())
        pbt = ebitda - m["depreciation"][mo] - m["interest"][mo]
        tax = half_up(pbt * m["tax_rate"] / 100)
        npat = pbt - tax
        prev = bs[prev_month(mo)]
        pay = month_payroll(run, prev, techw + opex["Office and admin wages"], m["provision_change"][mo], mo)
        sales_gst = sum(j["gst"] for j in mj)
        purchase_gst = tp.gst_on(purchases[mo]) + tp.gst_on(tax_opex(mo)) + tp.gst_on(m["capex"][mo])
        receipts = paid_in(inv, mo)
        pay_sup = prev["creditors"] + tp.with_gst(tax_opex(mo))        # last month's bills + this month's overheads, incl. GST
        capex_paid = tp.with_gst(m["capex"][mo])
        ato = 0                                                       # the July to September BAS is due 28 October
        operating = receipts - pay_sup - pay["pay_emp"] - m["interest"][mo] - ato
        bs[mo] = {"cash": prev["cash"] + operating - capex_paid - m["loan_repaid"][mo],
                  "debtors": unpaid_at(inv, MONTH_END[mo]), "stock": prev["stock"], "prepayments": prev["prepayments"],
                  "fixed_assets": prev["fixed_assets"] + m["capex"][mo] - m["depreciation"][mo],
                  "creditors": tp.with_gst(purchases[mo]), "provisions": prev["provisions"] + m["provision_change"][mo],
                  "tax_payable": prev["tax_payable"] + tax, "loan": prev["loan"] - m["loan_repaid"][mo],
                  "gst_payable": prev["gst_payable"] + sales_gst - purchase_gst,
                  "wages_owed": pay["wages_owed"], "super_payable": pay["super_payable"], "paygw_payable": pay["paygw_payable"],
                  "share_capital": prev["share_capital"], "retained": prev["retained"] + npat}
        hours = sum(j["hours"] for j in mj)
        avail = m["technicians"] * WORKING_DAYS[mo] * HOURS_PER_DAY
        r[mo] = dict(rev=rev, revenue=revenue, mat=mat, sub=sub, techw=techw, cos=cos, gp=gp, opex=opex, ebitda=ebitda, pbt=pbt,
                     tax=tax, npat=npat, receipts=receipts, pay_sup=pay_sup, pay_emp=pay["pay_emp"], operating=operating, ato=ato,
                     capex_paid=capex_paid, sales_gst=sales_gst, purchase_gst=purchase_gst, pay=pay,
                     jobs_gp=sum(j["gross_profit"] for j in mj), allocated=sum(j["labour_cost"] for j in mj),
                     hours=hours, available=avail)

    pnl = [row("Revenue", "heading", None),
           row(f"Maintenance contracts ({len(m['contracts'])})", "detail", per(lambda mo: r[mo]["rev"]["Maintenance contract"])),
           row("Installations (jobs)", "detail", per(lambda mo: r[mo]["rev"]["Installation"])),
           row("Call-outs: technician time", "detail", per(lambda mo: r[mo]["rev"]["Call-out time"])),
           row("Call-outs: materials charged", "detail", per(lambda mo: r[mo]["rev"]["Call-out materials"])),
           row("Total revenue", "subtotal", per(lambda mo: r[mo]["revenue"])),
           row("Cost of sales", "heading", None),
           row("Materials", "detail", per(lambda mo: -r[mo]["mat"])),
           row("Subcontractors", "detail", per(lambda mo: -r[mo]["sub"])),
           row("Technician wages (incl. on-costs)", "detail", per(lambda mo: -r[mo]["techw"])),
           row("Total cost of sales", "subtotal", per(lambda mo: -r[mo]["cos"])),
           row("Gross profit", "total", per(lambda mo: r[mo]["gp"])),
           row("Operating expenses", "heading", None)]
    for k in m["opex"]:
        pnl.append(row(k, "detail", per(lambda mo, k=k: -r[mo]["opex"][k])))
    pnl += [row("Total operating expenses", "subtotal", per(lambda mo: -sum(r[mo]["opex"].values()))),
            row("EBITDA", "total", per(lambda mo: r[mo]["ebitda"])),
            row("Depreciation", "subtotal", per(lambda mo: -m["depreciation"][mo])),
            row("Interest", "subtotal", per(lambda mo: -m["interest"][mo])),
            row("Profit before tax", "total", per(lambda mo: r[mo]["pbt"])),
            row(f"Income tax provision ({m['tax_rate']}%)", "subtotal", per(lambda mo: -r[mo]["tax"])),
            row("Net profit after tax", "key", per(lambda mo: r[mo]["npat"]))]
    bsr, cfr = sme_bs_cf(bs, r, m, "Materials on hand", "Vehicles and equipment", "Purchase of vehicles and equipment",
                         "Payments to suppliers", "Payments to employees")
    return dict(jobs=jobs, r=r, bs=bs, pnl=pnl, bsr=bsr, cfr=cfr, payroll=run)


SME_LIABILITIES = ("creditors", "wages_owed", "super_payable", "paygw_payable", "gst_payable", "provisions", "tax_payable")


def sme_bs_cf(bs, r, m, stock_label, fa_label, capex_label, sup_label, emp_label):
    def ca(mo): b = bs[mo]; return b["cash"] + b["debtors"] + b["stock"] + b["prepayments"]
    def cl(mo): b = bs[mo]; return sum(b[k] for k in SME_LIABILITIES)
    bsr = [row("Current assets", "heading", None),
           row("Cash at bank", "detail", per(lambda mo: bs[mo]["cash"])),
           row("Trade debtors (unpaid invoices)", "detail", per(lambda mo: bs[mo]["debtors"]), note="Invoices include GST."),
           row(stock_label, "detail", per(lambda mo: bs[mo]["stock"])),
           row("Prepayments", "detail", per(lambda mo: bs[mo]["prepayments"])),
           row("Total current assets", "subtotal", per(ca)),
           row(fa_label, "subtotal", per(lambda mo: bs[mo]["fixed_assets"])),
           row("Total assets", "total", per(lambda mo: ca(mo) + bs[mo]["fixed_assets"])),
           row("Current liabilities", "heading", None),
           row("Trade creditors (bills due next month)", "detail", per(lambda mo: bs[mo]["creditors"]), note="Bills include GST."),
           row("Wages owed (since the last pay run)", "detail", per(lambda mo: bs[mo]["wages_owed"])),
           row("Super payable", "detail", per(lambda mo: bs[mo]["super_payable"])),
           row("PAYG withholding payable", "detail", per(lambda mo: bs[mo]["paygw_payable"]), note="Paid with the BAS."),
           row("GST payable (net)", "detail", per(lambda mo: bs[mo]["gst_payable"]), note="GST on sales less GST credits, quarter to date. Paid with the BAS."),
           row("Employee leave provisions", "detail", per(lambda mo: bs[mo]["provisions"])),
           row("Income tax payable", "detail", per(lambda mo: bs[mo]["tax_payable"])),
           row("Total current liabilities", "subtotal", per(cl)),
           row("Equipment finance", "subtotal", per(lambda mo: bs[mo]["loan"])),
           row("Total liabilities", "total", per(lambda mo: cl(mo) + bs[mo]["loan"])),
           row("Net assets", "key", per(lambda mo: ca(mo) + bs[mo]["fixed_assets"] - cl(mo) - bs[mo]["loan"])),
           row("Equity", "heading", None),
           row("Share capital", "detail", per(lambda mo: bs[mo]["share_capital"])),
           row("Retained earnings", "detail", per(lambda mo: bs[mo]["retained"])),
           row("Total equity", "key", per(lambda mo: bs[mo]["share_capital"] + bs[mo]["retained"]))]
    cfr = [row("Operating activities", "heading", None),
           row("Receipts from customers (invoices paid)", "detail", per(lambda mo: r[mo]["receipts"]), note="Incl. GST."),
           row(sup_label, "detail", per(lambda mo: -r[mo]["pay_sup"]), note="Incl. GST."),
           row(emp_label, "detail", per(lambda mo: -r[mo]["pay_emp"]), note="Net pay and super, on each fortnightly pay day."),
           row("Interest paid", "detail", per(lambda mo: -m["interest"][mo])),
           row("GST, PAYG and income tax paid (BAS)", "detail", per(lambda mo: -r[mo]["ato"]), note="The July to September BAS is due 28 October."),
           row("Net cash from operating activities", "subtotal", per(lambda mo: r[mo]["operating"])),
           row("Investing activities", "heading", None),
           row(capex_label, "detail", per(lambda mo: -r[mo]["capex_paid"]), note="Incl. GST."),
           row("Net cash from investing activities", "subtotal", per(lambda mo: -r[mo]["capex_paid"])),
           row("Financing activities", "heading", None),
           row("Equipment finance repaid", "detail", per(lambda mo: -m["loan_repaid"][mo])),
           row("Net cash from financing activities", "subtotal", per(lambda mo: -m["loan_repaid"][mo])),
           row("Net change in cash", "total", per(lambda mo: r[mo]["operating"] - r[mo]["capex_paid"] - m["loan_repaid"][mo])),
           row("Cash at start of month", "subtotal", per(lambda mo: bs[prev_month(mo)]["cash"])),
           row("Cash at end of month", "key", per(lambda mo: bs[mo]["cash"]))]
    return bsr, cfr


# ===================================================================== SERVICES

SERVICES = {
    "name": "SME · services", "long_name": "Sample Advisory Pty Ltd",
    "about": "A Brisbane finance and operations consultancy: projects billed on milestones, monthly retainers and training. 6 consultants, 3 management and admin staff.",
    # cost_rate: what an hour of a consultant costs, salary and all on-costs; salaries are set from it (see loaded_wages)
    "consultants": 6, "cost_rate": 60, "target_margin": 40,
    # [code, type, client / description, rate or fee, days to pay]
    "engagements": [
        ["E-311", "Project", "Logistics systems rollout", 195, 30],
        ["E-314", "Project", "Retail pricing review", 210, 30],
        ["E-316", "Project", "Distributor cost-to-serve", 200, 45],
        ["E-318", "Project", "Health charity board pack", 180, 30],
        ["E-320", "Project", "Manufacturer process mapping", 185, 45],
        ["R-102", "Retainer", "Construction firm finance", 10400, 14],
        ["R-105", "Retainer", "Dental group reporting", 7500, 14],
        ["R-108", "Retainer", "Agribusiness CFO support", 13200, 30],
        ["R-110", "Retainer", "Hospitality payroll", 4600, 14],
        ["T-205", "Training", "Budgeting workshop", 7000, 30],
        ["T-207", "Training", "Excel for managers", 9700, 30],
        ["T-209", "Training", "Power BI basics", 5100, 30],
    ],
    # month -> code -> [hours, amount billed (projects only), contractors]
    "activity": {
        "2026-08": {"E-311": [180, 0, 4200], "E-314": [60, 0, 0], "E-316": [88, 17600, 0], "E-320": [100, 0, 1800],
                    "R-102": [56, 0, 0], "R-105": [42, 0, 0], "R-108": [68, 0, 0], "R-110": [48, 0, 0], "T-205": [20, 0, 900]},
        # Below the 40% target on purpose: payroll retainer scope creep (hours up, same fee), the logistics rollout
        # leaning on contractors, and the Excel course's venue and co-trainer.
        "2026-09": {"E-311": [210, 33400, 11200], "E-314": [96, 0, 0], "E-318": [64, 11520, 0], "E-320": [120, 26100, 2200],
                    "R-102": [58, 0, 0], "R-105": [44, 0, 0], "R-108": [70, 0, 0], "R-110": [52, 0, 0],
                    "T-207": [36, 0, 4200], "T-209": [14, 0, 0]},
    },
    "opening_wip": {"E-311": 13200, "E-314": 0, "E-316": 0, "E-318": 0, "E-320": 6600},
    "history_billing": {"2026-05": 130000, "2026-06": 139000, "2026-07": 133000},   # earlier months' invoices (for debtors)
    "history_contractors": {"2026-07": 3900},
    "opex": {"Management and admin wages": {"2026-08": 24000, "2026-09": 24000},
             "Marketing and business development": {"2026-08": 6500, "2026-09": 5800},
             "Rent and occupancy": {"2026-08": 8000, "2026-09": 8000},
             "IT and software": {"2026-08": 4500, "2026-09": 4500},
             "Professional indemnity insurance": {"2026-08": 2500, "2026-09": 2500},
             "Travel": {"2026-08": 2600, "2026-09": 1800},
             "Other overheads": {"2026-08": 3300, "2026-09": 3300}},
    "new_clients": {"2026-08": 3, "2026-09": 4},
    "depreciation": {"2026-08": 2000, "2026-09": 2000}, "interest": {"2026-08": 250, "2026-09": 240},
    "loan_repaid": {"2026-08": 1700, "2026-09": 1700}, "capex": {"2026-08": 0, "2026-09": 3200},
    "provision_change": {"2026-08": 700, "2026-09": 600}, "tax_rate": 25,
    "opening": {"cash": 158000, "prepayments": 15000, "fixed_assets": 61000,
                "provisions": 121000, "tax_payable": 48500, "loan": 18000, "share_capital": 20000},
}


SERVICES["salaries"] = {mo: loaded_wages(SERVICES["consultants"], WORKING_DAYS[mo], SERVICES["cost_rate"]) for mo in PERIODS}


def services_engagements(m):
    rng = random.Random(311)
    eng = {e[0]: e for e in m["engagements"]}
    rows, invoices = [], []
    for mo in ["2026-08", "2026-09"]:
        for code, (hours, billed, contractors) in m["activity"][mo].items():
            _, typ, desc, rate, pay = eng[code]
            if typ == "Project":
                revenue, bill = hours * rate, billed
            else:  # retainers and training: billed as delivered
                revenue = bill = rate
            rows.append({"month": mo, "code": code, "type": typ, "description": desc, "hours": hours,
                         "revenue": revenue, "billed": bill, "contractors": contractors,
                         "allocated_cost": hours * m["cost_rate"],
                         "contribution": revenue - contractors - hours * m["cost_rate"]})
            if bill:
                d = month_start(mo) + timedelta(days=(27 if typ == "Project" else rng.randrange(0, 20)))
                invoices.append({"invoice": f"INV-{mo[5:]}{code}", "code": code, "ex_gst": bill, "gst": tp.gst_on(bill), "amount": tp.with_gst(bill),
                                 "invoice_date": d, "paid_date": tp.next_banking_day(d + timedelta(days=pay + rng.choice([-3, 0, 0, 5, 12])))})
    for mo, total in m["history_billing"].items():  # earlier months, in a few invoices each
        parts = [total // 4] * 3 + [total - 3 * (total // 4)]
        for k, amt in enumerate(parts):
            d = month_start(mo) + timedelta(days=6 + 6 * k)
            invoices.append({"invoice": f"INV-{mo[5:]}H{k}", "code": "earlier", "ex_gst": amt, "gst": tp.gst_on(amt), "amount": tp.with_gst(amt),
                             "invoice_date": d, "paid_date": tp.next_banking_day(d + timedelta(days=rng.choice([14, 30, 30, 45, 52])))})
    return rows, invoices


def services(m):
    import history                                  # July's overheads (for July's GST) come from the history ledger
    rows, invoices = services_engagements(m)
    o = m["opening"]
    wip0 = sum(m["opening_wip"].values())
    tax_opex = lambda mo: sum(v[mo] for k, v in m["opex"].items() if taxable(k))
    leave = half_up(sum(m["provision_change"].values()) / len(m["provision_change"]))
    mgmt = m["opex"]["Management and admin wages"]
    wage_cost = lambda mo: loaded_wages(m["consultants"], tp.working_days(mo), m["cost_rate"]) + mgmt.get(mo, mgmt["2026-09"])
    run = sme_payroll("services", wage_cost, leave)
    billed_in = lambda mo, k: sum(i[k] for i in invoices if ym(i["invoice_date"]) == mo)
    jul = history.services_lines(m, "2026-07")
    jul_gst = (billed_in("2026-07", "gst") - tp.gst_on(m["history_contractors"]["2026-07"])
               - tp.gst_on(-sum(v for k, v in jul.items() if taxable(k))))
    bs = {"2026-07": {**o, "debtors": unpaid_at(invoices, MONTH_END["2026-07"]), "stock": wip0,
                      "creditors": tp.with_gst(m["history_contractors"]["2026-07"]), "gst_payable": jul_gst, **opening_payroll(run)}}
    b0 = bs["2026-07"]
    b0["retained"] = (o["cash"] + b0["debtors"] + wip0 + o["prepayments"] + o["fixed_assets"]
                      - b0["creditors"] - o["provisions"] - o["tax_payable"] - o["loan"] - o["share_capital"]
                      - b0["gst_payable"] - b0["wages_owed"] - b0["super_payable"] - b0["paygw_payable"])
    wip = dict(m["opening_wip"])
    r = {}
    for mo in ["2026-08", "2026-09"]:
        mr = [x for x in rows if x["month"] == mo]
        rev = {t: sum(x["revenue"] for x in mr if x["type"] == t) for t in ["Project", "Retainer", "Training"]}
        revenue = sum(rev.values())
        contractors = sum(x["contractors"] for x in mr)
        sal = m["salaries"][mo]
        cos = sal + contractors
        gp = revenue - cos
        opex = {k: v[mo] for k, v in m["opex"].items()}
        ebitda = gp - sum(opex.values())
        pbt = ebitda - m["depreciation"][mo] - m["interest"][mo]
        tax = half_up(pbt * m["tax_rate"] / 100)
        npat = pbt - tax
        for x in mr:
            if x["type"] == "Project":
                wip[x["code"]] = wip.get(x["code"], 0) + x["revenue"] - x["billed"]
        prev = bs[prev_month(mo)]
        pay = month_payroll(run, prev, sal + opex["Management and admin wages"], m["provision_change"][mo], mo)
        sales_gst = billed_in(mo, "gst")
        purchase_gst = tp.gst_on(contractors) + tp.gst_on(tax_opex(mo)) + tp.gst_on(m["capex"][mo])
        receipts = paid_in(invoices, mo)
        pay_sup = prev["creditors"] + tp.with_gst(tax_opex(mo))      # last month's contractor bills + this month's overheads, incl. GST
        capex_paid = tp.with_gst(m["capex"][mo])
        ato = 0                                                     # the July to September BAS is due 28 October
        operating = receipts - pay_sup - pay["pay_emp"] - m["interest"][mo] - ato
        bs[mo] = {"cash": prev["cash"] + operating - capex_paid - m["loan_repaid"][mo],
                  "debtors": unpaid_at(invoices, MONTH_END[mo]), "stock": sum(wip.values()), "prepayments": prev["prepayments"],
                  "fixed_assets": prev["fixed_assets"] + m["capex"][mo] - m["depreciation"][mo],
                  "creditors": tp.with_gst(contractors), "provisions": prev["provisions"] + m["provision_change"][mo],
                  "tax_payable": prev["tax_payable"] + tax, "loan": prev["loan"] - m["loan_repaid"][mo],
                  "gst_payable": prev["gst_payable"] + sales_gst - purchase_gst,
                  "wages_owed": pay["wages_owed"], "super_payable": pay["super_payable"], "paygw_payable": pay["paygw_payable"],
                  "share_capital": prev["share_capital"], "retained": prev["retained"] + npat}
        hours = sum(x["hours"] for x in mr)
        r[mo] = dict(rev=rev, revenue=revenue, contractors=contractors, sal=sal, cos=cos, gp=gp, opex=opex, ebitda=ebitda,
                     pbt=pbt, tax=tax, npat=npat, receipts=receipts, pay_sup=pay_sup, pay_emp=pay["pay_emp"], operating=operating,
                     ato=ato, capex_paid=capex_paid, sales_gst=sales_gst, purchase_gst=purchase_gst, pay=pay,
                     hours=hours, available=m["consultants"] * WORKING_DAYS[mo] * HOURS_PER_DAY,
                     contribution=sum(x["contribution"] for x in mr), allocated=sum(x["allocated_cost"] for x in mr),
                     wip=dict(wip))
    pnl = [row("Revenue", "heading", None),
           row("Projects (hours worked)", "detail", per(lambda mo: r[mo]["rev"]["Project"])),
           row("Retainers", "detail", per(lambda mo: r[mo]["rev"]["Retainer"])),
           row("Training", "detail", per(lambda mo: r[mo]["rev"]["Training"])),
           row("Total revenue", "subtotal", per(lambda mo: r[mo]["revenue"])),
           row("Cost of sales", "heading", None),
           row("Consultant salaries (incl. on-costs)", "detail", per(lambda mo: -r[mo]["sal"])),
           row("Contractors", "detail", per(lambda mo: -r[mo]["contractors"])),
           row("Total cost of sales", "subtotal", per(lambda mo: -r[mo]["cos"])),
           row("Gross profit", "total", per(lambda mo: r[mo]["gp"])),
           row("Operating expenses", "heading", None)]
    for k in m["opex"]:
        pnl.append(row(k, "detail", per(lambda mo, k=k: -r[mo]["opex"][k])))
    pnl += [row("Total operating expenses", "subtotal", per(lambda mo: -sum(r[mo]["opex"].values()))),
            row("EBITDA", "total", per(lambda mo: r[mo]["ebitda"])),
            row("Depreciation", "subtotal", per(lambda mo: -m["depreciation"][mo])),
            row("Interest", "subtotal", per(lambda mo: -m["interest"][mo])),
            row("Profit before tax", "total", per(lambda mo: r[mo]["pbt"])),
            row(f"Income tax provision ({m['tax_rate']}%)", "subtotal", per(lambda mo: -r[mo]["tax"])),
            row("Net profit after tax", "key", per(lambda mo: r[mo]["npat"]))]
    bsr, cfr = sme_bs_cf(bs, r, m, "Work in progress (unbilled project time)", "Office equipment", "Purchase of equipment",
                         "Payments to contractors and suppliers", "Payments to employees")
    return dict(engagements=rows, invoices=invoices, r=r, bs=bs, pnl=pnl, bsr=bsr, cfr=cfr, payroll=run)


# ========================================================================== NFP

NFP = {
    "name": "Not-for-profit", "long_name": "Sample Community Services Ltd",
    "about": "A Brisbane community services charity funded by six grants, donations, events and program fees. About 18 staff. Registered charity, income-tax exempt.",
    # [code, short name, program, funder, total, start, end, instalments [(date, amount)], received to 31 Jul, recognised to 31 Jul, spend Aug, spend Sep]
    "grants": [
        ["G-101", "Youth", "Youth outreach", "State Department of Families", 480000, date(2025, 7, 1), date(2027, 6, 30),
         [(date(2025, 7, 15), 60000), (date(2025, 10, 15), 60000), (date(2026, 1, 15), 60000), (date(2026, 4, 15), 60000), (date(2026, 7, 15), 60000), (date(2026, 10, 15), 60000)],
         262000, 21500, 22800],
        ["G-102", "Housing", "Housing support", "State Housing Program", 360000, date(2026, 1, 1), date(2026, 12, 31),
         [(date(2026, 1, 8), 180000), (date(2026, 7, 6), 180000)], 196000, 30500, 31200],
        ["G-103", "Meals", "Community meals", "Local council community grant", 48000, date(2026, 7, 1), date(2027, 6, 30),
         [(date(2026, 7, 10), 48000)], 3600, 4100, 4300],
        ["G-104", "Digital", "Digital literacy", "Philanthropic foundation", 90000, date(2025, 10, 1), date(2027, 3, 31),
         [(date(2025, 10, 20), 45000), (date(2026, 10, 20), 45000)], 49500, 5200, 4900],
        ["G-105", "Mind", "Mental health first aid", "Federal health program", 120000, date(2026, 4, 1), date(2027, 3, 31),
         [(date(2026, 4, 9), 60000), (date(2026, 10, 9), 60000)], 37000, 9400, 10800],
        ["G-106", "Volunteer", "Volunteer coordinator", "State volunteering grant", 36000, date(2026, 3, 1), date(2027, 2, 28),
         [(date(2026, 3, 3), 36000)], 15000, 3000, 3000],
    ],
    "grant_wage_share": 0.75,
    "untied_program": {"Program delivery wages (untied)": {"2026-08": 14000, "2026-09": 14500},
                       "Program costs (untied)": {"2026-08": 5500, "2026-09": 6100}},
    "income": {"Donations": {"2026-08": 18400, "2026-09": 27900},
               "Fundraising events": {"2026-08": 0, "2026-09": 41600},
               "Program fees": {"2026-08": 26800, "2026-09": 28300},
               "Interest": {"2026-08": 1450, "2026-09": 1380}},
    "fundraising": {"Grant writing and reporting": {"2026-08": 7100, "2026-09": 7100},
                    "Donor campaigns": {"2026-08": 2200, "2026-09": 5400},
                    "Event costs": {"2026-08": 2400, "2026-09": 16900}},
    "admin": {"Administration wages": {"2026-08": 18300, "2026-09": 18300},
              "Occupancy": {"2026-08": 10000, "2026-09": 10000},
              "Other administration": {"2026-08": 8000, "2026-09": 7600}},
    "depreciation": {"2026-08": 2900, "2026-09": 2900}, "capex": {"2026-08": 0, "2026-09": 0},
    "fees_receivable": {"2026-07": 9100, "2026-08": 9800, "2026-09": 10400},
    "provision_change": {"2026-08": 900, "2026-09": 700},
    "opening": {"cash": 610000, "prepayments": 21000, "fixed_assets": 178000, "payables": 36500, "provisions": 165000},
    "reserves_target_months": 3, "ending_within_months": 6,
}

NFP["grants"] = [gr[:7] + [[(tp.next_banking_day(d), amt) for d, amt in gr[7]]] + gr[8:] for gr in NFP["grants"]]   # banking days

NFP_TAXABLE_COSTS = ("Grant-funded program costs", "Program costs (untied)", "Donor campaigns", "Event costs", "Occupancy", "Other administration")


def nfp(m):
    import history                                  # July's lines (for July's GST) come from the history ledger
    a = m
    g = a["grants"]
    received = lambda gr, d: sum(amt for dt, amt in gr[7] if dt <= d)
    recog = {gr[0]: {"2026-07": gr[8]} for gr in g}
    for gr in g:
        recog[gr[0]]["2026-08"] = gr[8] + gr[9]
        recog[gr[0]]["2026-09"] = gr[8] + gr[9] + gr[10]
    def grant_bal(mo):  # positive = received in advance (liability); negative = spent ahead (receivable)
        return {gr[0]: received(gr, MONTH_END[mo]) - recog[gr[0]][mo] for gr in g}
    def adv(mo): return sum(v for v in grant_bal(mo).values() if v > 0)
    def grec(mo): return -sum(v for v in grant_bal(mo).values() if v < 0)
    grant_rows = []
    hist_rng = random.Random(102)
    for gr in g:
        months = []
        d = gr[5]
        while d <= gr[6]:
            months.append(d.strftime("%Y-%m"))
            d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        budget = dict(zip(months, split(gr[4], [1] * len(months))))      # even monthly budget, adds to the grant
        before = [mo for mo in months if mo < "2026-08"]
        spend = dict(zip(before, split(gr[8], [hist_rng.uniform(0.8, 1.2) for _ in before]))) if before else {}
        spend["2026-08"], spend["2026-09"] = gr[9], gr[10]
        to_date = [mo for mo in months if mo <= "2026-09"]
        budget_to_date = sum(budget[mo] for mo in to_date)
        grant_rows.append({"code": gr[0], "short": gr[1], "program": gr[2], "funder": gr[3], "total": gr[4],
                           "start": gr[5].isoformat(), "end": gr[6].isoformat(),
                           "received_to_date": received(gr, MONTH_END["2026-09"]), "spent_to_date": recog[gr[0]]["2026-09"],
                           "spent_aug": gr[9], "spent_sep": gr[10], "budget_to_date": budget_to_date,
                           "spend_vs_budget_pct": round(100 * recog[gr[0]]["2026-09"] / budget_to_date, 1),
                           "unspent": gr[4] - recog[gr[0]]["2026-09"],
                           "balance_30_sep": grant_bal("2026-09")[gr[0]],
                           "months_left": max(0, (gr[6].year - 2026) * 12 + gr[6].month - 9),
                           "monthly": [{"month": mo, "spend": spend[mo], "budget": budget[mo]} for mo in to_date],
                           "budget_by_month": budget})
    # wages and the pay run: the fortnightly pay run is a 26th of the year's gross wages, on August and September's level
    def month_wages(mo):
        k = 9 if mo == "2026-08" else 10
        gi = sum(gr[k] for gr in g)
        return (half_up(gi * a["grant_wage_share"]) + a["untied_program"]["Program delivery wages (untied)"][mo]
                + a["fundraising"]["Grant writing and reporting"][mo] + a["admin"]["Administration wages"][mo])
    run = tp.pay_run(6 * sum(tp.gross_from_cost(month_wages(mo), a["provision_change"][mo]) for mo in PERIODS), "nfp")
    run["payroll_tax"] = tp.payroll_tax_check("nfp", run["annual_gross"])
    # July's GST (the quarter started 1 July): on grant instalments, program fees and events, less credits on bills
    jul_spend = {gr["code"]: x["spend"] for gr in grant_rows for x in gr["monthly"] if x["month"] == "2026-07"} | history.nfp_grant_spend("2026-07")
    jul = history.nfp_lines(a, "2026-07", jul_spend)
    jul_gst = (tp.gst_on(sum(amt for gr in g for dt, amt in gr[7] if ym(dt) == "2026-07")) + tp.gst_on(jul["Program fees"])
               + tp.gst_on(jul["Fundraising events"]) - tp.gst_on(-sum(jul[k] for k in NFP_TAXABLE_COSTS)))
    o = a["opening"]
    bs = {"2026-07": {**o, "grants_in_advance": adv("2026-07"), "grants_receivable": grec("2026-07"),
                      "fees_receivable": tp.with_gst(a["fees_receivable"]["2026-07"]), "gst_payable": jul_gst, **opening_payroll(run)}}
    b0 = bs["2026-07"]
    b0["accumulated"] = (o["cash"] + b0["fees_receivable"] + b0["grants_receivable"] + o["prepayments"] + o["fixed_assets"]
                         - o["payables"] - b0["grants_in_advance"] - o["provisions"]
                         - b0["gst_payable"] - b0["wages_owed"] - b0["super_payable"] - b0["paygw_payable"])
    r = {}
    for mo in ["2026-08", "2026-09"]:
        k = 9 if mo == "2026-08" else 10
        gspend = {gr[0]: gr[k] for gr in g}
        grant_income = sum(gspend.values())
        other_income = {kk: v[mo] for kk, v in a["income"].items()}
        income = grant_income + sum(other_income.values())
        grant_wages = half_up(grant_income * a["grant_wage_share"])
        grant_costs = grant_income - grant_wages
        untied = {kk: v[mo] for kk, v in a["untied_program"].items()}
        program = grant_income + sum(untied.values())
        fund = {kk: v[mo] for kk, v in a["fundraising"].items()}
        admin = {kk: v[mo] for kk, v in a["admin"].items()}
        expenses = program + sum(fund.values()) + sum(admin.values()) + a["depreciation"][mo]
        surplus = income - expenses
        prev = bs[prev_month(mo)]
        wages = grant_wages + untied["Program delivery wages (untied)"] + fund["Grant writing and reporting"] + admin["Administration wages"]
        nonwage = expenses - a["depreciation"][mo] - wages                      # every bill is taxable (NFP_TAXABLE_COSTS)
        pay = month_payroll(run, prev, wages, a["provision_change"][mo], mo)
        instalments = sum(amt for gr in g for dt, amt in gr[7] if ym(dt) == mo)
        grants_received = tp.with_gst(instalments)
        fees_rec = tp.with_gst(a["fees_receivable"][mo])
        fees_received = tp.with_gst(other_income["Program fees"]) - (fees_rec - prev["fees_receivable"])
        don_received = other_income["Donations"] + tp.with_gst(other_income["Fundraising events"])
        sales_gst = tp.gst_on(instalments) + tp.gst_on(other_income["Program fees"]) + tp.gst_on(other_income["Fundraising events"])
        purchase_gst = tp.gst_on(nonwage) + tp.gst_on(a["capex"][mo])
        pay_sup = prev["payables"]                 # suppliers are paid the following month
        ato = 0                                     # the July to September BAS is due 28 October
        operating = grants_received + don_received + fees_received + other_income["Interest"] - pay_sup - pay["pay_emp"] - ato
        capex_paid = tp.with_gst(a["capex"][mo])
        bs[mo] = {"cash": prev["cash"] + operating - capex_paid, "fees_receivable": fees_rec,
                  "grants_receivable": grec(mo), "prepayments": prev["prepayments"],
                  "fixed_assets": prev["fixed_assets"] + a["capex"][mo] - a["depreciation"][mo],
                  "payables": tp.with_gst(nonwage), "grants_in_advance": adv(mo), "provisions": prev["provisions"] + a["provision_change"][mo],
                  "gst_payable": prev["gst_payable"] + sales_gst - purchase_gst,
                  "wages_owed": pay["wages_owed"], "super_payable": pay["super_payable"], "paygw_payable": pay["paygw_payable"],
                  "accumulated": prev["accumulated"] + surplus}
        r[mo] = dict(gspend=gspend, grant_income=grant_income, other_income=other_income, income=income,
                     grant_wages=grant_wages, grant_costs=grant_costs, untied=untied, program=program, fund=fund, admin=admin,
                     expenses=expenses, surplus=surplus, wages=wages, nonwage=nonwage, grants_received=grants_received,
                     fees_received=fees_received, don_received=don_received, pay_sup=pay_sup, pay_emp=pay["pay_emp"], pay=pay,
                     sales_gst=sales_gst, purchase_gst=purchase_gst, ato=ato, capex_paid=capex_paid,
                     operating=operating, cash_expenses=expenses - a["depreciation"][mo])
    pnl = [row("Income", "heading", None)]
    for gr in g:
        pnl.append(row(f"{gr[2]} grant", "detail", per(lambda mo, c=gr[0]: r[mo]["gspend"][c])))
    for kk in a["income"]:
        pnl.append(row(kk, "detail", per(lambda mo, kk=kk: r[mo]["other_income"][kk])))
    pnl += [row("Total income", "subtotal", per(lambda mo: r[mo]["income"])),
            row("Programs", "heading", None),
            row("Grant-funded program wages", "detail", per(lambda mo: -r[mo]["grant_wages"])),
            row("Grant-funded program costs", "detail", per(lambda mo: -r[mo]["grant_costs"]))]
    for kk in a["untied_program"]:
        pnl.append(row(kk, "detail", per(lambda mo, kk=kk: -r[mo]["untied"][kk])))
    pnl.append(row("Total program spend", "subtotal", per(lambda mo: -r[mo]["program"])))
    for head, key, total in [("Fundraising", "fund", "Total fundraising costs"), ("Administration", "admin", "Total administration")]:
        pnl.append(row(head, "heading", None))
        for kk in a["fundraising" if key == "fund" else "admin"]:
            pnl.append(row(kk, "detail", per(lambda mo, kk=kk, key=key: -r[mo][key][kk])))
        pnl.append(row(total, "subtotal", per(lambda mo, key=key: -sum(r[mo][key].values()))))
    pnl += [row("Depreciation", "subtotal", per(lambda mo: -a["depreciation"][mo])),
            row("Total expenses", "total", per(lambda mo: -r[mo]["expenses"])),
            row("Surplus for the month", "key", per(lambda mo: r[mo]["surplus"]), note="Income-tax exempt charity: no income tax.")]

    LIAB = ("payables", "wages_owed", "super_payable", "paygw_payable", "gst_payable", "grants_in_advance", "provisions")
    def ca(mo): b = bs[mo]; return b["cash"] + b["fees_receivable"] + b["grants_receivable"] + b["prepayments"]
    def cl(mo): b = bs[mo]; return sum(b[k] for k in LIAB)
    bsr = [row("Current assets", "heading", None),
           row("Cash at bank", "detail", per(lambda mo: bs[mo]["cash"])),
           row("Program fees receivable", "detail", per(lambda mo: bs[mo]["fees_receivable"]), note="Incl. GST."),
           row("Grants receivable (spent ahead of instalment)", "detail", per(lambda mo: bs[mo]["grants_receivable"])),
           row("Prepayments", "detail", per(lambda mo: bs[mo]["prepayments"])),
           row("Total current assets", "subtotal", per(ca)),
           row("Vehicles and equipment", "subtotal", per(lambda mo: bs[mo]["fixed_assets"])),
           row("Total assets", "total", per(lambda mo: ca(mo) + bs[mo]["fixed_assets"])),
           row("Current liabilities", "heading", None),
           row("Payables (bills due next month)", "detail", per(lambda mo: bs[mo]["payables"]), note="Bills include GST."),
           row("Wages owed (since the last pay run)", "detail", per(lambda mo: bs[mo]["wages_owed"])),
           row("Super payable", "detail", per(lambda mo: bs[mo]["super_payable"])),
           row("PAYG withholding payable", "detail", per(lambda mo: bs[mo]["paygw_payable"]), note="Paid with the BAS."),
           row("GST payable (net)", "detail", per(lambda mo: bs[mo]["gst_payable"]), note="GST on grants, program fees and events less GST credits, quarter to date. Paid with the BAS."),
           row("Grants received in advance (unspent)", "detail", per(lambda mo: bs[mo]["grants_in_advance"])),
           row("Employee leave provisions", "detail", per(lambda mo: bs[mo]["provisions"])),
           row("Total liabilities", "total", per(cl)),
           row("Net assets", "key", per(lambda mo: ca(mo) + bs[mo]["fixed_assets"] - cl(mo))),
           row("Equity", "heading", None),
           row("Accumulated funds", "key", per(lambda mo: bs[mo]["accumulated"]))]
    cfr = [row("Operating activities", "heading", None),
           row("Grant instalments received", "detail", per(lambda mo: r[mo]["grants_received"]), note="Incl. GST. Next instalments arrive in October."),
           row("Donations and fundraising received", "detail", per(lambda mo: r[mo]["don_received"]), note="Event income incl. GST; donations carry none."),
           row("Program fees received", "detail", per(lambda mo: r[mo]["fees_received"]), note="Incl. GST."),
           row("Interest received", "detail", per(lambda mo: r[mo]["other_income"]["Interest"])),
           row("Payments to suppliers", "detail", per(lambda mo: -r[mo]["pay_sup"]), note="Incl. GST."),
           row("Payments to employees", "detail", per(lambda mo: -r[mo]["pay_emp"]), note="Net pay and super, on each fortnightly pay day."),
           row("GST and PAYG paid (BAS)", "detail", per(lambda mo: -r[mo]["ato"]), note="The July to September BAS is due 28 October."),
           row("Net cash from operating activities", "subtotal", per(lambda mo: r[mo]["operating"])),
           row("Investing activities", "heading", None),
           row("Purchase of vehicles and equipment", "detail", per(lambda mo: -r[mo]["capex_paid"])),
           row("Net cash from investing activities", "subtotal", per(lambda mo: -r[mo]["capex_paid"])),
           row("Net change in cash", "total", per(lambda mo: r[mo]["operating"] - r[mo]["capex_paid"])),
           row("Cash at start of month", "subtotal", per(lambda mo: bs[prev_month(mo)]["cash"])),
           row("Cash at end of month", "key", per(lambda mo: bs[mo]["cash"]))]
    return dict(r=r, bs=bs, pnl=pnl, bsr=bsr, cfr=cfr, grants=grant_rows, grant_bal=grant_bal, payroll=run)

# ============================================================ the fourth sheet
# Three headline numbers (this month vs last month) and one chart that drills
# into the detail. The full detail lists go to the Excel/PDF downloads and CSVs.

def chg(cur, prev, fmt, better="up"):
    if fmt(cur) == fmt(prev):          # the same once rounded: say so, not a red arrow next to two equal numbers
        return f"■ same as Aug ({fmt(prev)})", ""
    up = cur > prev
    good = (up and better == "up") or (not up and better == "down")
    arrow = "▲" if up else ("▼" if cur < prev else "■")
    return f"{arrow} from {fmt(prev)} in Aug", "good" if (good and cur != prev) else ("" if cur == prev else "bad")


def money(v):
    """$1,234, with negatives in accounting brackets: ($1,234)."""
    v = half_up(v)
    return f"(${-v:,})" if v < 0 else f"${v:,}"


# ---- number formats: ONE rule per kind, used on the site, in PDFs and in Excel
# money: whole dollars, negatives in brackets · pct: 1 decimal place (stored as a
# fraction) · hours: 1 dp · int: whole · months: 1 dp · cents: whole cents
FMT = {
    "money": lambda v: money(v),
    "pct": lambda v: f"({round_half_up(-v * 100, 1):.1f}%)" if v < 0 else f"{round_half_up(v * 100, 1):.1f}%",
    "hours": lambda v: f"({round_half_up(-v, 1):,.1f} h)" if v < 0 else f"{round_half_up(v, 1):,.1f} h",
    "int": lambda v: f"{round_half_up(v):,}",
    "months": lambda v: f"({round_half_up(-v, 1):.1f} months)" if v < 0 else f"{round_half_up(v, 1):.1f} months",
    "cents": lambda v: f"({-half_up(v)}¢)" if v < 0 else f"{half_up(v)}¢",
    "date": lambda v: v,
    "text": lambda v: v,
}


def inp(label, kind, values):
    """An input row (data): one value per column."""
    return {"label": label, "kind": kind, "values": list(values), "calc": None}


def calc(label, kind, expr):
    """A calculated row: expr uses r0, r1… for earlier rows, e.g. 'r4/r0'. Becomes an Excel formula."""
    return {"label": label, "kind": kind, "values": None, "calc": expr}


def support(title, formula, rows, note=None, series=None, cols=("Sep 2026", "Aug 2026")):
    """The workings behind a number. Calculated rows are worked out here (for the site and
    PDF) and written as formulas in Excel, from the same expressions."""
    import re
    def ev(expr, c):
        try:
            return eval(re.sub(r"r(\d+)", lambda m: f"rows[{m.group(1)}]['values'][{c}]", expr), {}, {"rows": rows})
        except (ZeroDivisionError, TypeError):
            return None          # nothing to divide by (e.g. no revenue that month): shown as "–", and IFERROR in Excel
    for r_ in rows:
        if r_["calc"]:
            r_["values"] = [ev(r_["calc"], c) for c in range(len(cols))]
    shown = [[r_["label"], *["–" if v is None else FMT[r_["kind"]](v) for v in r_["values"]]] + ([""] if len(cols) == 1 else []) for r_ in rows]
    return {"title": title, "formula": formula, "head": ["", *cols], "rows": shown, "note": note, "series": series,
            "xl": {"cols": list(cols), "rows": rows}}


def fourth_trades(m, out):
    r = out["r"]
    S = lambda f: [f(mo) for mo in PERIODS]
    installs = sorted([j for j in out["jobs"] if j["month"] == "2026-09" and j["type"] == "Installation"],
                      key=lambda j: -j["gross_profit"] / j["revenue"])     # bars sorted by value
    s_gm = support("Gross margin (P&L)", "Gross profit ÷ revenue. All technician wages and on-costs included; overheads are not.", [
        inp("Revenue (every job invoiced in the month)", "money", S(lambda mo: r[mo]["revenue"])),
        inp("Materials", "money", S(lambda mo: -r[mo]["mat"])), inp("Subcontractors", "money", S(lambda mo: -r[mo]["sub"])),
        inp("Technician wages", "money", S(lambda mo: -r[mo]["techw"])),
        calc("Gross profit", "money", "r0+r1+r2+r3"), calc("Gross margin (P&L)", "pct", "r4/r0")],
        "Gross margin is before overheads (office wages, marketing, vehicles, rent and so on): it is not profit. Wages include their on-costs: super (12%) and leave as it's earned. No payroll tax: wages are under Queensland's $1.3 million threshold. Technicians are on salary, so a quiet month for jobs lowers gross margin even if every job is priced well.")
    s_cac = support("Cost to win a customer", "Marketing spend ÷ new customers", [
        inp("Marketing spend", "money", S(lambda mo: m["opex"]["Marketing"][mo])),
        inp("New customers (first job ever)", "int", S(lambda mo: m["new_customers"][mo])),
        calc("Cost per new customer", "money", "r0/r1")])
    s_ut = support("Technician time on jobs", "Hours charged to jobs ÷ hours available", [
        inp("Hours charged to jobs (timesheets)", "hours", S(lambda mo: r[mo]["hours"])),
        inp("Technicians", "int", S(lambda mo: m["technicians"])), inp("Working days", "int", S(lambda mo: WORKING_DAYS[mo])),
        inp("Hours per day", "hours", S(lambda mo: HOURS_PER_DAY)),
        calc("Hours available", "hours", "r1*r2*r3"), calc("Time on jobs", "pct", "r0/r4")],
        "August had 20 working days: 21 weekdays, less the Ekka People's Day holiday (Wed 12 Aug). The rest is travel, training, quoting and waiting time.")
    kp = lambda sp, i=-1: sp["xl"]["rows"][i]["values"]
    gm, cac, util = kp(s_gm), kp(s_cac), kp(s_ut)
    k1, c1 = chg(gm[0], gm[1], FMT["pct"])
    k2, c2 = chg(cac[0], cac[1], FMT["money"], "down")
    k3, c3 = chg(util[0], util[1], FMT["pct"])
    details = [support(j["description"], "Job gross margin ÷ revenue for this job (before overheads)", [
        inp("Revenue", "money", [j["revenue"]]), inp("Materials", "money", [-j["materials"]]),
        inp("Subcontractors", "money", [-j["subcontractors"]]), inp("Technician hours", "hours", [j["hours"]]),
        inp("Technician cost rate ($/hour, wages and all on-costs)", "money", [m["tech_cost_rate"]]), calc("Technician time", "money", "-r3*r4"),
        calc("Job gross margin", "money", "r0+r1+r2+r5"), calc("Job gross margin %", "pct", "r6/r0")], cols=("This job",)) for j in installs]
    return {
        "kpis": [{"label": "Gross margin (P&L), September", "value": FMT["pct"](gm[0]), "sub": k1, "cls": c1, "spine": True, "support": s_gm},
                 {"label": "Cost to win a customer", "value": FMT["money"](cac[0]), "sub": k2, "cls": c2, "good_when": "lower", "support": s_cac},
                 {"label": "Technician time on jobs", "value": FMT["pct"](util[0]), "sub": k3, "cls": c3, "support": s_ut}],
        "chart": {"title": "Job gross margin on each installation invoiced in September 2026",
                  "subtitle": f"Whole job, recognised when invoiced: revenue less materials, subcontractors and technician time at ${m['tech_cost_rate']}/hour. Before overheads: not profit. One {m['target_margin']}.0% target for every job for now.",
                  "labels": [j["description"] for j in installs],
                  "values": [round(d["xl"]["rows"][-1]["values"][0] * 100, 1) for d in details],
                  "target": float(m["target_margin"]), "format": "pct1", "what": "job margin", "details": details,
                  "views": [{"id": "pct", "label": "Gross margin %", "values": [round(d["xl"]["rows"][-1]["values"][0] * 100, 1) for d in details],
                             "format": "pct1", "target": float(m["target_margin"])},
                            {"id": "dollars", "label": "Gross margin $", "values": [j["gross_profit"] for j in installs], "format": "money0",
                             "marks": [half_up(j["revenue"] * m["target_margin"] / 100) for j in installs],
                             "mark_label": f"Target gross margin ({m['target_margin']}.0% of the job's revenue)", "below_marks": True}]},
        "facts": dict(gm=gm, cac=cac, util=util),
    }


def fourth_services(m, out):
    r = out["r"]
    S = lambda f: [f(mo) for mo in PERIODS]
    sep = sorted([x for x in out["engagements"] if x["month"] == "2026-09"], key=lambda x: -x["contribution"] / x["revenue"])
    s_ut = support("Consultant utilisation", "Billable hours ÷ hours available", [
        inp("Billable hours (timesheets)", "hours", S(lambda mo: r[mo]["hours"])),
        inp("Consultants", "int", S(lambda mo: m["consultants"])), inp("Working days", "int", S(lambda mo: WORKING_DAYS[mo])),
        inp("Hours per day", "hours", S(lambda mo: HOURS_PER_DAY)),
        calc("Hours available", "hours", "r1*r2*r3"), calc("Utilisation", "pct", "r0/r4")])
    s_rate = support("Revenue per billable hour", "Revenue ÷ billable hours", [
        inp("Revenue", "money", S(lambda mo: r[mo]["revenue"])), inp("Billable hours", "hours", S(lambda mo: r[mo]["hours"])),
        calc("Revenue per hour", "money", "r0/r1")],
        "Retainers and training are fixed fees, so fewer hours on them raises the hourly figure.")
    s_lock = support("Cash tied up in work", "Work in progress + unpaid invoices at month end", [
        inp("Work in progress (project time not yet billed)", "money", S(lambda mo: out["bs"][mo]["stock"])),
        inp("Unpaid client invoices", "money", S(lambda mo: out["bs"][mo]["debtors"])),
        calc("Total tied up", "money", "r0+r1")],
        "Milestone billing on the logistics and manufacturer projects landed at the end of September, so it moved from unbilled to unpaid.")
    kp = lambda sp: sp["xl"]["rows"][-1]["values"]
    util, rate, lock = kp(s_ut), kp(s_rate), kp(s_lock)
    k1, c1 = chg(util[0], util[1], FMT["pct"])
    k2, c2 = chg(rate[0], rate[1], FMT["money"])
    k3, c3 = chg(lock[0], lock[1], FMT["money"], "down")
    details = [support(x["description"], "Gross margin ÷ revenue for this engagement (before overheads)", [
        inp("Revenue", "money", [x["revenue"]]), inp("Contractors", "money", [-x["contractors"]]),
        inp("Consultant hours", "hours", [x["hours"]]), inp("Consultant cost rate ($/hour, wages and all on-costs)", "money", [m["cost_rate"]]),
        calc("Consultant time", "money", "-r2*r3"), calc("Gross margin", "money", "r0+r1+r4"), calc("Gross margin %", "pct", "r5/r0")],
        cols=("This engagement",)) for x in sep]
    return {
        "kpis": [{"label": "Consultant utilisation, September", "value": FMT["pct"](util[0]), "sub": k1, "cls": c1, "spine": True, "support": s_ut},
                 {"label": "Revenue per billable hour", "value": FMT["money"](rate[0]), "sub": k2, "cls": c2, "support": s_rate},
                 {"label": "Unbilled work + unpaid invoices", "value": FMT["money"](lock[0]), "sub": k3, "cls": c3, "good_when": "lower", "support": s_lock}],
        "chart": {"title": "Gross margin on each client engagement, September 2026 work only",
                  "subtitle": f"September's revenue less contractors and consultant time at ${m['cost_rate']}/hour. Before overheads: not profit. Not the whole engagement to date. One {m['target_margin']}.0% target for every engagement for now.",
                  "labels": [x["description"] for x in sep],
                  "values": [round(d["xl"]["rows"][-1]["values"][0] * 100, 1) for d in details],
                  "target": float(m["target_margin"]), "format": "pct1", "what": "engagement margin", "details": details,
                  "views": [{"id": "pct", "label": "Gross margin %", "values": [round(d["xl"]["rows"][-1]["values"][0] * 100, 1) for d in details],
                             "format": "pct1", "target": float(m["target_margin"])},
                            {"id": "dollars", "label": "Gross margin $", "values": [x["contribution"] for x in sep], "format": "money0",
                             "marks": [half_up(x["revenue"] * m["target_margin"] / 100) for x in sep],
                             "mark_label": f"Target gross margin ({m['target_margin']}.0% of revenue)", "below_marks": True}]},
        "facts": dict(util=util, rate=rate, lock=lock),
    }


def fourth_nfp(m, out):
    r, bs = out["r"], out["bs"]
    S = lambda f: [f(mo) for mo in PERIODS]
    fund_rows = [inp(k, "money", S(lambda mo, k=k: r[mo]["fund"][k])) for k in m["fundraising"]]
    nf = len(fund_rows)
    s_ctr = support("Cost to raise a dollar", "Fundraising costs ÷ money raised (grants, donations, events), in cents", fund_rows + [
        calc("Fundraising costs", "money", "+".join(f"r{i}" for i in range(nf))),
        inp("Grant income", "money", S(lambda mo: r[mo]["grant_income"])),
        inp("Donations", "money", S(lambda mo: r[mo]["other_income"]["Donations"])),
        inp("Fundraising events", "money", S(lambda mo: r[mo]["other_income"]["Fundraising events"])),
        calc("Money raised", "money", f"r{nf + 1}+r{nf + 2}+r{nf + 3}"),
        calc("Cost per dollar raised", "cents", f"r{nf}/r{nf + 4}*100")],
        "September's gala raised $41,600 but cost $16,900 to run, which lifts the month's figure.")
    s_run = support("Unrestricted cash runway", "(Cash at bank − unspent grant money − GST and PAYG owed to the ATO) ÷ a month's cash spending", [
        inp("Cash at bank", "money", S(lambda mo: bs[mo]["cash"])),
        inp("Less unspent grant money (belongs to funders' programs)", "money", S(lambda mo: -bs[mo]["grants_in_advance"])),
        inp("Less GST and PAYG withheld owed to the ATO (paid with the BAS)", "money", S(lambda mo: -(bs[mo]["gst_payable"] + bs[mo]["paygw_payable"]))),
        calc("Unrestricted cash", "money", "r0+r1+r2"),
        inp("Cash spending in the month (expenses less depreciation)", "money", S(lambda mo: r[mo]["cash_expenses"])),
        calc("Runway", "months", "r3/r4")], f"Reserves target: {m['reserves_target_months']}.0 months.")
    ending = [gr for gr in out["grants"] if gr["months_left"] <= m["ending_within_months"]]
    s_end = support(f"Grants ending in the next {m['ending_within_months']} months", "Grant total − spent to date, for each grant ending soon",
                    [inp(f"{gr['program']} (ends {ds.strf(date.fromisoformat(gr['end']), '%-d %b %Y')})", "money", [gr["unspent"]]) for gr in ending]
                    + [calc("Total still to spend", "money", "+".join(f"r{i}" for i in range(len(ending))))],
                    "Unspent money usually has to be returned, or an extension negotiated, so plan the spending now.", cols=("Still to spend",))
    ctr, run = s_ctr["xl"]["rows"][-1]["values"], s_run["xl"]["rows"][-1]["values"]
    k1, c1 = chg(ctr[0], ctr[1], FMT["cents"], "down")
    k2, c2 = chg(run[0], run[1], FMT["months"])
    G = sorted(out["grants"], key=lambda gr: -gr["total"])     # biggest grants first, same order in both views
    mname = lambda mo: date(int(mo[:4]), int(mo[5:]), 1).strftime("%b %y")
    details = [support(gr["program"], f"{gr['funder']} · {money(gr['total'])} · {date.fromisoformat(gr['start']).strftime('%b %Y')} to {date.fromisoformat(gr['end']).strftime('%b %Y')}", [
        inp("Grant total", "money", [gr["total"]]), inp("Received from the funder", "money", [gr["received_to_date"]]),
        inp("Spent to date", "money", [gr["spent_to_date"]]), inp("Budget to date", "money", [gr["budget_to_date"]]),
        inp("Months left", "int", [gr["months_left"]]), calc("Still to spend", "money", "r0-r2"),
        calc("Over (under) budget to date", "money", "r2-r3"), calc("Over (under) budget, % of budget to date", "pct", "r2/r3-1")], None,
        {"title": "Spend by month against budget", "labels": [mname(x["month"]) for x in gr["monthly"]],
         "values": [x["spend"] for x in gr["monthly"]], "budget": [x["budget"] for x in gr["monthly"]], "format": "money0"},
        cols=("This grant",)) for gr in G]
    pcts = [round(d["xl"]["rows"][-1]["values"][0] * 100, 1) for d in details]          # over (+) or under (-) budget, % of budget to date
    var_d = [d["xl"]["rows"][-2]["values"][0] for d in details]                          # the same, in dollars
    return {
        "kpis": [{"label": "Cost to raise a dollar, September", "value": FMT["cents"](ctr[0]), "sub": k1, "cls": c1, "good_when": "lower", "spine": True, "support": s_ctr},
                 {"label": "Unrestricted cash runway", "value": FMT["months"](run[0]), "sub": k2, "cls": c2, "support": s_run},
                 {"label": f"Grants ending in {m['ending_within_months']} months", "value": money(sum(gr['unspent'] for gr in ending)),
                  "sub": f"to spend in {m['ending_within_months']} months · {len(ending)} grant{'s' if len(ending) != 1 else ''} ending", "cls": "bad" if ending else "", "good_when": "lower", "support": s_end}],
        "chart": {"title": "Each grant: over or under budget to 30 September 2026",
                  "subtitle": "Spending to date against budget to date (the grant spread evenly over its months). Over budget in red, under budget in green; within 1% in amber.",
                  "labels": [gr["program"] for gr in G],
                  "values": pcts, "format": "pct_var", "what": "grant spend against budget", "variance": True,
                  "views": [{"id": "pct", "label": "% of budget", "values": pcts, "format": "pct_var"},
                            {"id": "dollars", "label": "$", "values": var_d, "format": "money_var"}],
                  "details": details},
        "facts": dict(ctr=ctr, runway=run, ending=ending),
    }


# ============================================================== assumptions

def tax_assumption_rows(org, out):
    run = out["payroll"]
    rows = [["GST", "registered; 10%, accruals basis: GST on a sale is owed when it's invoiced, a credit on a bill is claimed when it's received. "
                    "The P&L excludes GST; invoices, bills, debtors, creditors and cash include it"],
            ["BAS", "quarterly, self-lodged: GST on sales − GST credits + PAYG withheld" + (" + PAYG instalment" if org != "nfp" else "")
                    + ". July to September is due 28 October; October to December, 28 February"],
            ["Pay runs", f"fortnightly on Thursdays: ${run['gross']:,} gross (a 26th of the year's gross wages); net pay ${run['net']:,} and super "
                         f"${run['super']:,} paid on the day; PAYG withheld (about {round(tp.PAYG_RATE[org] * 100)}% of gross, ${run['payg']:,}) goes with the BAS. "
                         "Two months a year have three pay runs"],
            ["Super", f"{round(tp.SUPER_RATE * 100)}% of gross wages, paid with each pay run (Payday Super, from 1 July 2026)"],
            ["Payroll tax", "none: the charity is exempt for wages paid for its charitable work (assumption to confirm)" if org == "nfp" else
                            f"none: Queensland's threshold is $1.3 million of wages a year (rate 4.75% above it); this business pays about ${round(run['annual_gross'] * (1 + tp.SUPER_RATE), -3):,.0f} including super"],
            ["Banking days", "money only moves on banking days: a payment due on a weekend or Queensland public holiday moves to the next banking day"]]
    if org == "nfp":
        rows[0][1] = ("registered (income over the $150,000 not-for-profit threshold); 10%, accruals basis. The P&L excludes GST; cash, fees receivable and bills include it")
        rows += [["Donations (assumption to confirm)", "no GST: a gift isn't payment for anything"],
                 ["Program fees (assumption to confirm)", "taxable: GST included in what's charged"],
                 ["Grants (assumption to confirm)", "taxable supplies under each funding agreement: the funder pays each instalment plus 10% GST"],
                 ["Fundraising events (assumption to confirm)", "taxable: ticket sales include GST"]]
    return rows


def trades_assumptions(m, out):
    sep = [j for j in out["jobs"] if j["month"] == "2026-09"]
    return [
        ["The business", [["What it is", m["about"]], ["Reporting month", "September 2026 (the last closed month), compared with August 2026"],
                          ["Financial year", "FY2027: 1 July 2026 to 30 June 2027"]]],
        ["Jobs (September)", [["Maintenance contracts", f"{len(m['contracts'])} customers, invoiced on the 1st, paid in about {m['contract_pay_days']} days"],
                              ["Installations", f"{len(m['installs']['2026-09'])} named jobs, each with its own quote, materials, subcontractors and hours"],
                              ["Call-outs", f"{m['callouts']['2026-09']} jobs at ${m['callout_rate']}/hour plus materials marked up {round((m['materials_markup'] - 1) * 100)}%"],
                              ["Jobs in September", f"{len(sep)} in total (every one is in the spreadsheet download and CSV)"]]],
        ["Costs", [["Technicians", f"{m['technicians']} employed full time: ${m['tech_wages']['2026-09']:,} in September incl. on-costs (every available hour at ${m['tech_cost_rate']})"],
                   ["Job costing rate", f"${m['tech_cost_rate']}/hour = technician wages incl. on-costs ÷ available hours, worked out each month; time charged to jobs + time not charged = technician wages"],
                   ["Working days", "20 in August (21 weekdays, less the Ekka People's Day holiday, Wed 12 Aug), 22 in September; 7.6 hours a day"],
                   ["Overheads", "set month by month, as shown in the P&L"],
                   ["Income tax", f"{m['tax_rate']}% of profit, provided monthly; the PAYG instalment is paid with each quarter's BAS"]]],
        ["Cash and balance sheet", [["Customer payments", "each invoice is paid on its own date; unpaid invoices at month end = debtors"],
                                    ["Supplier bills", "materials and subcontractors are paid the following month"],
                                    ["Equipment finance", f"${m['loan_repaid']['2026-09']:,} repaid each month"],
                                    ["New equipment", f"a ${m['capex']['2026-09']:,} trailer bought in September"]]],
        ["GST, BAS and payroll", tax_assumption_rows("trades", out)],
    ]


def services_assumptions(m, out):
    return [
        ["The business", [["What it is", m["about"]], ["Reporting month", "September 2026, compared with August 2026"],
                          ["Financial year", "FY2027: 1 July 2026 to 30 June 2027"]]],
        ["Engagements (September)", [["Projects", "hours worked at each project's rate; billed on milestones (unbilled time = work in progress)"],
                                     ["Retainers", "fixed monthly fee, billed monthly"], ["Training", "fixed fee, billed on delivery"],
                                     ["Engagements in September", f"{len(m['activity']['2026-09'])} (every one is in the spreadsheet download and CSV)"]]],
        ["Costs", [["Consultants", f"{m['consultants']} employed full time: ${m['salaries']['2026-09']:,} in September incl. on-costs (every available hour at ${m['cost_rate']})"],
                   ["Engagement costing rate", f"${m['cost_rate']}/hour = consultant salaries incl. on-costs ÷ available hours, worked out each month; time charged to clients + time not charged = salaries"],
                   ["Working days", "20 in August (21 weekdays, less the Ekka People's Day holiday, Wed 12 Aug), 22 in September; 7.6 hours a day"],
                   ["Income tax", f"{m['tax_rate']}% of profit, provided monthly"]]],
        ["Cash and balance sheet", [["Client payments", "each invoice is paid on its own date; unpaid invoices at month end = debtors"],
                                    ["Contractors", "paid the following month"]]],
        ["GST, BAS and payroll", tax_assumption_rows("services", out)],
    ]


def nfp_assumptions(m, out):
    return [
        ["The organisation", [["What it is", m["about"]], ["Reporting month", "September 2026, compared with August 2026"],
                              ["Financial year", "FY2027: 1 July 2026 to 30 June 2027"]]],
        ["Grants", [[gr['program'], f"{gr['funder']}: ${gr['total']:,}, {gr['start'][:7]} to {gr['end'][:7]}"] for gr in out["grants"]]
                   + [["Grant income", "recognised as the money is spent on the program"],
                      ["Unspent grants", "instalments received but not yet spent are a liability (grants received in advance)"]]],
        ["Other income and costs", [["Donations", "including the spring appeal in September"],
                                    ["Fundraising event", "September gala: income and costs in the same month"],
                                    ["Grant-funded spending", f"{round(m['grant_wage_share'] * 100)}% wages, the rest program costs"],
                                    ["Income tax", "none: registered charity, income-tax exempt"]]],
        ["Cash and balance sheet", [["Suppliers", "paid the following month"],
                                    ["Unrestricted cash", "cash at bank less unspent grant money, and less GST and PAYG withheld owed to the ATO"],
                                    ["Cash runway", "unrestricted cash ÷ this month's cash spending"],
                                    ["Reserves target", f"{m['reserves_target_months']} months of spending"]]],
        ["GST, BAS and payroll", tax_assumption_rows("nfp", out)],
    ]


# =================================================================== checks

def check_sections(rows, name):
    pending, problems = [], []
    for rw in rows:
        if rw["level"] == "heading":
            pending = []
        elif rw["level"] == "detail":
            pending.append(rw)
        elif rw["level"] == "subtotal" and pending:
            for i in range(2):
                if sum(p["values"][i] for p in pending) != rw["values"][i]:
                    problems.append(f"{name}: {rw['label']} {COLUMNS[i]}")
            pending = []
    return problems


def run_checks(org, model, out):
    problems = []
    for key in ("pnl", "bsr", "cfr"):
        problems += check_sections(out[key], f"{org} {key}")
    v = lambda key, label: next(rw["values"] for rw in out[key] if rw["label"] == label)
    pnl_labels = [rw["label"] for rw in out["pnl"]]
    for i, mo in enumerate(PERIODS):
        bs, prev = out["bs"][mo], out["bs"][prev_month(mo)]
        if org == "nfp":
            if v("bsr", "Net assets")[i] != v("bsr", "Accumulated funds")[i]: problems.append(f"nfp balance {mo}")
            if bs["accumulated"] - prev["accumulated"] != out["r"][mo]["surplus"]: problems.append(f"nfp surplus roll {mo}")
            if v("pnl", "Total income")[i] + v("pnl", "Total expenses")[i] != v("pnl", "Surplus for the month")[i]: problems.append("nfp surplus")
            grant_labels = {f"{gr[2]} grant" for gr in model["grants"]}
            grant_lines = sum(rw["values"][i] for rw in out["pnl"] if rw["label"] in grant_labels)
            if grant_lines != sum(out["r"][mo]["gspend"].values()): problems.append(f"nfp grant income {mo}")
            for gr_ in out["grants"]:
                if sum(x["spend"] for x in gr_["monthly"]) != gr_["spent_to_date"]: problems.append(f"nfp grant history {gr_['program']}")
                if sum(gr_["budget_by_month"].values()) != gr_["total"]: problems.append(f"nfp grant budget {gr_['program']}")
            bal = out["grant_bal"](mo)
            if bs["grants_in_advance"] - bs["grants_receivable"] != sum(bal.values()): problems.append(f"nfp grants in advance {mo}")
        else:
            if v("bsr", "Net assets")[i] != v("bsr", "Total equity")[i]: problems.append(f"{org} balance {mo}")
            if bs["retained"] - prev["retained"] != out["r"][mo]["npat"]: problems.append(f"{org} profit roll {mo}")
            for a, b, c in [("Total revenue", "Total cost of sales", "Gross profit"), ("Gross profit", "Total operating expenses", "EBITDA")]:
                if v("pnl", a)[i] + v("pnl", b)[i] != v("pnl", c)[i]: problems.append(f"{org} {c} {mo}")
            if v("pnl", "EBITDA")[i] + v("pnl", "Depreciation")[i] + v("pnl", "Interest")[i] != v("pnl", "Profit before tax")[i]: problems.append(f"{org} PBT")
            tax = next(l for l in pnl_labels if l.startswith("Income tax"))
            if v("pnl", "Profit before tax")[i] + v("pnl", tax)[i] != v("pnl", "Net profit after tax")[i]: problems.append(f"{org} NPAT")
            r = out["r"][mo]
            if org == "trades":
                mj = [j for j in out["jobs"] if j["month"] == mo]
                if sum(j["revenue"] for j in mj) != r["revenue"]: problems.append(f"trades job revenue {mo}")
                if sum(j["materials"] for j in mj) != r["mat"] or sum(j["subcontractors"] for j in mj) != r["sub"]: problems.append(f"trades job costs {mo}")
                if r["jobs_gp"] - (r["techw"] - r["allocated"]) != r["gp"]: problems.append(f"trades job GP to P&L {mo}")
                if bs["debtors"] != unpaid_at(out["jobs"], MONTH_END[mo]): problems.append(f"trades debtors {mo}")
            if org == "services":
                me = [x for x in out["engagements"] if x["month"] == mo]
                if sum(x["revenue"] for x in me) != r["revenue"]: problems.append(f"services engagement revenue {mo}")
                if r["contribution"] - (r["sal"] - r["allocated"]) != r["gp"]: problems.append(f"services engagement GP {mo}")
                if bs["stock"] != sum(r["wip"].values()): problems.append(f"services WIP {mo}")
                if bs["debtors"] != unpaid_at(out["invoices"], MONTH_END[mo]): problems.append(f"services debtors {mo}")
        cf = lambda label: v("cfr", label)[i]
        if cf("Cash at start of month") + cf("Net change in cash") != cf("Cash at end of month"): problems.append(f"{org} cash roll {mo}")
        if cf("Cash at end of month") != v("bsr", "Cash at bank")[i]: problems.append(f"{org} cash ties {mo}")
        if sum(rw["values"][i] for rw in out["cfr"] if rw["label"].startswith("Net cash from")) != cf("Net change in cash"): problems.append(f"{org} cf total {mo}")
        if bs["cash"] < 0: problems.append(f"{org} negative cash {mo}")
    return problems


# ============================================================ worked examples
# For the SME and not-for-profit pages: a question, the report that answers it,
# what it shows and what you'd do about it. Every number comes from the model
# above, and every example carries its workings.

def ex(org, question, visual, shows, action, sp):
    return {"org": org, "question": question, "visual": visual, "shows": shows, "action": action, "support": sp}


def examples_trades(m, out, f4):
    r, bs = out["r"], out["bs"]
    ch = f4["chart"]
    det = {d["title"]: d for d in ch["details"]}
    worst = min(range(len(ch["values"])), key=lambda i: ch["values"][i])
    wname = ch["labels"][worst]
    wj = next(j for j in out["jobs"] if j["month"] == "2026-09" and j["description"] == wname)
    below = sum(v < ch["target"] for v in ch["values"])
    e1 = ex("trades", "Which jobs actually make money?",
            {"type": "bars", "chart": {k: ch[k] for k in ("title", "labels", "values", "target", "format")}},
            f"{below} of the {len(ch['values'])} installation jobs invoiced in September made less than the {ch['target']:.1f}% job gross margin target. "
            f"The {wname} made a {ch['values'][worst]:.1f}% job gross margin: {FMT['hours'](wj['hours'])} of technician time ({money(wj['labour_cost'])}) "
            f"and {money(wj['subcontractors'])} of subcontractors on a {money(wj['revenue'])} job.",
            "Worth knowing what made this job different (hours, subcontractors, the customer) before quoting the next one.",
            det[wname])
    kc = f4["kpis"][1]
    cr = kc["support"]["xl"]["rows"]
    e2 = ex("trades", "What does it cost to win a customer?",
            {"type": "kpis", "kpis": [{"label": "September", "value": FMT["money"](cr[2]["values"][0])},
                                      {"label": "August", "value": FMT["money"](cr[2]["values"][1])}]},
            f"{int(cr[1]['values'][0])} new customers came from {money(cr[0]['values'][0])} of marketing in September, "
            f"against {int(cr[1]['values'][1])} from {money(cr[0]['values'][1])} in August: {money(cr[2]['values'][0])} each, down from {money(cr[2]['values'][1])}.",
            "Keep September's marketing mix, and record where each new customer came from, so next month's report shows the cost per channel.",
            kc["support"])
    # cash against the next pay run and supplier bills: unpaid invoices by age at 30 September
    end = MONTH_END["2026-09"]
    unpaid = [j for j in out["jobs"] if j["invoice_date"] <= end and j["paid_date"] > end]
    buckets = [("Invoiced 0-30 days ago", 0, 30), ("Invoiced 31-60 days ago", 31, 60), ("Invoiced more than 60 days ago", 61, 9999)]
    aged = [sum(j["amount"] for j in unpaid if lo <= (end - j["invoice_date"]).days <= hi) for _, lo, hi in buckets]
    if sum(aged) != bs["2026-09"]["debtors"]:
        raise SystemExit("aged debtors don't add up to trade debtors")
    sp3 = support("Will cash cover payroll and the bills in October?", "Cash at bank − next pay run − supplier bills due, before any collections", [
        inp("Cash at bank, 30 September", "money", [bs["2026-09"]["cash"]]),
        inp("Gross wages a pay run (a 26th of the year's, technicians + office)", "money", [out["payroll"]["gross"]]),
        inp("Less PAYG withheld (paid to the ATO with the BAS)", "money", [-out["payroll"]["payg"]]),
        inp("Plus super (paid with the pay run)", "money", [out["payroll"]["super"]]),
        calc("Next pay run, 1 October: net pay + super", "money", "r1+r2+r3"),
        inp("Supplier bills due in October (September's purchases, incl. GST)", "money", [bs["2026-09"]["creditors"]]),
        calc("Cash left before collections", "money", "r0-r4-r5"),
        *[inp(f"Unpaid invoices: {b[0].lower()}", "money", [a_]) for b, a_ in zip(buckets, aged)],
        calc("Unpaid invoices, total (incl. GST)", "money", "r7+r8+r9")],
        "Customers pay on their own dates; every unpaid invoice is in the jobs list in the spreadsheet download.", cols=("30 Sep 2026",))
    x3 = sp3["xl"]["rows"]
    over30 = aged[1] + aged[2]
    top3 = sorted(unpaid, key=lambda j: -j["amount"])[:3]
    if over30:
        tail = f"{money(over30)} of it invoiced more than 30 days ago."
        act = "Chase the invoices more than 30 days old this week, largest first, and time the supplier payment run for after the first collections land."
    else:
        tail = "none of it more than 30 days old, so this is about timing, not bad debts."
        act = (f"Ask the three largest customers ({money(sum(j['amount'] for j in top3))} between them) for their payment dates this week, "
               "and time the supplier payment run for after the first collections land.")
    e3 = ex("trades", "Will cash cover payroll next month?",
            {"type": "bars", "chart": {"title": "Unpaid invoices at 30 September, by age", "labels": [b[0] for b in buckets],
                                       "values": aged, "format": "money0", "plain": True}},
            f"Cash at bank is {money(x3[0]['values'][0])}. The next pay run ({money(x3[4]['values'][0])}) and September's supplier bills "
            f"({money(x3[5]['values'][0])}) come to {money(x3[4]['values'][0] + x3[5]['values'][0])}, so October depends on collecting some of the "
            f"{money(sum(aged))} customers owe, " + tail,
            act, sp3)
    return [e1, e2, e3]


def examples_services(m, out, f4):
    sep = [x for x in out["engagements"] if x["month"] == "2026-09"]
    types = ["Project", "Retainer", "Training"]
    plural = {"Project": "projects", "Retainer": "retainers", "Training": "training"}
    rows = []
    for t in types:
        xs = [x for x in sep if x["type"] == t]
        P = plural[t].capitalize()
        rows += [inp(f"{P}: revenue", "money", [sum(x["revenue"] for x in xs)]),
                 inp(f"{P}: contribution (after contractors and consultant time)", "money", [sum(x["contribution"] for x in xs)]),
                 inp(f"{P}: hours", "hours", [sum(x["hours"] for x in xs)])]
    rows += [calc(f"{plural[t].capitalize()}: margin", "pct", f"r{3 * i + 1}/r{3 * i}") for i, t in enumerate(types)]
    rows += [calc(f"{plural[t].capitalize()}: contribution per hour", "money", f"r{3 * i + 1}/r{3 * i + 2}") for i, t in enumerate(types)]
    sp = support("Gross margin by type of work, September", "Gross margin ÷ revenue, and gross margin ÷ hours, for each type of work", rows,
                 f"Gross margin = revenue less contractors and consultant time at ${m['cost_rate']}/hour (wages and all on-costs). Before overheads: not profit.", cols=("Sep 2026",))
    xr = sp["xl"]["rows"]
    margin = [xr[9 + i]["values"][0] * 100 for i in range(3)]
    perh = [xr[12 + i]["values"][0] for i in range(3)]
    low = min(sep, key=lambda x: x["contribution"] / x["revenue"])
    lowm = 100 * low["contribution"] / low["revenue"]
    best = max(range(3), key=lambda i: perh[i])
    all_above = all(v >= m["target_margin"] for v in margin)
    return [ex("services", "Which services should you drop?",
               {"type": "bars", "chart": {"title": "Gross margin by type of work, September", "labels": [plural[t].capitalize() for t in types],
                                          "values": [round(v, 1) for v in margin], "target": float(m["target_margin"]), "format": "pct1"}},
               ("Every type of work made more than the " if all_above else "Not every type of work made the ") + f"{m['target_margin']:.1f}% target in September: "
               + ", ".join(f"{plural[t]} {margin[i]:.1f}% ({money(perh[i])} an hour)" for i, t in enumerate(types))
               + f". The lowest single engagement was {low['description']} at {lowm:.1f}%.",
               ("Nothing needs dropping this month. " if all_above else "Review the work under target first. ")
               + f"Worth a look: {low['description']} has the lowest gross margin; {plural[types[best]]} makes the most per hour.",
               sp)]


def examples_nfp(m, out, f4):
    r, bs = out["r"]["2026-09"], out["bs"]["2026-09"]
    src = [("Grants", "Grant writing and reporting", r["grant_income"]),
           ("Donations", "Donor campaigns", r["other_income"]["Donations"]),
           ("Fundraising events", "Event costs", r["other_income"]["Fundraising events"])]
    rows = []
    for name, cost, raised in src:
        rows += [inp(f"{name}: cost ({cost.lower()})", "money", [r["fund"][cost]]), inp(f"{name}: raised", "money", [raised])]
    rows += [calc(f"{name}: cost per dollar raised", "cents", f"r{2 * i}/r{2 * i + 1}*100") for i, (name, _, _) in enumerate(src)]
    sp1 = support("Cost to raise a dollar, by source, September", "Fundraising cost ÷ money raised, for each source, in cents", rows, cols=("Sep 2026",))
    cents = [sp1["xl"]["rows"][6 + i]["values"][0] for i in range(3)]
    e1 = ex("nfp", "Which funding is worth chasing?",
            {"type": "bars", "chart": {"title": "Cost to raise a dollar, by source, September (cents)", "labels": [x[0] for x in src],
                                       "values": [half_up(c) for c in cents], "format": "cents_int", "plain": True}},
            f"Grants cost {half_up(cents[0])}¢ to raise each dollar, donations {half_up(cents[1])}¢ and the September gala {half_up(cents[2])}¢ "
            f"({money(r['fund']['Event costs'])} to raise {money(r['other_income']['Fundraising events'])}).",
            "Put the next spare hours into grant writing. Keep the gala only if it also brings in new regular donors, and track that from this year's guest list.",
            sp1)
    ending = sorted([gr for gr in out["grants"] if gr["months_left"] <= m["ending_within_months"]], key=lambda g: g["months_left"])
    rows = []
    for gr in ending:
        rows += [inp(f"{gr['program']}: still to spend", "money", [gr["unspent"]]), inp(f"{gr['program']}: months left", "int", [gr["months_left"]]),
                 inp(f"{gr['program']}: spent in September", "money", [gr["spent_sep"]])]
    rows += [calc(f"{gr['program']}: needed each month to finish on time", "money", f"r{3 * i}/r{3 * i + 1}") for i, gr in enumerate(ending)]
    sp2 = support("Grants ending in the next 6 months", "Still to spend ÷ months left, against what was spent in September", rows, cols=("30 Sep 2026",))
    need = [sp2["xl"]["rows"][3 * len(ending) + i]["values"][0] for i in range(len(ending))]
    g0, n0 = ending[0], need[0]
    e2 = ex("nfp", "Will each grant be spent before it ends?",
            {"type": "kpis", "kpis": [{"label": f"{gr['program']}: still to spend", "value": money(gr["unspent"]),
                                       "sub": f"{gr['months_left']} months left · {money(nd)} a month needed"} for gr, nd in zip(ending, need)]},
            f"{g0['program']} has {money(g0['unspent'])} left to spend in {g0['months_left']} months: {money(n0)} a month, "
            f"against {money(g0['spent_sep'])} spent in September.",
            f"Lift {g0['program']} spending by {money(n0 - g0['spent_sep'])} a month from October, or ask the {g0['funder'].replace('State ', 'state ', 1) if False else g0['funder']} now about carrying the balance over.",
            sp2)
    kr = f4["kpis"][1]["support"]
    xr = kr["xl"]["rows"]
    sp3 = support("Reserves: how far short of 3.0 months?", "Target months × monthly cash spending − unrestricted cash", [
        inp("Unrestricted cash, 30 September", "money", [xr[2]["values"][0]]), inp("Cash spending in September", "money", [xr[3]["values"][0]]),
        calc("Runway", "months", "r0/r1"), inp("Reserves target", "months", [float(m["reserves_target_months"])]),
        calc("Cash needed for the target", "money", "r3*r1"), calc("Gap to the target", "money", "r4-r0")], cols=("30 Sep 2026",))
    y = sp3["xl"]["rows"]
    e3 = ex("nfp", "How many months could you run on your own money?",
            {"type": "kpis", "kpis": [{"label": "Runway now", "value": FMT["months"](y[2]["values"][0])},
                                      {"label": "Target", "value": FMT["months"](y[3]["values"][0])},
                                      {"label": "Gap", "value": money(y[5]["values"][0])}]},
            f"Unrestricted cash ({money(y[0]['values'][0])}, after setting aside unspent grant money) would cover {FMT['months'](y[2]['values'][0])} "
            f"of spending at September's rate, short of the {FMT['months'](y[3]['values'][0])} target by {money(y[5]['values'][0])}.",
            "Take a reserves plan to the board: how much of each month's surplus goes to reserves, and by when the gap is closed.",
            sp3)
    hs = next(d for d in f4["chart"]["details"] if d["title"] == g0["program"])
    se = hs["series"]
    under = sum(v < b for v, b in zip(se["values"], se["budget"]))
    e4 = ex("nfp", f"How has {g0['program']} spent over time?",
            {"type": "series", "series": se},
            f"{g0['program']} spent less than its {money(se['budget'][0])} monthly budget in {under} of its {len(se['values'])} months so far, "
            f"which is why {money(g0['unspent'])} is left with {g0['months_left']} months to go.",
            "Worth knowing what held the under-budget months back (staffing, referrals, timing) while there's still time to catch up.",
            hs)
    return [e1, e2, e3, e4]


def build():
    """Run every model and check it. Returns {org: {...}} ready to publish."""
    result, problems = {}, []
    for org, m, fn, fourth, assum in [("trades", TRADES, trades, fourth_trades, trades_assumptions),
                                      ("services", SERVICES, services, fourth_services, services_assumptions),
                                      ("nfp", NFP, nfp, fourth_nfp, nfp_assumptions)]:
        out = fn(m)
        problems += run_checks(org, m, out)
        f4 = fourth(m, out)
        exf = {"trades": examples_trades, "services": examples_services, "nfp": examples_nfp}[org]
        result[org] = dict(model=m, out=out, fourth=f4, assumptions=assum(m, out), examples=exf(m, out, f4))
    if problems:
        raise SystemExit("Financial model checks FAILED:\n  " + "\n  ".join(problems))
    return result


if __name__ == "__main__":
    res = build()
    for org, v in res.items():
        print(f"\n=== {org}: {v['model']['long_name']} ===")
        for title, rows in [("P&L", v["out"]["pnl"]), ("Balance sheet", v["out"]["bsr"]), ("Cash flow", v["out"]["cfr"])]:
            print(f"-- {title}")
            for rw in rows:
                vals = "" if rw["values"] is None else "  ".join(f"{x:>10,}" for x in rw["values"])
                print(f"   {rw['level'][:3]:3} {rw['label'][:46]:46} {vals}")
        print("-- fourth", [(k["label"], k["value"], k["sub"]) for k in v["fourth"]["kpis"]])
        print("-- chart", list(zip(v["fourth"]["chart"]["labels"], v["fourth"]["chart"]["values"])))
    print("\nAll checks passed.")
