#!/usr/bin/env python3
"""
model_rules.py — rules the sample numbers must always keep (site review, 9 Oct 2026). Run from the repo root:

    python3 -I tools/1_build_data/tests/model_rules.py .

  N1  time charged to the work + time not charged = technician wages (consultant salaries), every whole month,
      and the costing rate is wages ÷ available hours (people × working days × 7.6)
  N4  pay runs: (net pay + super) × pay runs in the month = cash paid to employees, every month with cash
  N5  balance sheets balance with GST payable, PAYG withholding payable, super payable and wages owed included
  N11 no money moves on a Saturday, Sunday or Queensland public holiday

Prints PASS or FAIL for each rule and exits 1 if anything fails. (When check_numbers.py arrives, these rules move into it.)
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

import data_status as ds          # noqa: E402
import financial_model as fm      # noqa: E402
import tax_payroll as tp          # noqa: E402
import warehouse as wh            # noqa: E402

fails = []


def rule(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def rows(t):
    return next(x for x in t if isinstance(x, list) and x and isinstance(x[0], list))


def cols(t):
    return [c[0] for c in next(x for x in t if isinstance(x, list) and x and isinstance(x[0], tuple))]


def records(t):
    c = cols(t)
    return [dict(zip(c, r)) for r in rows(t)]


res = fm.build()
tables = wh.build(res)
day = lambda k: date(k // 10000, k // 100 % 100, k % 100)
acct = {r[0]: r for r in rows(tables["dim_account"])}         # [id, org, statement, section, line, level, order, postable]

# ---- N1: charged + not charged = wages; wages = available hours x rate (every whole month in the ledger)
gl = defaultdict(int)
for k, org, a, amt, *_ in rows(tables["fact_gl_daily"]):
    gl[(org, str(k)[:4] + "-" + str(k)[4:6], acct[a][4])] += amt
charged = defaultdict(float)                                   # hours on the work, by the month the work is counted in (jobs invoiced, engagement months)
for r in records(tables["fact_job_month"]):
    charged[("trades", r["month_key"])] += r["tech_hours"]
for r in records(tables["fact_engagement_month"]):
    charged[("services", r["month_key"])] += r["hours"]
import history                     # noqa: E402
months = [m for m in history.HIST + ["2026-08", "2026-09"]]
bad = []
for org, line, people, rate in (("trades", "Technician wages (incl. on-costs)", history.trades_techs, fm.TRADES["tech_cost_rate"]),
                                ("services", "Consultant salaries (incl. on-costs)", history.services_consultants, fm.SERVICES["cost_rate"])):
    for m in months:
        wages = -gl[(org, m, line)]
        avail = people(m) * tp.working_days(m) * fm.HOURS_PER_DAY
        if abs(wages - avail * rate) > 1:
            bad.append(f"{org} {m}: wages {wages} vs {avail:.1f} h × ${rate}")
        charged_h = charged[(org, m)]
        not_charged = wages - charged_h * rate
        if abs(not_charged - (avail - charged_h) * rate) > 1:
            bad.append(f"{org} {m}: time not charged ${not_charged:,.0f} vs {(avail - charged_h):.1f} h × ${rate}")
rule("N1 charged + not charged time = wages, at wages ÷ available hours", not bad, "; ".join(bad[:5]))

# ---- N4: pay runs x runs in the month (net pay + super) = cash paid to employees
bad = []
cash_by = defaultdict(int)
for k, org, a, amt in rows(tables["fact_cash_daily"]):
    if acct[a][4] == "Payments to employees":
        cash_by[(org, str(k)[:4] + "-" + str(k)[4:6])] += -amt
for org in ("trades", "services", "nfp"):
    run = res[org]["out"]["payroll"]
    if run["net"] + run["payg"] != run["gross"]:
        bad.append(f"{org}: net + PAYG isn't the gross pay run")
    for m in ("2026-08", "2026-09", "2026-10"):
        n = len([d for d in tp.pay_days_in(m) if d <= ds.AS_AT.date()])
        if n * (run["net"] + run["super"]) != cash_by[(org, m)]:
            bad.append(f"{org} {m}: {n} pay runs × ${run['net'] + run['super']:,} ≠ ${cash_by[(org, m)]:,} paid")
    if abs(26 * run["gross"] - run["annual_gross"]) > 26:
        bad.append(f"{org}: 26 pay runs don't add to the year's gross wages")
rule("N4 pay runs × runs in the month + super = cash paid to employees", not bad, "; ".join(bad))

# ---- N5: balance sheets balance, with GST, PAYG withholding, super and wages owed in the liabilities
bad = []
need = ("GST payable (net)", "PAYG withholding payable", "Super payable", "Wages owed (since the last pay run)")
for org in ("trades", "services", "nfp"):
    out = res[org]["out"]
    labels = [r["label"] for r in out["bsr"]]
    for n_ in need:
        if n_ not in labels:
            bad.append(f"{org}: no '{n_}' line")
    v = lambda label: next(r["values"] for r in out["bsr"] if r["label"] == label)
    eq = "Accumulated funds" if org == "nfp" else "Total equity"
    for i, m in enumerate(fm.PERIODS):
        if v("Net assets")[i] != v(eq)[i]:
            bad.append(f"{org} {m}: net assets {v('Net assets')[i]} ≠ {eq.lower()} {v(eq)[i]}")
        liab = [r for r in out["bsr"] if r["level"] == "detail" and labels.index(r["label"]) > labels.index("Current liabilities")
                and (org == "nfp" or labels.index(r["label"]) < labels.index("Equity"))]
        tot = v("Total liabilities")[i] - (0 if org == "nfp" else v("Equipment finance")[i])
        if sum(r["values"][i] for r in liab if r["label"] not in ("Share capital", "Retained earnings", "Accumulated funds")) != tot:
            bad.append(f"{org} {m}: liabilities don't add up")
    if v("Cash at bank") != next(r["values"] for r in out["cfr"] if r["label"] == "Cash at end of month"):
        bad.append(f"{org}: cash flow doesn't end at the bank")
rule("N5 balance sheets balance with GST, PAYG withholding and super payable", not bad, "; ".join(bad))

# ---- N11: banking days only
bad = [f"{r[1]} {day(r[0])}" for r in rows(tables["fact_cash_daily"]) if not ds.working(day(r[0]))]
rule("N11 no money moves on weekends or Queensland public holidays", not bad, ", ".join(bad[:8]))

print("PROBLEMS:", fails)
sys.exit(1 if fails else 0)
