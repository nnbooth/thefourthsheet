#!/usr/bin/env python3
"""
model_tables.py - STAGE 1: the home-page dashboard model as CSV table rows for the database.

Takes the checked model (financial_model.build()) and returns model_statements, model_fourth_sheet_kpis and
model_assumptions. These used to live in publish_dashboard.py (stage 3), which also needs `statements` and
ORDER, so those now live here and publish_dashboard.py imports them.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]
import financial_model as fm

ORDER = ["trades", "services", "nfp"]


def statements(org, v):
    nfp = org == "nfp"
    o = v["out"]
    return {
        "pnl": {"tab": "P&L", "title": ("Income and expenditure" if nfp else "Profit and loss") + ", September 2026", "rows": o["pnl"]},
        "bs": {"tab": "Balance sheet", "title": "Balance sheet at 30 September 2026", "rows": o["bsr"]},
        "cf": {"tab": "Cash flow", "title": "Cash flow, September 2026", "rows": o["cfr"]},
    }


def csv_tables(res):
    st, kp, asm = [], [], []
    for org in ORDER:
        v = res[org]
        for skey, s in statements(org, v).items():
            for i, rw in enumerate(s["rows"], 1):
                if rw["values"] is None:
                    continue
                for period, val in zip(fm.PERIODS, rw["values"]):
                    st.append([org, skey, s["title"], i, rw["label"], rw["level"], period, val])
        for k in v["fourth"]["kpis"]:
            kp.append([org, k["label"], k["value"], k["sub"]])
        for group, items in v["assumptions"]:
            for item, val in items:
                asm.append([org, group, item, val])
    return {
        "model_statements": ("Home-page dashboard: month-end P&L / income and expenditure, balance sheet and cash flow for the three sample organisations, September 2026 and August 2026, whole dollars. Costs and outflows are negative. level = detail/subtotal/total/key.",
                             ["org", "statement_key", "statement", "line_order", "line", "level", "period", "amount_aud"], st),
        "model_fourth_sheet_kpis": ("Home-page dashboard: the fourth-sheet KPI tiles for September 2026, as displayed.", ["org", "kpi", "value", "comparison"], kp),
        "model_assumptions": ("Home-page dashboard: the assumptions each sample organisation's statements are built from.", ["org", "assumption_group", "assumption", "value"], asm),
    }
