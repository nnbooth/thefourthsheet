#!/usr/bin/env python3
"""
drivers.py — supporting files for every input that isn't a transaction.

The transactions (jobs, invoices, timesheets, ledger, grants, deliveries) are
already tables. This module writes tables for everything else the reports use,
so no number exists only in code:

  driver_month          headcount, wages, new customers, working days … by org and month
  cost_rate             costing rates, mark-ups, tax rate, payment terms
  target                every target line and threshold (margins, budgets, reserves, on-time bands)
  opening_balance       the balance sheet at 31 July 2026 that every balance starts from
  kpi_workings          each headline number and chart bar, line by line: inputs, results, calculation
  commentary            the notes and chart descriptions shown with the numbers
  dim_contract          maintenance contracts (fee, hours, materials, payment terms)
  dim_carrier           delivery carriers, in and out, and the regions they serve
  simulation_parameter  the rules used to invent the sample data (late rates, the planted stories, seeds)

Every table is checked against the model before it's written. Used by tools/1_build_data/sample_data.py.
"""

import re

import deliveries as dl
import financial_model as fm

V = lambda n: f"VARCHAR({n})"
BS_LABELS = {
    "trades": {"cash": "Cash at bank", "debtors": "Trade debtors (unpaid invoices)", "stock": "Materials on hand",
               "prepayments": "Prepayments", "fixed_assets": "Vehicles and equipment",
               "creditors": "Trade creditors (bills due next month)", "provisions": "Employee leave provisions",
               "tax_payable": "Income tax payable", "loan": "Equipment finance", "share_capital": "Share capital",
               "retained": "Retained earnings"},
    "nfp": {"cash": "Cash at bank", "fees_receivable": "Program fees receivable",
            "grants_receivable": "Grants receivable (spent ahead of instalment)", "prepayments": "Prepayments",
            "fixed_assets": "Vehicles and equipment", "payables": "Payables (bills due next month)",
            "grants_in_advance": "Grants received in advance (unspent)", "provisions": "Employee leave provisions",
            "accumulated": "Accumulated funds"},
}
PAYROLL_TAX_LABELS = {"wages_owed": "Wages owed (since the last pay run)", "super_payable": "Super payable",
                      "paygw_payable": "PAYG withholding payable", "gst_payable": "GST payable (net)"}
for _o in ("trades", "nfp"):
    BS_LABELS[_o].update(PAYROLL_TAX_LABELS)
BS_LABELS["services"] = {**BS_LABELS["trades"], "stock": "Work in progress (unbilled project time)",
                         "fixed_assets": "Office equipment"}
LIABILITY_OR_EQUITY = {"creditors", "provisions", "tax_payable", "loan", "share_capital", "retained", "payables",
                       "grants_in_advance", "accumulated"} | set(PAYROLL_TAX_LABELS)


def build(res, account_ids):
    T, problems = {}, []

    def tbl(name, desc, cols, rows):
        T[name] = (desc, [c[0] for c in cols], rows, cols)

    org = [("org_id", V(12) + " REFERENCES dim_org(org_id)")]

    # ---- driver_month
    rows = []
    for mo in fm.PERIODS:
        t, s = fm.TRADES, fm.SERVICES
        rows += [["trades", mo, "Technicians", t["technicians"], "people"],
                 ["trades", mo, "Technician wages incl. on-costs", t["tech_wages"][mo], "$"],
                 ["trades", mo, "New customers (first job ever)", t["new_customers"][mo], "customers"],
                 ["trades", mo, "Call-outs", t["callouts"][mo], "jobs"],
                 ["trades", mo, "Working days", fm.WORKING_DAYS[mo], "days"],
                 ["trades", mo, "Hours per working day", fm.HOURS_PER_DAY, "hours"],
                 ["services", mo, "Consultants", s["consultants"], "people"],
                 ["services", mo, "Consultant salaries incl. on-costs", s["salaries"][mo], "$"],
                 ["services", mo, "New clients", s["new_clients"][mo], "clients"],
                 ["services", mo, "Working days", fm.WORKING_DAYS[mo], "days"],
                 ["services", mo, "Hours per working day", fm.HOURS_PER_DAY, "hours"]]
        for side, m in (("trades", t), ("services", s)):
            rows += [[side, mo, "Leave provision increase", m["provision_change"][mo], "$"],
                     [side, mo, "Equipment finance repaid", m["loan_repaid"][mo], "$"],
                     [side, mo, "Equipment bought", m["capex"][mo], "$"]]
        n = fm.NFP
        rows += [["nfp", mo, "Program fees receivable at month end", n["fees_receivable"][mo], "$"],
                 ["nfp", mo, "Leave provision increase", n["provision_change"][mo], "$"],
                 ["nfp", mo, "Equipment bought", n["capex"][mo], "$"]]
    # check the drivers behind the headline numbers
    cac_rows = res["trades"]["fourth"]["kpis"][1]["support"]["xl"]["rows"]
    if [r[3] for r in rows if r[0] == "trades" and r[2].startswith("New customers")] != cac_rows[1]["values"]:
        problems.append("driver_month new customers")
    import warehouse
    rows += [r_ for r_ in warehouse.build.history["drivers"] if r_[3] is not None]     # Oct 2024 to Jul 2026, and October to date
    tbl("driver_month", "Supporting drivers by organisation and month, Oct 2024 to October 2026: headcount, wages, new customers, marketing, working days and other inputs that aren't transactions.",
        org + [("month_key", V(7)), ("driver", V(60)), ("value", "DECIMAL(14,2)"), ("unit", V(12))], rows)

    # ---- cost_rate
    t, s, n = fm.TRADES, fm.SERVICES, fm.NFP
    rows = [["trades", "Technician cost rate", t["tech_cost_rate"], "$ per hour", "Technician time charged to a job"],
            ["trades", "Call-out charge rate", t["callout_rate"], "$ per hour", "Call-out labour billed to the customer"],
            ["trades", "Materials mark-up on call-outs", t["materials_markup"], "multiplier", "Call-out materials billed to the customer"],
            ["trades", "Income tax rate", t["tax_rate"] / 100, "share", "Monthly tax provision"],
            ["trades", "Maintenance contract payment terms", t["contract_pay_days"], "days", "Contract invoices"],
            ["services", "Consultant cost rate", s["cost_rate"], "$ per hour", "Consultant time charged to an engagement"],
            ["services", "Income tax rate", s["tax_rate"] / 100, "share", "Monthly tax provision"],
            ["nfp", "Share of grant spending that is wages", n["grant_wage_share"], "share", "Splits grant-funded spending into wages and program costs"]]
    tbl("cost_rate", "Supporting rates: costing rates, mark-ups, tax rate and payment terms used in the calculations.",
        org + [("rate", V(60)), ("value", "DECIMAL(14,4)"), ("unit", V(16)), ("used_for", V(80))], rows)

    # ---- target
    rows = [["trades", "Installation job margin", "Every installation job", t["target_margin"] / 100, "share"],
            ["services", "Engagement margin", "Every client engagement", s["target_margin"] / 100, "share"],
            ["nfp", "Grant spend against budget to date", "Every grant", 1.0, "share"],
            ["nfp", "Reserves (unrestricted cash runway)", "Organisation", n["reserves_target_months"], "months"],
            ["nfp", "Grants ending soon: window", "Every grant", n["ending_within_months"], "months"],
            ["distribution", "On time: good", "Every customer / supplier on the map", 0.95, "share"],
            ["distribution", "On time: some late", "Every customer / supplier on the map", 0.80, "share"]]
    tbl("target", "Supporting targets and thresholds: the target lines, colour bands and windows used on the dashboard, map and exports. One target per group for now (per-job targets from quotes are on the to-do list).",
        org + [("target", V(60)), ("applies_to", V(60)), ("value", "DECIMAL(10,4)"), ("unit", V(10))], rows)

    # ---- opening_balance (31 July 2026) with a balance check
    rows = []
    for o in ("trades", "services", "nfp"):
        b = res[o]["out"]["bs"]["2026-07"]
        assets = sum(v for k, v in b.items() if k in BS_LABELS[o] and k not in LIABILITY_OR_EQUITY)
        claims = sum(v for k, v in b.items() if k in BS_LABELS[o] and k in LIABILITY_OR_EQUITY)
        if assets != claims:
            problems.append(f"opening balance {o} doesn't balance")
        for k, label in BS_LABELS[o].items():
            rows.append([o, "2026-07-31", account_ids[(o, "bsr", label)], label,
                         "Liability or equity" if k in LIABILITY_OR_EQUITY else "Asset", b[k]])
        start_cash = next(r_["values"][1] for r_ in res[o]["out"]["cfr"] if r_["label"] == "Cash at start of month")
        if start_cash != b["cash"]:
            problems.append(f"opening cash {o}")
    tbl("opening_balance", "Supporting opening balance sheet at 31 July 2026 (the day before the reporting starts). Assets equal liabilities plus equity for each organisation.",
        org + [("as_at", "DATE"), ("account_id", "INT REFERENCES dim_account(account_id)"), ("line", V(60)), ("side", V(20)), ("amount", "INT")], rows)

    # ---- kpi_workings and commentary
    rows, notes = [], []
    for o in ("trades", "services", "nfp"):
        f4 = res[o]["fourth"]
        items = [("Headline number", k["label"], k["support"]) for k in f4["kpis"]]
        scope = {"trades": "Installation job", "services": "Engagement", "nfp": "Grant"}[o]
        items += [(scope, d["title"], d) for d in f4["chart"].get("details", [])]
        for sc, subject, sp in items:
            xr, cols = sp["xl"]["rows"], sp["xl"]["cols"]
            for i, r_ in enumerate(xr):
                calc = re.sub(r"r(\d+)", lambda m: f"[line {int(m.group(1)) + 1}]", r_["calc"]) if r_["calc"] else None
                for c, col in enumerate(cols):
                    rows.append([o, sc, subject, i + 1, r_["label"], r_["kind"], col, r_["values"][c], 1 if calc else 0, calc])
                if r_["calc"]:     # re-check every calculated line from its inputs
                    for c in range(len(cols)):
                        got = eval(re.sub(r"r(\d+)", lambda m: f"xr[{m.group(1)}]['values'][{c}]", r_["calc"]), {}, {"xr": xr})
                        if abs(got - r_["values"][c]) > 1e-9:
                            problems.append(f"kpi_workings {o} {subject} {r_['label']}")
            if sp.get("note"):
                notes.append([o, sc, subject, "2026-09", "Note on the workings", sp["note"]])
        ch = f4["chart"]
        notes.append([o, "Chart", ch["title"], "2026-09", "What the chart measures", ch.get("subtitle", "")])
    tbl("kpi_workings", "Supporting workings for every headline number and chart bar, line by line. is_calculated = 1 lines are worked out from the other lines ([line n] refers to line n of the same item) and are formulas in the Excel downloads.",
        org + [("scope", V(20)), ("subject", V(80)), ("line_no", "INT"), ("line", V(80)), ("kind", V(10)), ("column_label", V(20)),
               ("value", "DECIMAL(18,6)"), ("is_calculated", "INT"), ("calculation", V(120))], rows)
    tbl("commentary", "Supporting commentary: the notes and chart descriptions shown with the numbers (typed by the analyst at month end in real use).",
        org + [("scope", V(20)), ("subject", V(80)), ("month_key", V(7)), ("kind", V(30)), ("text", V(1000))], notes)

    # ---- dim_contract
    from ids import contract_no
    rows = [[contract_no(i), "trades", cust, fee, hrs, mat, t["contract_pay_days"]] for i, (cust, fee, hrs, mat) in enumerate(t["contracts"])]
    jm = {j["job"]: j for j in res["trades"]["out"]["jobs"] if j["month"] == "2026-09" and j["type"] == "Maintenance contract"}
    for r_ in rows:
        if jm[r_[0]]["revenue"] != r_[3]:
            problems.append(f"contract {r_[0]}")
    tbl("dim_contract", "Supporting maintenance contracts: one per customer, invoiced on the 1st of each month.",
        [("contract_id", V(10) + " PRIMARY KEY"), ("org_id", V(12) + " REFERENCES dim_org(org_id)"), ("customer", V(60)),
         ("monthly_fee", "INT"), ("tech_hours_per_month", "DECIMAL(6,1)"), ("materials_per_month", "INT"), ("payment_days", "INT")], rows)

    # ---- dim_carrier
    regions = {}
    for reg, car in dl.CARRIER_BY_REGION.items():
        regions.setdefault(car, []).append(reg)
    rows = [[c, "Out (to customers)", "Own fleet" if c == "Own trucks" else "Courier" if "courier" in c else "Third-party carrier",
             ", ".join(sorted(regions.get(c, ["Inner Brisbane (urgent orders)"])))] for c in dl.BASE_LATE]
    rows += [[c, "In (from suppliers)", "Supplier" if "Supplier" in c else "Third-party carrier", ""]
             for c in sorted({sp[7] for sp in dl.SUPPLIERS})]
    tbl("dim_carrier", "Supporting carriers for deliveries in and out, and the regions each delivery-out carrier serves.",
        [("carrier", V(30) + " PRIMARY KEY"), ("direction", V(20)), ("carrier_type", V(24)), ("regions_served", V(200))], rows)

    # ---- simulation_parameter (how the sample data was invented)
    rows = [["deliveries", f"Chance a delivery is late: {c}", p, "share"] for c, p in dl.BASE_LATE.items()]
    rows += [["deliveries", "Extra chance of being late on a Monday", 0.05, "share"],
             ["deliveries", "Carrier A, Gold Coast, from 7 Sep 2026: chance late", 0.38, "share"],
             ["deliveries", "Supplier C, September 2026: chance late", 0.55, "share"],
             ["deliveries", "Port hold on Supplier D, 21-25 Sep 2026: days late", 6, "working days"],
             ["deliveries", "Chance a delivery is short (not in full)", 0.03, "share"]]
    rows += [["deliveries", f"Chance late: {sp[1]}", sp[8], "share"] for sp in dl.SUPPLIERS]
    rows += [["deliveries", "Random seed (deliveries out)", 2026, "seed"], ["deliveries", "Random seed (deliveries in)", 4040, "seed"],
             ["model", "Random seed (trades jobs)", 2604, "seed"], ["model", "Random seed (services invoices)", 311, "seed"],
             ["model", "Random seed (grant history)", 102, "seed"]]
    tbl("simulation_parameter", "How the sample data was invented: the rules and random seeds the generators use. Not business data; kept so the sample can be rebuilt exactly.",
        [("area", V(20)), ("parameter", V(80)), ("value", "DECIMAL(10,4)"), ("unit", V(16))], rows)

    if problems:
        raise SystemExit("Supporting files checks FAILED:\n  " + "\n  ".join(problems))
    return T
