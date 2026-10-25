#!/usr/bin/env python3
"""
statement_lines.py — the layout of each organisation's profit and loss, balance sheet and cash flow, as two tables a
reporting tool (Power BI first) can build the statements from without knowing anything about the chart of accounts:

  statement_line          one row per line of each statement, in the order it prints: headings, the accounts, and the
                          subtotals and totals (line_kind says which). This is what a matrix puts down the left.
  statement_line_account  which accounts make up each line, and with what sign (+1 / -1). An account line is itself;
                          "Total revenue" is the revenue accounts; "Net assets" is the assets less the liabilities.

So a subtotal is never stored and never typed into a formula: it's the sum of its accounts, and adding an account to
the ledger only means adding it to the layout (dim_account), never editing a measure.

How each kind of line is worked out (one rule per kind; an unknown subtotal stops the build until it has a rule):
  value         an account that carries amounts: P&L accounts are posted daily (fact_gl_daily); balance-sheet and
                cash-flow accounts are the ones stored at month end (fact_balance_month, fact_cash_flow_month).
  sum           P&L     "Total <x>" subtotal: the accounts in its section since the last subtotal there.
                        "Total expenses": every account below the income section. Anything else (gross profit, EBITDA,
                        profit before tax, net profit, surplus): every account above it, income + and costs -.
                Balance "Total <x>" subtotal: its section since the last subtotal; "Total <x>" total or key: its whole
                        section above it; "Net assets": assets less liabilities (account codes x1xxx less x2xxx).
                Cash    "Net cash from <x>": its section; "Net change in cash": every flow above it.
  opening_cash  "Cash at start of month": cash at bank at the end of the month before the period.
  closing_cash  "Cash at end of month": cash at bank at the end of the period (the balance sheet's own line).

CHECKED (stops the build if not): every account with amounts is on exactly one value line; every line of the locked
August and September statements comes out to the dollar; every month's balance sheet balances (net assets = equity),
every month's cash flow ends on the balance sheet's cash, and every month's bottom line equals the ledger's profit.

Used by warehouse.py (stage 1), which writes the two tables with the rest of the star schema.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import financial_model as fm

ORGS = ["trades", "services", "nfp"]
STATEMENTS = [("P&L", "pnl"), ("Balance sheet", "bsr"), ("Cash flow", "cfr")]
# which line each statement's checks hang off (and Power BI's check measures find by `role`)
ROLES = {"Net profit after tax": "profit", "Surplus for the month": "profit", "Net assets": "net_assets",
         "Total equity": "equity", "Accumulated funds": "equity", "Net change in cash": "net_change",
         "Cash at start of month": "opening_cash", "Cash at end of month": "closing_cash"}


def month_of(date_key):
    return f"{str(date_key)[:4]}-{str(date_key)[4:6]}"


def prev_month(mo):
    y, m = int(mo[:4]), int(mo[5:])
    return f"{y - (m == 1)}-{12 if m == 1 else m - 1:02d}"


def band(account_id):
    """The account's class from its code: 1 assets, 2 liabilities, 3 equity, 4 income, 5-7 costs, 8 cash flow."""
    return account_id % 10000 // 1000


def rollup(stmt, ln, lines, values, cash_id):
    """[(account_id, factor)] for one computed line, from the lines above it in the same statement."""
    above = [x for x in lines if x["order"] < ln["order"]]
    same = [x for x in above if x["section"] == ln["section"]]
    since = same[max((i + 1 for i, x in enumerate(same) if x["id"] not in values), default=0):]
    label, level = ln["line"], ln["level"]
    pick = lambda xs: [(x["id"], 1) for x in xs if x["id"] in values]          # noqa: E731
    if stmt == "P&L":
        if label == "Total expenses":
            return pick(x for x in above if x["section"] != lines[0]["section"])
        if label.startswith("Total ") and level == "subtotal":
            return pick(since)
        if level in ("total", "key"):
            return pick(above)
    if stmt == "Balance sheet":
        if label == "Net assets":
            return [(x["id"], {1: 1, 2: -1}[band(x["id"])]) for x in above if x["id"] in values and band(x["id"]) in (1, 2)]
        if label.startswith("Total ") and level == "subtotal":
            return pick(since)
        if label.startswith("Total ") and level in ("total", "key"):
            return pick(same)
    if stmt == "Cash flow":
        if label in ("Cash at start of month", "Cash at end of month"):
            return [(cash_id, 1)]
        if label.startswith("Net cash from "):
            return pick(since)
        if label == "Net change in cash":
            return pick(above)
    raise SystemExit(f"statement_lines: no rule for the {stmt} line '{label}' ({level}): add one to rollup()")


def place(rows):
    """Lines the current statements don't print (finished grants: line_order 0) go after the last line of their section
    that ends in the same word ("... grant"), or the section's last detail line. Returns the rows in print order."""
    keyed = []
    for r in rows:
        if r["order"]:
            keyed.append(((r["order"], 0), r))
            continue
        sec = [x for x in rows if x["order"] and x["section"] == r["section"] and x["level"] == "detail"]
        like = [x for x in sec if x["line"].split()[-1] == r["line"].split()[-1]] or sec
        keyed.append(((max(x["order"] for x in like), r["id"]), r))
    return [r for _, r in sorted(keyed, key=lambda k: k[0])]


def build(res, acct_rows, gl, bal, cf):
    """The statement_line and statement_line_account rows, checked (see the module notes)."""
    from warehouse import account_code
    gl_m, bal_m, cf_m = {}, {}, {}
    for r in gl:
        k = (r[1], month_of(r[0]), r[2])
        gl_m[k] = gl_m.get(k, 0) + r[3]
    for src, dst in ((bal, bal_m), (cf, cf_m)):
        for org, mo, aid, amt in src:
            dst[(org, mo, aid)] = dst.get((org, mo, aid), 0) + amt
    carries = {"P&L": {r[0] for r in acct_rows if r[2] == "P&L" and r[7]},
               "Balance sheet": {k[2] for k in bal_m}, "Cash flow": {k[2] for k in cf_m}}
    posted = {k[2] for k in gl_m}
    if posted - carries["P&L"]:
        raise SystemExit(f"statement_lines: the ledger posts to accounts that aren't postable: {sorted(posted - carries['P&L'])}")

    line_rows, acct_out, layout = [], [], {}
    for org in ORGS:
        for stmt, key_ in STATEMENTS:
            lines = sorted(({"id": r[0], "section": r[3], "line": r[4], "level": r[5], "order": r[6]}
                            for r in acct_rows if r[1] == org and r[2] == stmt), key=lambda x: x["order"])
            values = carries[stmt] & {x["id"] for x in lines}
            cash_id = next((r[0] for r in acct_rows if r[1] == org and r[2] == "Balance sheet" and r[4] == "Cash at bank"), None)
            heads = []
            for order, rw in enumerate(res[org]["out"][key_], 1):
                if rw["level"] == "heading":
                    heads.append({"id": account_code(org, rw["label"], rw["label"], 0, stmt), "section": rw["label"],
                                  "line": rw["label"], "level": "heading", "order": order})
            if {h["id"] for h in heads} & {x["id"] for x in lines} or len({h["id"] for h in heads}) != len(heads):
                raise SystemExit(f"statement_lines: {org} {stmt} heading keys clash with account codes")
            for ln in lines:
                ln["parts"] = [(ln["id"], 1)] if ln["id"] in values else rollup(stmt, ln, lines, values, cash_id)
                ln["kind"] = ("value" if ln["id"] in values else "opening_cash" if ln["line"] == "Cash at start of month"
                              else "closing_cash" if ln["line"] == "Cash at end of month" else "sum")
            for h in heads:
                h.update(parts=[], kind="heading")
            ordered = place(heads + lines)
            for n, ln in enumerate(ordered, 1):
                line_rows.append([ln["id"], org, stmt, ln["section"], ln["line"], ln["level"], ln["kind"], n,
                                  ROLES.get(ln["line"]), 0 if ln["order"] == 0 else 1])
                acct_out += [[org, ln["id"], aid, f] for aid, f in ln["parts"]]
            layout[(org, stmt)] = ordered
    check(res, layout, gl_m, bal_m, cf_m)
    return line_rows, acct_out


def amount(stmt, ln, org, mo, gl_m, bal_m, cf_m):
    """One line for one month, the way Power BI's [Amount] measure works it out."""
    if ln["kind"] == "opening_cash":
        return sum(f * bal_m.get((org, prev_month(mo), a), 0) for a, f in ln["parts"])
    src = gl_m if stmt == "P&L" else bal_m if stmt == "Balance sheet" or ln["kind"] == "closing_cash" else cf_m
    return sum(f * src.get((org, mo, a), 0) for a, f in ln["parts"])


def check(res, layout, gl_m, bal_m, cf_m):
    problems = []
    for (org, stmt), lines in layout.items():
        labels = [ln["line"] for ln in lines]
        if len(labels) != len(set(labels)):     # Power BI sorts each label by its line_order: a repeat can't have two
            problems.append(f"{org} {stmt}: a line label appears twice: {sorted({x for x in labels if labels.count(x) > 1})}")
        vals = [a for ln in lines if ln["kind"] == "value" for a, _ in ln["parts"]]
        stored = {k[2] for k in (gl_m if stmt == "P&L" else bal_m if stmt == "Balance sheet" else cf_m) if k[0] == org}
        if sorted(vals) != sorted(set(vals)) or stored - set(vals):
            problems.append(f"{org} {stmt}: accounts with amounts that aren't on exactly one line: {sorted(stored - set(vals))}")
        # the locked months: every line the model prints, to the dollar
        model = {rw["label"]: rw["values"] for rw in res[org]["out"][dict(STATEMENTS)[stmt]] if rw["values"] is not None}
        for i, mo in enumerate(fm.PERIODS):
            for ln in lines:
                if ln["kind"] != "heading" and ln["line"] in model:
                    got = amount(stmt, ln, org, mo, gl_m, bal_m, cf_m)
                    if got != model[ln["line"]][i]:
                        problems.append(f"{org} {mo} {stmt} '{ln['line']}': {got:,} but the statement says {model[ln['line']][i]:,}")
    # every month: the balance sheet balances, the cash flow ends on the balance sheet's cash, the bottom line is the ledger's profit
    for org in ORGS:
        role = {(stmt, ROLES[ln["line"]]): ln for (o, stmt), lines in layout.items() if o == org for ln in lines if ln["line"] in ROLES}
        for mo in sorted({k[1] for k in bal_m if k[0] == org}):
            a = lambda stmt, r: amount(stmt, role[(stmt, r)], org, mo, gl_m, bal_m, cf_m)   # noqa: E731
            if a("Balance sheet", "net_assets") != a("Balance sheet", "equity"):
                problems.append(f"{org} {mo}: net assets {a('Balance sheet', 'net_assets'):,} isn't equity {a('Balance sheet', 'equity'):,}")
            if any(k[0] == org and k[1] == mo for k in cf_m) and \
                    a("Cash flow", "opening_cash") + a("Cash flow", "net_change") != a("Cash flow", "closing_cash"):
                problems.append(f"{org} {mo}: the cash flow doesn't end on the balance sheet's cash")
        for mo in sorted({k[1] for k in gl_m if k[0] == org}):
            ledger = sum(v for k, v in gl_m.items() if k[0] == org and k[1] == mo)
            if amount("P&L", role[("P&L", "profit")], org, mo, gl_m, bal_m, cf_m) != ledger:
                problems.append(f"{org} {mo}: the P&L's bottom line isn't the ledger's profit {ledger:,}")
    if problems:
        raise SystemExit("statement_lines: the statements don't come out of the layout:\n  " + "\n  ".join(problems[:20]))
