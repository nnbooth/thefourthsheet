#!/usr/bin/env python3
"""
month_end.py — the balance sheet and cash flow for every month, October 2024 to September 2026, for the three sample
organisations: the month-end close the model (financial_model.py) does for August and September, done for every month
of the history.

August and September are LOCKED and come from the model untouched. The history's balance sheets join them at 31 July
2026, the model's opening balance, to the dollar:

  Owed and owing      worked out from that month's own records at month end, the way the model does it:
                      debtors = invoices unpaid at month end; creditors = this month's bills; GST and PAYG withheld =
                      every month whose BAS hasn't been paid yet (paid on the 28th of the month after each quarter;
                      October to December: 28 February); wages owed since the last pay run; super (quarterly until
                      Payday Super, 1 July 2026); grants received ahead of spending (or spent ahead of instalments);
                      unbilled project time.
  Carried forward     cash, fixed assets, finance, leave provisions, income tax and retained earnings: worked back from
                      31 July 2026, a month at a time, by that month's own movements (depreciation, purchases, repayments,
                      leave accrued, tax provided and paid, profit, dividends).
  Cash flow           every line is what was earned or incurred less the change in what's owed (receipts = invoiced less
                      the rise in debtors, and so on), so the cash flow, the balance sheet and the profit agree by
                      construction, and the checks below prove it every month.

CHECKED (stops the build if not): every month's balance sheet balances; cash at the end = cash at the start + the
month's net cash flow; retained earnings / accumulated funds move by exactly the profit less dividends; 31 July 2026
equals the model's opening balance on every line; cash, finance, leave, work in progress and income tax payable are
never negative; profit equals the history ledger's (history.py) for every month.

Used by sample_data.py (fact_balance_month, fact_cash_flow_month) through warehouse.py.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

from datetime import date, timedelta

import data_status as ds
import financial_model as fm
import history
import tax_payroll as tp
from financial_model import half_up, unpaid_at, paid_in

MONTHS = history.HIST                       # Oct 2024 to Jul 2026: the history's month ends (Jul 2026 = the model's opening)
FLOW_MONTHS = MONTHS[1:]                    # Nov 2024 to Jul 2026: months with a month before them to move from
JULY = "2026-07"


def mend(mo):
    return ds.month_end(mo)


def prev_of(mo):
    y, m = map(int, mo.split("-"))
    return f"{y - (m == 1)}-{(m - 2) % 12 + 1:02d}"


def bas_paid_on(mo):
    """The day the BAS covering this month is paid (the 28th after its quarter, as paid: the next banking day)."""
    return tp.next_banking_day(tp.bas_due(mo))


def sg_paid_on(mo):
    """Before Payday Super (1 July 2026): super guarantee for a quarter is paid by the 28th of the month after it."""
    q_end = tp.quarter_of(mo)[-1]
    y, m = map(int, q_end.split("-"))
    return tp.next_banking_day(date(y + (m == 12), m % 12 + 1, 28))


def unpaid(by_month, mo, paid_on):
    """What's still owed at a month end: every month (up to this one) whose payment day is after the month end."""
    return sum(v for k, v in by_month.items() if k <= mo and paid_on(k) > mend(mo))


def fy_of(mo):
    y, m = map(int, mo.split("-"))
    return y + 1 if m >= 7 else y


def wages_owed(run, mo):
    """Wages since the last pay run at month end: a 10th of a pay run's gross for each working day since (as the model's opening)."""
    last = max(tp.pay_days(fm.month_start(mo), mend(mo)))
    since = sum(1 for k in range(1, (mend(mo) - last).days + 1) if ds.working(last + timedelta(days=k)))
    return half_up(run["gross"] * since / 10)


class Payroll:
    """Pay runs for each financial year (a 26th of the year's gross wages) and what's owed at each month end."""

    def __init__(self, org, wage_cost, leave, model_run):
        self.org, self.wage_cost, self.leave = org, wage_cost, leave
        self.runs = {}
        for fy in sorted({fy_of(mo) for mo in MONTHS}):
            if fy >= 2027:
                self.runs[fy] = model_run                       # FY2027: the model's pay run
                continue
            ms = [mo for mo in MONTHS if fy_of(mo) == fy]
            gross = sum(tp.gross_from_cost(wage_cost(mo), leave) for mo in ms) * 12 / len(ms)
            self.runs[fy] = tp.pay_run(half_up(gross), org)

    def run(self, mo):
        return self.runs[fy_of(mo)]

    def month(self, mo):
        w = self.wage_cost(mo)
        gross = tp.gross_from_cost(w, self.leave)
        return {"cost": w, "gross": gross, "super": w - self.leave - gross, "withheld": len(tp.pay_days_in(mo)) * self.run(mo)["payg"]}

    def owed(self, mo):
        """{wages_owed, super_payable, paygw_payable} at a month end."""
        run = self.run(mo)
        owed = wages_owed(run, mo)
        withheld = {k: self.month(k)["withheld"] for k in MONTHS if k <= mo}
        if mo >= "2026-07":                                   # Payday Super: paid with each pay run
            sup = half_up(owed * tp.SUPER_RATE)
        else:
            sup = unpaid({k: self.month(k)["super"] for k in MONTHS if k <= mo}, mo, sg_paid_on)
        return {"wages_owed": owed, "super_payable": sup, "paygw_payable": unpaid(withheld, mo, bas_paid_on)}


def roll_back(bs, mo_after, moves):
    """A carried-forward balance one month earlier: the later month end less that month's movement."""
    return {k: bs[mo_after][k] - v for k, v in moves.items()}


# ======================================================================= TRADES

TRADES_CAPEX = {"2025-03": 46000, "2025-11": 18500, "2026-04": 9800}      # a new van, then test equipment and tools
DIVIDENDS = {"trades": {}, "services": {}}
SERVICES_CAPEX = {"2025-02": 7400, "2026-01": 5200}                       # laptops and screens


def trades(res):
    T, out = fm.TRADES, res["trades"]["out"]
    jobs = history.trades_jobs(T) + [j for j in out["jobs"] if j["month"] in history.MODEL_MONTHS]
    invoices = [j for j in jobs] + [j for j in out["jobs"] if j["month"] in fm.PERIODS]
    leave = half_up(sum(T["provision_change"].values()) / len(T["provision_change"]))
    lines = {mo: {k: int(round(v)) for k, v in history.trades_lines(T, mo).items()} for mo in MONTHS}   # whole dollars, as posted
    wage = lambda mo: -(lines[mo]["Technician wages (incl. on-costs)"] + lines[mo]["Office and admin wages"])
    pr = Payroll("trades", wage, leave, out["payroll"])
    tax_opex = lambda mo: -sum(v for k, v in lines[mo].items() if fm.taxable(k))
    mj = lambda mo: [j for j in jobs if j["month"] == mo]
    purchases = lambda mo: sum(j["materials"] + j["subcontractors"] for j in mj(mo))
    pnl = {}
    for mo in MONTHS:
        jgp = sum(j["revenue"] - j["materials"] - j["subcontractors"] for j in mj(mo))
        pbt = jgp + sum(lines[mo].values())
        tax = half_up(pbt * T["tax_rate"] / 100)
        pnl[mo] = {"revenue": sum(j["revenue"] for j in mj(mo)), "pbt": pbt, "tax": tax, "npat": pbt - tax,
                   "dep": -lines[mo]["Depreciation"], "interest": -lines[mo]["Interest"]}
    net_gst = {mo: sum(j["gst"] for j in mj(mo)) - tp.gst_on(purchases(mo)) - tp.gst_on(tax_opex(mo)) - tp.gst_on(TRADES_CAPEX.get(mo, 0))
               for mo in MONTHS}
    return close("trades", res, MONTHS, invoices, pnl, net_gst, pr, leave,
                 owed_state=lambda mo: {"debtors": unpaid_at(invoices, mend(mo)), "creditors": tp.with_gst(purchases(mo))},
                 receipts=lambda mo: paid_in(invoices, mo),
                 bills=lambda mo: tp.with_gst(purchases(mo)) + tp.with_gst(tax_opex(mo)),
                 capex=TRADES_CAPEX, repaid=T["loan_repaid"]["2026-08"], dividends=DIVIDENDS["trades"])


# ===================================================================== SERVICES

def services(res):
    S, out = fm.SERVICES, res["services"]["out"]
    eng, inv = history.services_engagements(S)
    # invoices: the history's to April 2026; May to July are the model's (its July debtors and its earlier billing)
    invoices = [i for i in inv if i["invoice_date"].strftime("%Y-%m") <= "2026-04"] + out["invoices"]
    leave = half_up(sum(S["provision_change"].values()) / len(S["provision_change"]))
    lines = {mo: {k: int(round(v)) for k, v in history.services_lines(S, mo).items()} for mo in MONTHS}   # whole dollars, as posted
    wage = lambda mo: -(lines[mo]["Consultant salaries (incl. on-costs)"] + lines[mo]["Management and admin wages"])
    pr = Payroll("services", wage, leave, out["payroll"])
    tax_opex = lambda mo: -sum(v for k, v in lines[mo].items() if fm.taxable(k))
    me = lambda mo: [x for x in eng if x["month"] == mo]
    contractors = lambda mo: sum(x["contractors"] for x in me(mo))
    # July's contractor bills at month end are the model's opening ($3,900 + GST); the rest of July's contractor cost in
    # the ledger came from a contractor not registered for GST, paid in the month
    gst_base = lambda mo: S["history_contractors"][JULY] if mo == JULY else contractors(mo)
    billed = lambda mo, k="ex_gst": sum(i[k] for i in invoices if i["invoice_date"].strftime("%Y-%m") == mo)
    pnl = {}
    for mo in MONTHS:
        pbt = sum(x["revenue"] - x["contractors"] for x in me(mo)) + sum(lines[mo].values())
        tax = half_up(pbt * S["tax_rate"] / 100)
        pnl[mo] = {"revenue": sum(x["revenue"] for x in me(mo)), "billed": billed(mo), "pbt": pbt, "tax": tax, "npat": pbt - tax,
                   "dep": -lines[mo]["Depreciation"], "interest": -lines[mo]["Interest"]}
    net_gst = {mo: billed(mo, "gst") - tp.gst_on(gst_base(mo)) - tp.gst_on(tax_opex(mo)) - tp.gst_on(SERVICES_CAPEX.get(mo, 0))
               for mo in MONTHS}
    return close("services", res, MONTHS, invoices, pnl, net_gst, pr, leave,
                 owed_state=lambda mo: {"debtors": unpaid_at(invoices, mend(mo)), "creditors": tp.with_gst(gst_base(mo))},
                 receipts=lambda mo: paid_in(invoices, mo),
                 bills=lambda mo: contractors(mo) + tp.gst_on(gst_base(mo)) + tp.with_gst(tax_opex(mo)),
                 capex=SERVICES_CAPEX, repaid=S["loan_repaid"]["2026-08"], dividends=DIVIDENDS["services"], wip=True)


# ======================================================================= the close (SMEs)

def close(org, res, months, invoices, pnl, net_gst, pr, leave, owed_state, receipts, bills, capex, repaid, dividends, wip=False):
    m, out = res[org]["model"], res[org]["out"]
    july = out["bs"][JULY]
    bs = {JULY: dict(july)}
    # owed and owing, from each month's records
    for mo in months[:-1]:
        bs[mo] = {**owed_state(mo), **pr.owed(mo), "gst_payable": unpaid(net_gst, mo, bas_paid_on)}
    mine = {**owed_state(JULY), **pr.owed(JULY), "gst_payable": unpaid(net_gst, JULY, bas_paid_on)}
    differs = {k: (v, july[k]) for k, v in mine.items() if v != july[k]}
    if differs:
        raise SystemExit(f"month_end {org}: 31 July worked out from the records doesn't match the model's opening balance: {differs}")
    # income tax: provided each month, paid with the BAS that covers the quarter it was provided in
    tax_paid = {mo: 0 for mo in months}
    for mo in months:
        for q, paid in tp.bas_payments_between(mend(prev_of(mo)), mend(mo)):
            tax_paid[mo] += sum(pnl[k]["tax"] for k in q if k in pnl) or 3 * pnl[months[0]]["tax"]
    flows = {}
    # carried forward: back from 31 July, a month at a time
    for mo in reversed(months[1:]):
        p, b = prev_of(mo), bs[mo]
        cap = capex.get(mo, 0)
        div = dividends.get(mo, 0)
        moves = {"fixed_assets": cap - pnl[mo]["dep"], "loan": -repaid, "provisions": leave,
                 "tax_payable": pnl[mo]["tax"] - tax_paid[mo], "retained": pnl[mo]["npat"] - div,
                 "prepayments": 0, "share_capital": 0}
        if wip:
            moves["stock"] = pnl[mo]["revenue"] - pnl[mo]["billed"]
        else:
            moves["stock"] = 0
        bs[p].update(roll_back(bs, mo, moves))
        # the month's cash flow: earned or incurred, less the change in what's owed
        pm = pr.month(mo)
        pay_emp = (pm["gross"] + pm["super"] - (b["wages_owed"] - bs[p]["wages_owed"]) - (b["super_payable"] - bs[p]["super_payable"])
                   - pm["withheld"])
        gst_paid = bs[p]["gst_payable"] + net_gst[mo] - b["gst_payable"]
        payg_paid = bs[p]["paygw_payable"] + pm["withheld"] - b["paygw_payable"]
        ato = gst_paid + payg_paid + tax_paid[mo]
        rec = receipts(mo)
        sup = bs[p]["creditors"] + bills(mo) - b["creditors"]          # bills paid: owed at the start + billed - owed at the end
        operating = rec - sup - pay_emp - pnl[mo]["interest"] - ato
        capex_paid = tp.with_gst(cap)
        net = operating - capex_paid - repaid - div
        bs[p]["cash"] = b["cash"] - net
        flows[mo] = {"receipts": rec, "pay_sup": sup, "pay_emp": pay_emp, "interest": pnl[mo]["interest"], "ato": ato,
                     "operating": operating, "capex_paid": capex_paid, "repaid": repaid, "dividends": div, "net": net,
                     "gst_paid": gst_paid, "payg_paid": payg_paid, "tax_paid": tax_paid[mo]}
    check(org, bs, flows, pnl, months)
    return {"bs": bs, "flows": flows, "pnl": pnl}


# ========================================================================== NFP

# The grants that finished during the history were paid like the current ones: in advance, quarterly or half-yearly,
# with a final instalment in the grant's last month for what was actually spent (the acquittal: more, or a refund).
PAST_INSTALMENTS = {"G-091": ([(date(y, m, 15), 57000) for y, m in [(2023, 7), (2023, 10), (2024, 1), (2024, 4), (2024, 7), (2024, 10), (2025, 1), (2025, 4)]], date(2025, 6, 15)),
                    "G-093": ([(date(y, m, 15), 72000) for y, m in [(2024, 1), (2024, 7), (2025, 1), (2025, 7)]], date(2025, 12, 15)),
                    "G-095": ([(date(2025, 1, 15), 168000), (date(2025, 7, 15), 168000)], date(2025, 12, 15)),
                    "G-097": ([(date(2025, 7, 15), 44000)], date(2026, 6, 15))}
NFP_CAPEX = {"2025-08": 38500}                    # a second-hand van for the meals program


def nfp(res):
    N, out = fm.NFP, res["nfp"]["out"]
    cur_spend = {g["code"]: {x["month"]: x["spend"] for x in g["monthly"]} for g in out["grants"]}
    spend = {}
    for mo in MONTHS:                                         # each month's grant spend (= grant income), as the ledger posts it
        s = history.nfp_grant_spend(mo)
        s.update({code: ms[mo] for code, ms in cur_spend.items() if mo in ms})
        spend[mo] = s
    lines = {mo: {k: int(round(v)) for k, v in history.nfp_lines(N, mo, spend[mo]).items()} for mo in MONTHS}
    # every grant's instalments (banking days): the current ones from the model, the finished ones above, settled at the end
    inst = {gr[0]: list(gr[7]) for gr in N["grants"]}
    before = {}                                               # finished grants' spend before October 2024, at the budget's pace
    for code, _, _, _, total, s, e in history.NFP_PAST_GRANTS:
        months = history.grant_months(s, e)
        before[code] = round(total / len(months) * sum(1 for x in months if x < MONTHS[0]))
        sched, final = PAST_INSTALMENTS[code]
        spent = before[code] + sum(spend[mo].get(code, 0) for mo in MONTHS)
        inst[code] = [(tp.next_banking_day(d), a) for d, a in sched] + [(tp.next_banking_day(final), spent - sum(a for _, a in sched))]
    received = lambda code, d: sum(a for dt, a in inst[code] if dt <= d)
    recognised = lambda code, mo: before.get(code, 0) + sum(spend[k].get(code, 0) for k in MONTHS if k <= mo)
    def grant_bal(mo):
        return {c: received(c, mend(mo)) - recognised(c, mo) for c in inst}
    instalments = lambda mo: sum(a for c in inst for dt, a in inst[c] if dt.strftime("%Y-%m") == mo)
    wage_lines = ("Grant-funded program wages", "Program delivery wages (untied)", "Grant writing and reporting", "Administration wages")
    wage = lambda mo: -sum(lines[mo][k] for k in wage_lines)
    leave = half_up(sum(N["provision_change"].values()) / len(N["provision_change"]))
    pr = Payroll("nfp", wage, leave, out["payroll"])
    income_keys = ("Donations", "Fundraising events", "Program fees", "Interest")
    nonwage = lambda mo: -sum(v for k, v in lines[mo].items() if v < 0 and k not in wage_lines and k != "Depreciation")
    fees_rec = lambda mo: tp.with_gst(N["fees_receivable"][mo] if mo in N["fees_receivable"] else round(lines[mo]["Program fees"] * 0.36 / 100) * 100)
    pnl = {mo: {"surplus": sum(spend[mo].values()) + sum(lines[mo].values()), "dep": -lines[mo]["Depreciation"]} for mo in MONTHS}
    net_gst = {mo: tp.gst_on(instalments(mo)) + tp.gst_on(lines[mo]["Program fees"]) + tp.gst_on(lines[mo]["Fundraising events"])
               - tp.gst_on(nonwage(mo)) - tp.gst_on(NFP_CAPEX.get(mo, 0)) for mo in MONTHS}
    july = out["bs"][JULY]
    bs = {JULY: dict(july)}
    state = lambda mo: {"fees_receivable": fees_rec(mo), "payables": tp.with_gst(nonwage(mo)),
                        "grants_in_advance": sum(v for v in grant_bal(mo).values() if v > 0),
                        "grants_receivable": -sum(v for v in grant_bal(mo).values() if v < 0),
                        **pr.owed(mo), "gst_payable": unpaid(net_gst, mo, bas_paid_on)}
    for mo in MONTHS[:-1]:
        bs[mo] = state(mo)
    differs = {k: (v, july[k]) for k, v in state(JULY).items() if k != "payables" and v != july[k]}
    if differs:
        raise SystemExit(f"month_end nfp: 31 July worked out from the records doesn't match the model's opening balance: {differs}")
    flows = {}
    for mo in reversed(MONTHS[1:]):
        p, b = prev_of(mo), bs[mo]
        cap = NFP_CAPEX.get(mo, 0)
        bs[p].update(roll_back(bs, mo, {"fixed_assets": cap - pnl[mo]["dep"], "provisions": leave, "accumulated": pnl[mo]["surplus"], "prepayments": 0}))
        pm = pr.month(mo)
        pay_emp = (pm["gross"] + pm["super"] - (b["wages_owed"] - bs[p]["wages_owed"]) - (b["super_payable"] - bs[p]["super_payable"]) - pm["withheld"])
        gst_paid = bs[p]["gst_payable"] + net_gst[mo] - b["gst_payable"]
        payg_paid = bs[p]["paygw_payable"] + pm["withheld"] - b["paygw_payable"]
        ln = lines[mo]
        f = {"grants_received": tp.with_gst(instalments(mo)),
             "don_received": ln["Donations"] + tp.with_gst(ln["Fundraising events"]),
             "fees_received": tp.with_gst(ln["Program fees"]) - (b["fees_receivable"] - bs[p]["fees_receivable"]),
             "interest": ln["Interest"],
             "pay_sup": bs[p]["payables"] + tp.with_gst(nonwage(mo)) - b["payables"], "pay_emp": pay_emp,
             "ato": gst_paid + payg_paid, "capex_paid": tp.with_gst(cap), "gst_paid": gst_paid, "payg_paid": payg_paid}
        f["operating"] = f["grants_received"] + f["don_received"] + f["fees_received"] + f["interest"] - f["pay_sup"] - f["pay_emp"] - f["ato"]
        f["net"] = f["operating"] - f["capex_paid"]
        bs[p]["cash"] = b["cash"] - f["net"]
        flows[mo] = f
    problems = []
    for mo in MONTHS:
        b = bs[mo]
        assets = b["cash"] + b["fees_receivable"] + b["grants_receivable"] + b["prepayments"] + b["fixed_assets"]
        liab = sum(b[k] for k in ("payables", "wages_owed", "super_payable", "paygw_payable", "gst_payable", "grants_in_advance", "provisions"))
        if assets - liab != b["accumulated"]:
            problems.append(f"{mo}: doesn't balance ({assets - liab - b['accumulated']:+,})")
        for k in ("cash", "provisions", "fixed_assets", "grants_in_advance", "grants_receivable", "fees_receivable"):
            if b[k] < 0:
                problems.append(f"{mo}: {k} negative ({b[k]:,})")
    for mo, f in flows.items():
        if bs[prev_of(mo)]["cash"] + f["net"] != bs[mo]["cash"] or bs[prev_of(mo)]["accumulated"] + pnl[mo]["surplus"] != bs[mo]["accumulated"]:
            problems.append(f"{mo}: cash or accumulated funds don't roll")
    if problems:
        raise SystemExit("month_end nfp checks FAILED:\n  " + "\n  ".join(problems[:30]))
    return {"bs": bs, "flows": flows, "pnl": pnl, "spend": spend, "instalments": inst, "grant_bal": {mo: grant_bal(mo) for mo in MONTHS}}


LIAB = ("creditors", "wages_owed", "super_payable", "paygw_payable", "gst_payable", "provisions", "tax_payable", "loan")


def check(org, bs, flows, pnl, months):
    problems = []
    for mo in months:
        b = bs[mo]
        assets = b["cash"] + b["debtors"] + b["stock"] + b["prepayments"] + b["fixed_assets"]
        if assets - sum(b[k] for k in LIAB) != b["share_capital"] + b["retained"]:
            problems.append(f"{mo}: doesn't balance ({assets - sum(b[k] for k in LIAB) - b['share_capital'] - b['retained']:+,})")
        for k in ("cash", "loan", "provisions", "tax_payable", "stock", "debtors", "fixed_assets"):
            if b[k] < 0:
                problems.append(f"{mo}: {k} negative ({b[k]:,})")
    for mo, f in flows.items():
        p = prev_of(mo)
        if bs[p]["cash"] + f["net"] != bs[mo]["cash"]:
            problems.append(f"{mo}: cash doesn't roll")
        if bs[p]["retained"] + pnl[mo]["npat"] - f["dividends"] != bs[mo]["retained"]:
            problems.append(f"{mo}: retained earnings don't roll")
    if problems:
        raise SystemExit(f"month_end {org} checks FAILED:\n  " + "\n  ".join(problems[:30]))


# ====================================================================== the tables

# Each balance-sheet line (as the model's statements name it) and the balance behind it
SME_BS = lambda stock, fa: [("Cash at bank", "cash"), ("Trade debtors (unpaid invoices)", "debtors"), (stock, "stock"), ("Prepayments", "prepayments"),
                            (fa, "fixed_assets"), ("Trade creditors (bills due next month)", "creditors"), ("Wages owed (since the last pay run)", "wages_owed"),
                            ("Super payable", "super_payable"), ("PAYG withholding payable", "paygw_payable"), ("GST payable (net)", "gst_payable"),
                            ("Employee leave provisions", "provisions"), ("Income tax payable", "tax_payable"), ("Equipment finance", "loan"),
                            ("Share capital", "share_capital"), ("Retained earnings", "retained")]
BS_LINES = {"trades": SME_BS("Materials on hand", "Vehicles and equipment"),
            "services": SME_BS("Work in progress (unbilled project time)", "Office equipment"),
            "nfp": [("Cash at bank", "cash"), ("Program fees receivable", "fees_receivable"), ("Grants receivable (spent ahead of instalment)", "grants_receivable"),
                    ("Prepayments", "prepayments"), ("Vehicles and equipment", "fixed_assets"), ("Payables (bills due next month)", "payables"),
                    ("Wages owed (since the last pay run)", "wages_owed"), ("Super payable", "super_payable"), ("PAYG withholding payable", "paygw_payable"),
                    ("GST payable (net)", "gst_payable"), ("Grants received in advance (unspent)", "grants_in_advance"),
                    ("Employee leave provisions", "provisions"), ("Accumulated funds", "accumulated")]}
# Each cash-flow line, the flow behind it, and its sign (in +, out -)
SME_CF = lambda sup, capex: [("Receipts from customers (invoices paid)", "receipts", 1), (sup, "pay_sup", -1), ("Payments to employees", "pay_emp", -1),
                             ("Interest paid", "interest", -1), ("GST, PAYG and income tax paid (BAS)", "ato", -1), (capex, "capex_paid", -1),
                             ("Equipment finance repaid", "repaid", -1)]
CF_LINES = {"trades": SME_CF("Payments to suppliers", "Purchase of vehicles and equipment"),
            "services": SME_CF("Payments to contractors and suppliers", "Purchase of equipment"),
            "nfp": [("Grant instalments received", "grants_received", 1), ("Donations and fundraising received", "don_received", 1),
                    ("Program fees received", "fees_received", 1), ("Interest received", "interest", 1), ("Payments to suppliers", "pay_sup", -1),
                    ("Payments to employees", "pay_emp", -1), ("GST and PAYG paid (BAS)", "ato", -1), ("Purchase of vehicles and equipment", "capex_paid", -1)]}


def build(res):
    """{org: month_end result} for every organisation, plus the rows of fact_balance_month and fact_cash_flow_month as
    (org, month, line, amount): history months from the close above, August and September from the model's statements."""
    out, bal, cf = {}, [], []
    for org, fn in (("trades", trades), ("services", services), ("nfp", nfp)):
        r = out[org] = fn(res)
        if any(f.get("dividends") for f in r["flows"].values()):
            raise SystemExit(f"month_end {org}: dividends need a cash-flow line (and an account) before they can be paid")
        model = res[org]["out"]
        for mo in MONTHS:
            bal += [(org, mo, line, r["bs"][mo][k]) for line, k in BS_LINES[org]]
        for mo in FLOW_MONTHS:
            cf += [(org, mo, line, sign * r["flows"][mo][k]) for line, k, sign in CF_LINES[org]]
        for i, mo in enumerate(fm.PERIODS):            # August and September: the model's own statements, line by line
            rows = {rw["label"]: rw["values"][i] for rw in model["bsr"] + model["cfr"] if rw["values"] is not None}
            for line, k in BS_LINES[org]:
                if rows[line] != model["bs"][mo][k]:
                    raise SystemExit(f"month_end {org}: '{line}' isn't the model's {k} for {mo}")
                bal.append((org, mo, line, rows[line]))
            cf += [(org, mo, line, rows[line]) for line, _, _ in CF_LINES[org]]
    return out, bal, cf


if __name__ == "__main__":
    res = fm.build()
    for org, fn in (("trades", trades), ("services", services), ("nfp", nfp)):
        r = fn(res)
        print(f"== {org}: checks passed")
        for mo in MONTHS:
            b = r["bs"][mo]
            print(f"  {mo} " + " ".join(f"{k[:8]} {v:>9,}" for k, v in b.items()))
