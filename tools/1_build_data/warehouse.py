#!/usr/bin/env python3
"""
warehouse.py — the cloud-database version of the home-page sample model.

The dashboard's statements are monthly, but the point of The Fourth Sheet is
seeing the numbers DAILY, not when the accountant closes the month. So the
model's transactions are laid out as a small star schema at daily grain,
ready to load into a cloud database (Azure SQL / SQL Server or PostgreSQL)
and rebuild in Power BI or any other tool:

  Dimensions   dim_date, dim_org, dim_account, dim_job, dim_engagement, dim_grant
  Facts        fact_gl_daily          every P&L posting, by day (job / engagement / grant tagged)
               fact_cash_daily        every cash-flow line, by day
               fact_balance_daily     closing cash and unpaid invoices, every day
               fact_timesheet_daily   technician / consultant hours by job or engagement, by day
               fact_job_month         each trades job: revenue, costs, hours, margin
               fact_engagement_month  each services engagement: hours, revenue, billing, margin
               fact_invoice           every customer invoice with its paid date
               fact_grant_instalment  grant payment schedule
               fact_grant_position    each grant at 30 September 2026

CHECKED: the daily ledger rolls up to every P&L line for August and
September exactly, the daily cash rolls up to every cash-flow line and the
closing balance at each month end equals the balance-sheet cash, and the
daily hours add up to the job and engagement hours. If anything is out, the
build stops.

Used by tools/1_build_data/sample_data.py, which writes the CSVs and schema.sql.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

from datetime import date, timedelta

import data_status as ds
import financial_model as fm
import tax_payroll as tp

FIRST, LAST = date(2024, 10, 1), date(2026, 12, 31)      # 24 months of history, the current quarter, and the forecast horizon
QLD_HOLIDAYS = ds.QLD_HOLIDAYS
GALA = date(2026, 9, 19)                      # NFP spring gala (Saturday)
ORG_SECTOR = {"trades": "SME", "services": "SME", "nfp": "Not-for-profit"}


def days(mo):
    d, out = fm.month_start(mo), []
    while d.strftime("%Y-%m") == mo:
        out.append(d)
        d += timedelta(days=1)
    return out


def working(d):
    return d.weekday() < 5 and d not in QLD_HOLIDAYS


def wdays(mo):
    return [d for d in days(mo) if working(d)]


def allocate(total, weights):
    """Split an integer total in proportion to weights; parts always add back exactly."""
    sign, total = (-1 if total < 0 else 1), abs(total)
    tw = sum(weights)
    raw = [total * w / tw for w in weights]
    parts = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - parts[i], reverse=True)[: total - sum(parts)]:
        parts[i] += 1
    return [sign * p for p in parts]


def spread(total, dates):
    return list(zip(dates, allocate(total, [1] * len(dates))))


def key(d):
    return int(d.strftime("%Y%m%d"))


# ------------------------------------------------------------------- dimensions

def locked_on(mo):
    """The day the month was locked (the period-lock register), or None while it isn't."""
    d = ds.lock_date(mo)
    return d.isoformat() if d else None


def dim_date():
    rows, d = [], FIRST
    while d <= LAST:
        fy = d.year + 1 if d.month >= 7 else d.year
        fy_m = (d.month - 7) % 12 + 1
        rows.append([key(d), d.isoformat(), d.day, d.strftime("%a"), d.weekday() + 1, 1 if d.weekday() >= 5 else 0, 1 if working(d) else 0,
                     QLD_HOLIDAYS.get(d), (d - timedelta(days=d.weekday())).isoformat(), d.isocalendar()[1],
                     d.strftime("%Y-%m"), d.strftime("%b %Y"), f"Q{(d.month - 1) // 3 + 1} {d.year}",
                     f"FY{fy}", fy_m, f"FY{fy} Q{(fy_m - 1) // 3 + 1}",
                     ds.day_status(d), ds.month_status(d.strftime("%Y-%m"))[0], locked_on(d.strftime("%Y-%m")),
                     ds.AS_AT.strftime("%Y-%m-%d %H:%M")])
        d += timedelta(days=1)
    return rows


ORG_DIGIT = {"trades": 1, "services": 2, "nfp": 3}
SECTION_BASE = {"Current assets": 1000, "Current liabilities": 2000, "Equity": 3000, "Revenue": 4000, "Income": 4000,
                "Cost of sales": 5000, "Programs": 5000, "Operating expenses": 6000, "Fundraising": 6000, "Administration": 6500,
                "Operating activities": 8000, "Investing activities": 8500, "Financing activities": 8800}


def account_code(org, section, label, k, stmt="P&L"):
    """A chart-of-accounts code: the organisation's digit, then the account (assets 1xxx, liabilities 2xxx, equity 3xxx,
    income 4xxx, direct costs 5xxx, overheads 6xxx, depreciation, interest and tax 7xxx, cash-flow lines 8xxx),
    10 apart within a section, as a bookkeeper would number them."""
    below_line = stmt == "P&L" and (label in ("Depreciation", "Interest") or label.startswith("Income tax"))
    base = 7000 if below_line else SECTION_BASE.get(section, 9000)
    return ORG_DIGIT[org] * 10000 + base + 10 * k


def accounts(res):
    """dim_account: every line of every statement, with its chart-of-accounts code (account_code)."""
    rows, ids = [], {}
    for org in ["trades", "services", "nfp"]:
        out = res[org]["out"]
        for stmt, key_ in [("P&L", "pnl"), ("Balance sheet", "bsr"), ("Cash flow", "cfr")]:
            section, used = "", {}
            for order, rw in enumerate(out[key_], 1):
                if rw["level"] == "heading":
                    section = rw["label"]
                    continue
                band = account_code(org, section, rw["label"], 0, stmt)
                used[band] = used.get(band, 0) + 1
                n = account_code(org, section, rw["label"], used[band], stmt)
                ids[(org, key_, rw["label"])] = n
                postable = 1 if rw["level"] == "detail" or (key_ == "pnl" and rw["level"] == "subtotal" and
                                                          (rw["label"] in ("Depreciation", "Interest") or rw["label"].startswith("Income tax"))) else 0
                rows.append([n, org, stmt, section, rw["label"], rw["level"], order, postable])
    return rows, ids


# ------------------------------------------------------------- daily ledger

def pattern(org, label, mo):
    """Which days a P&L line falls on, for lines not built from jobs/engagements/grants."""
    if any(s in label for s in ("Rent", "Occupancy", "Insurance", "IT and software", "indemnity")):
        return [fm.month_start(mo)]
    if label in ("Depreciation", "Interest") or label.startswith("Income tax"):
        return [ds.month_end(mo)]
    if label in ("Fundraising events", "Event costs") and mo == "2026-09":
        return [GALA]
    if label == "Donations":
        return days(mo)
    return wdays(mo)


def gl_daily(res, acct):
    rows = []   # [date_key, org, account_id, amount, job_id, engagement_id, grant_id]

    def post(d, org, label, amount, job=None, eng=None, grant=None):
        if amount:
            rows.append([key(d), org, acct[(org, "pnl", label)], amount, job, eng, grant])

    # trades: revenue and job costs straight from each job, on its invoice date
    t = res["trades"]["out"]
    rev_line = {"Maintenance contract": next(rw["label"] for rw in t["pnl"] if rw["label"].startswith("Maintenance contracts")),
                "Installation": "Installations (jobs)", "Call-out": "Call-outs and repairs"}
    for j in t["jobs"]:
        if j["month"] in fm.PERIODS:
            if j["type"] == "Call-out":
                post(j["invoice_date"], "trades", "Call-outs: technician time", j["labour_revenue"], job=j["job"])
                post(j["invoice_date"], "trades", "Call-outs: materials charged", j["materials_revenue"], job=j["job"])
            else:
                post(j["invoice_date"], "trades", rev_line[j["type"]], j["revenue"], job=j["job"])
            post(j["invoice_date"], "trades", "Materials", -j["materials"], job=j["job"])
            post(j["invoice_date"], "trades", "Subcontractors", -j["subcontractors"], job=j["job"])
    done = {("trades", l) for l in list(rev_line.values()) + ["Call-outs: technician time", "Call-outs: materials charged", "Materials", "Subcontractors"]}

    # services: project revenue follows the hours worked each day; retainers on the 1st; training on the day
    s = res["services"]["out"]
    for x in s["engagements"]:
        mo, code = x["month"], x["code"]
        if x["type"] == "Project":
            for d, amt in zip(*_eng_days(x)):
                post(d, "services", "Projects (hours worked)", amt, eng=code)
        elif x["type"] == "Retainer":
            post(fm.month_start(mo), "services", "Retainers", x["revenue"], eng=code)
        else:
            post(_training_day(x), "services", "Training", x["revenue"], eng=code)
        if x["contractors"]:
            post(wdays(mo)[-1], "services", "Contractors", -x["contractors"], eng=code)
    done |= {("services", l) for l in ("Projects (hours worked)", "Retainers", "Training", "Contractors")}

    # nfp: each grant's spend (= grant income) spread over the working days
    n = res["nfp"]["out"]
    for gr in fm.NFP["grants"]:
        label = f"{gr[2]} grant"
        for mo, spend in [("2026-08", gr[9]), ("2026-09", gr[10])]:
            for d, amt in spread(spend, wdays(mo)):
                post(d, "nfp", label, amt, grant=gr[0])
        done.add(("nfp", label))

    # everything else: by its pattern
    for org in ["trades", "services", "nfp"]:
        for rw in res[org]["out"]["pnl"]:
            if rw["values"] is None or (org, rw["label"]) in done or (org, "pnl", rw["label"]) not in acct:
                continue
            postable = rw["level"] == "detail" or rw["label"] in ("Depreciation", "Interest") or rw["label"].startswith("Income tax")
            if not postable:
                continue
            for i, mo in enumerate(fm.PERIODS):
                for d, amt in spread(rw["values"][i], pattern(org, rw["label"], mo)):
                    post(d, org, rw["label"], amt)
    return rows


def _eng_days(x):
    ds = wdays(x["month"])
    halves = allocate(int(x["hours"] * 2), [1] * len(ds))
    keep = [(d, h) for d, h in zip(ds, halves) if h]
    return [d for d, _ in keep], allocate(x["revenue"], [h for _, h in keep])


def _training_day(x):
    ds = wdays(x["month"])
    return ds[(int(x["code"][2:]) * 3) % len(ds)]


# --------------------------------------------------------------- timesheets

def timesheets(res):
    rows = []   # [date_key, org, job_id, engagement_id, hours]
    for j in res["trades"]["out"]["jobs"]:
        if j["month"] not in fm.PERIODS:
            continue
        if j["type"] == "Call-out":
            rows.append([key(j["invoice_date"]), "trades", j["job"], None, j["hours"]])
            continue
        ds = wdays(j["month"])
        if j["type"] == "Installation":   # the working days leading up to completion
            ds = [d for d in ds if d <= j["invoice_date"]][-5:] or ds[:1]
        for d, h in zip(ds, allocate(int(j["hours"] * 2), [1] * len(ds))):
            if h:
                rows.append([key(d), "trades", j["job"], None, h / 2])
    for x in res["services"]["out"]["engagements"]:
        if x["type"] == "Project":
            ds = wdays(x["month"])
            pairs = zip(ds, allocate(int(x["hours"] * 2), [1] * len(ds)))
        elif x["type"] == "Training":
            d0 = _training_day(x)
            pairs = [(d0, int(x["hours"] * 2))]
        else:
            ds = wdays(x["month"])
            pairs = zip(ds, allocate(int(x["hours"] * 2), [1] * len(ds)))
        for d, h in pairs:
            if h:
                rows.append([key(d), "services", None, x["code"], h / 2])
    return rows


# ---------------------------------------------------------------- daily cash

def cash_pattern(org, label, mo):
    """Which days a cash-flow line moves on: always banking days (no weekends or Queensland public holidays)."""
    if label.startswith("Interest"):
        return wdays(mo)[-1:]                     # the last banking day of the month
    if label == "Payments to employees":
        return tp.pay_days_in(mo)
    if label.startswith("Payments to"):          # supplier runs on the 15th and the last working day
        return [d for d in wdays(mo) if d.day >= 15][:1] + wdays(mo)[-1:]
    if label.startswith("Purchase of"):
        return [d for d in wdays(mo) if d.day >= 10][:1]
    if label.endswith("repaid"):
        return [d for d in wdays(mo) if d.day >= 28][:1] or wdays(mo)[-1:]
    if label == "Program fees received":
        return wdays(mo)
    return wdays(mo)


def cash_daily(res, acct):
    rows, bal = [], []   # fact_cash_daily, fact_balance_daily
    for org in ["trades", "services", "nfp"]:
        out = res[org]["out"]
        invoices = out["jobs"] if org == "trades" else out.get("invoices", [])
        flows = {}
        for rw in out["cfr"]:
            if rw["level"] != "detail":
                continue
            for i, mo in enumerate(fm.PERIODS):
                label, total = rw["label"], rw["values"][i]
                if label.startswith("Receipts from customers"):
                    parts = {}
                    for inv in invoices:
                        if inv["paid_date"].strftime("%Y-%m") == mo:
                            parts[inv["paid_date"]] = parts.get(inv["paid_date"], 0) + inv["amount"]
                    pairs = sorted(parts.items())
                elif label == "Grant instalments received":
                    pairs = [(dt, a) for gr in fm.NFP["grants"] for dt, a in gr[7] if dt.strftime("%Y-%m") == mo]
                elif label == "Donations and fundraising received":
                    don = fm.NFP["income"]["Donations"][mo]
                    ev = fm.NFP["income"]["Fundraising events"][mo]
                    pairs = spread(don, wdays(mo)) + ([(tp.next_banking_day(GALA), tp.with_gst(ev))] if ev else [])   # the gala's takings bank on Monday
                else:
                    pairs = spread(total, cash_pattern(org, label, mo))
                for d, amt in pairs:
                    if amt:
                        rows.append([key(d), org, acct[(org, "cfr", label)], amt])
                        flows[d] = flows.get(d, 0) + amt
        cash = out["bs"]["2026-07"]["cash"]
        for mo in ["2026-08", "2026-09"]:
            for d in days(mo):
                cash += flows.get(d, 0)
                debt = fm.unpaid_at(invoices, d) if invoices else None
                bal.append([key(d), org, cash, debt])
    return rows, bal


# ------------------------------------------------------------------- build

def build(res):
    acct_rows, acct = accounts(res)
    gl = gl_daily(res, acct)
    ts = timesheets(res)
    cf, bal = cash_daily(res, acct)
    check(res, acct, gl, ts, cf, bal)          # August and September, against the locked statements

    # ---- 24 months of history and October to date (never touches August or September)
    import history
    h = history.build(res)
    for org, label in h["extra_accounts"]:          # ledger lines that only exist in history (finished grants): more income accounts
        if (org, "pnl", label) not in acct:
            band = ORG_DIGIT[org] * 10000 + 4000
            nid = max(v for v in acct.values() if band <= v < band + 1000) + 10
            acct[(org, "pnl", label)] = nid
            acct_rows.append([nid, org, "P&L", "Income", label, "detail", 0, 1])
    for d, org, label, amt, job, eng, grant in h["gl"]:
        if (org, "pnl", label) not in acct:
            raise SystemExit(f"history posts to an unknown line: {org} {label}")
        gl.append([key(d), org, acct[(org, "pnl", label)], amt, job, eng, grant])
    ts += [[key(d), org, j, e, hrs] for d, org, j, e, hrs in h["ts"]]
    cf += [[key(d), org, acct[(org, "cfr", label)], amt] for d, org, label, amt in h["cash"]]
    bal += [[key(d), org, c, debt] for d, org, c, debt in h["bal"]]
    if any(d.strftime("%Y-%m") in ("2026-08", "2026-09") for d, *_ in h["gl"]):
        raise SystemExit("history tried to post into a locked month")
    build.history = h

    t, s, n = res["trades"]["out"], res["services"]["out"], res["nfp"]["out"]
    seen, dim_job = set(), []
    for j in t["jobs"]:
        if j["job"] not in seen:
            seen.add(j["job"])
            dim_job.append([j["job"], "trades", j["type"], j["description"]])
    for j in h["jobs"]:
        if j["job"] not in seen:
            seen.add(j["job"])
            dim_job.append([j["job"], "trades", j["type"], j["description"]])
    dim_eng = [[e[0], "services", e[1], e[2], e[3] if e[1] == "Project" else None, e[3] if e[1] != "Project" else None, e[4]]
               for e in fm.SERVICES["engagements"]]
    have = {e[0] for e in dim_eng}
    for x in h["eng"]:
        if x["code"] not in have:
            have.add(x["code"])
            hs = next((e for e in history.SERVICES_HISTORY if e[0] == x["code"]), None)
            rate = hs[3] if hs else x["revenue"]
            dim_eng.append([x["code"], "services", x["type"], x["description"], rate if x["type"] == "Project" else None,
                            rate if x["type"] != "Project" else None, 14 if x["type"] == "Retainer" else 30])
    dim_grant = [[g["code"], "nfp", g["program"], g["funder"], g["total"], g["start"], g["end"]] for g in n["grants"]]
    dim_grant += [[g[0], "nfp", g[2], g[3], g[4], g[5].isoformat(), g[6].isoformat()] for g in h["past_grants"]]
    job_month = [[j["month"], j["job"], j["invoice_date"].isoformat(), j["revenue"], j["labour_revenue"], j["materials_revenue"], j["materials"], j["subcontractors"], j["hours"],
                  j["labour_cost"], j["gross_profit"]] for j in t["jobs"] + h["jobs"]]
    eng_month = [[x["month"], x["code"], x["hours"], x["revenue"], x["billed"], x["contractors"], x["allocated_cost"], x["contribution"],
                  s["r"][x["month"]]["wip"].get(x["code"], 0) if x["type"] == "Project" else 0] for x in s["engagements"]]
    eng_month += [[x["month"], x["code"], x["hours"], x["revenue"], None if x["month"] in history.MODEL_MONTHS else x["billed"], x["contractors"],
                   x["allocated_cost"], x["contribution"], None] for x in h["eng"]]     # May to July 2026 were billed by the model's monthly invoices
    invoices = [["trades", f"INV-{j['job']}-{j['month'][5:]}", j["job"], None, j["invoice_date"].isoformat(), j["paid_date"].isoformat(), j["amount"]]
                for j in t["jobs"] + [j for j in h["jobs"] if j["month"] != "2026-10" or j["invoice_date"] <= history.AS_AT]]
    invoices += [["services", i["invoice"], None, i["code"], i["invoice_date"].isoformat(), i["paid_date"].isoformat(), i["amount"]] for i in h["eng_inv"]
                 if not (history.MODEL_MONTHS[0] <= i["invoice_date"].strftime("%Y-%m") <= history.MODEL_MONTHS[-1])]   # May to July: the model's invoices (below)
    invoices += [["services", i["invoice"], None, None if i["code"] == "earlier" else i["code"], i["invoice_date"].isoformat(),
                  i["paid_date"].isoformat(), i["amount"]] for i in s["invoices"]]
    # invoice numbers come from each business's own billing sequence, in the order the invoices were issued
    from ids import Running
    seq = {"trades": Running(204_117, "trades-invoice", skip=0.01), "services": Running(8_812, "services-invoice", skip=0.01)}
    for inv in sorted(invoices, key=lambda r: (r[0], r[4], r[1])):
        inv[1] = f"INV-{seq[inv[0]].next()}"
    instal = [[gr[0], key(d), a] for gr in fm.NFP["grants"] for d, a in gr[7]]
    gpos = [[g["code"], 20260930, g["received_to_date"], g["spent_to_date"], g["budget_to_date"], g["spend_vs_budget_pct"],
             g["unspent"], g["balance_30_sep"], g["months_left"]] for g in n["grants"]]
    orgs = [[o, res[o]["model"]["name"], res[o]["model"]["long_name"], ORG_SECTOR[o], res[o]["model"]["about"]] for o in ["trades", "services", "nfp"]]
    orgs.append(["distribution", "Deliveries", "Sample Distribution Pty Ltd", "SME", "A distribution centre at Wacol, Brisbane: deliveries out to customers across south-east Queensland and in from suppliers (the map on Our work)."])
    build.account_ids = acct
    acct_label = {v: k[2] for k, v in acct.items()}

    T = {}
    def tbl(name, desc, cols, rows):
        T[name] = (desc, [c[0] for c in cols], rows, cols)
    V = lambda n: f"VARCHAR({n})"
    tbl("dim_date", "Calendar, 1 Oct 2024 to 31 Dec 2026: the drill-down path from financial year to quarter, month, week and day, with Brisbane working days and public holidays. date_key = yyyymmdd; weeks start Monday. Data status as at the run: day_status / month_status = Locked (month closed), Provisional (over but not locked), Incomplete (today / month to date) or Future; a month is locked when someone locks it (period_lock); month_locked_on is blank until then.",
        [("date_key", "INT PRIMARY KEY"), ("calendar_date", "DATE NOT NULL"), ("day_of_month", "INT"), ("day_name", V(3)),
         ("day_of_week", "INT"), ("is_weekend", "INT"), ("is_working_day", "INT"), ("public_holiday", V(60)),
         ("week_start", "DATE"), ("iso_week", "INT"), ("month_key", V(7)), ("month_name", V(8)), ("calendar_quarter", V(7)),
         ("financial_year", V(6)), ("fy_month_no", "INT"), ("fy_quarter", V(10)),
         ("day_status", V(12)), ("month_status", V(12)), ("month_locked_on", "DATE"), ("status_as_at", V(16))], dim_date())
    tbl("dim_org", "The three sample organisations.",
        [("org_id", V(12) + " PRIMARY KEY"), ("toggle_name", V(30)), ("legal_name", V(60)), ("sector", V(20)), ("about", V(300))], orgs)
    tbl("dim_account", "Every statement line for each organisation (P&L, balance sheet, cash flow). is_postable = daily facts post to it; the rest are subtotals and totals.",
        [("account_id", "INT PRIMARY KEY"), ("org_id", V(10) + " REFERENCES dim_org(org_id)"), ("statement", V(20)), ("section", V(40)),
         ("line", V(60)), ("line_level", V(10)), ("line_order", "INT"), ("is_postable", "INT")], acct_rows)
    tbl("dim_job", "Trades jobs: maintenance contracts (one id per customer, billed monthly), installations and call-outs.",
        [("job_id", V(10) + " PRIMARY KEY"), ("org_id", V(10) + " REFERENCES dim_org(org_id)"), ("job_type", V(30)), ("description", V(80))], dim_job)
    tbl("dim_engagement", "Services client engagements. rate_or_fee: hourly rate for projects, fixed fee for retainers (monthly) and training.",
        [("engagement_id", V(10) + " PRIMARY KEY"), ("org_id", V(10) + " REFERENCES dim_org(org_id)"), ("engagement_type", V(20)),
         ("description", V(80)), ("hourly_rate", "INT"), ("fixed_fee", "INT"), ("payment_days", "INT")], dim_eng)
    tbl("dim_grant", "Not-for-profit grants.",
        [("grant_id", V(10) + " PRIMARY KEY"), ("org_id", V(10) + " REFERENCES dim_org(org_id)"), ("program", V(60)), ("funder", V(60)),
         ("grant_total", "INT"), ("start_date", "DATE"), ("end_date", "DATE")], dim_grant)
    tbl("fact_gl_daily", "Daily P&L postings, Oct 2024 to 6 Oct 2026 (income +, costs -). August and September equal the locked P&L to the dollar; October is incomplete. Tagged with the job, engagement or grant where there is one.",
        [("date_key", "INT REFERENCES dim_date(date_key)"), ("org_id", V(10) + " REFERENCES dim_org(org_id)"),
         ("account_id", "INT REFERENCES dim_account(account_id)"), ("amount", "INT"), ("job_id", V(10)), ("engagement_id", V(10)), ("grant_id", V(10))], gl)
    tbl("fact_cash_daily", "Daily cash movements by cash-flow line, Aug 2026 to 6 Oct 2026 (in +, out -). Customer receipts are the actual invoice payment dates.",
        [("date_key", "INT REFERENCES dim_date(date_key)"), ("org_id", V(10) + " REFERENCES dim_org(org_id)"),
         ("account_id", "INT REFERENCES dim_account(account_id)"), ("amount", "INT")], cf)
    tbl("fact_balance_daily", "Closing cash at bank and unpaid customer invoices at the end of every day, Aug 2026 to 6 Oct 2026. Month-end values equal the balance sheet.",
        [("date_key", "INT REFERENCES dim_date(date_key)"), ("org_id", V(10) + " REFERENCES dim_org(org_id)"), ("cash_at_bank", "INT"), ("unpaid_invoices", "INT")], bal)
    tbl("fact_timesheet_daily", "Hours by day against each trades job or services engagement, Oct 2024 to 6 Oct 2026 (half-hour units). Add up to the job and engagement hours.",
        [("date_key", "INT REFERENCES dim_date(date_key)"), ("org_id", V(10) + " REFERENCES dim_org(org_id)"),
         ("job_id", V(10)), ("engagement_id", V(10)), ("hours", "DECIMAL(6,1)")], ts)
    tbl("fact_job_month", "Each trades job by month, Oct 2024 to Sep 2026 plus October to date. Labour cost = hours x $68. Aug and Sep add up to the P&L. "
        f"Call-outs bill technician time (${fm.TRADES['callout_rate']}/hour) and materials (cost x {fm.TRADES['materials_markup']}) separately: labour_revenue + materials_revenue = revenue; blank for other jobs (one price). "
        "Revenue excludes GST (the invoice adds 10%).",
        [("month_key", V(7)), ("job_id", V(10) + " REFERENCES dim_job(job_id)"), ("invoice_date", "DATE"), ("revenue", "INT"),
         ("labour_revenue", "INT"), ("materials_revenue", "INT"), ("materials", "INT"),
         ("subcontractors", "INT"), ("tech_hours", "DECIMAL(6,1)"), ("labour_cost", "INT"), ("gross_profit", "INT")], job_month)
    tbl("fact_engagement_month", "Each services engagement by month, Oct 2024 to Sep 2026 plus October to date. Consultant time costed at $60/hour; wip_closing = unbilled project time at month end (August and September; every month's total is in fact_balance_month). billed is blank for May to July 2026: those months were billed in monthly invoices, not by engagement (fact_invoice).",
        [("month_key", V(7)), ("engagement_id", V(10) + " REFERENCES dim_engagement(engagement_id)"), ("hours", "DECIMAL(6,1)"), ("revenue", "INT"),
         ("billed", "INT"), ("contractors", "INT"), ("consultant_time_cost", "INT"), ("contribution", "INT"), ("wip_closing", "INT")], eng_month)
    tbl("fact_invoice", "Every customer invoice, Oct 2024 to 6 Oct 2026, with the date it was paid (always a banking day). amount includes GST (10%); revenue in the P&L doesn't. Unpaid at a date = debtors at that date.",
        [("org_id", V(10) + " REFERENCES dim_org(org_id)"), ("invoice_id", V(20)), ("job_id", V(10)), ("engagement_id", V(10)),
         ("invoice_date", "DATE"), ("paid_date", "DATE"), ("amount", "INT")], invoices)
    tbl("fact_grant_instalment", "Grant payment schedule (banking days). amount excludes GST: the funder pays it plus 10% GST.",
        [("grant_id", V(10) + " REFERENCES dim_grant(grant_id)"), ("date_key", "INT REFERENCES dim_date(date_key)"), ("amount", "INT")],
        [r for r in instal if FIRST <= date(r[1] // 10000, r[1] // 100 % 100, r[1] % 100) <= LAST])
    gsm = [[g["code"], x["month"], x["spend"], x["budget"]] for g in n["grants"] for x in g["monthly"]]
    current = {g["code"] for g in n["grants"]}
    past_budget = {g[0]: round(g[4] / len(history.grant_months(g[5], g[6]))) for g in h["past_grants"]}
    oct_spend = {}
    for code, mo, amt in h["grant_month"]:
        if mo == "2026-10":
            oct_spend[code] = oct_spend.get(code, 0) + amt
        elif code not in current:
            gsm.append([code, mo, amt, past_budget[code]])
    gsm += [[code, "2026-10", amt, next((x["budget"] for g in n["grants"] if g["code"] == code for x in [{"budget": g["budget_by_month"].get("2026-10", 0)}]), 0)]
            for code, amt in oct_spend.items()]
    tbl("fact_grant_spend_month", "Each grant's spend (= grant income) and budget by month, Oct 2024 to Sep 2026 plus October 2026 to date (incomplete), including grants that have finished. Current grants: spend adds up to spent_to_date at 30 Sep.",
        [("grant_id", V(10) + " REFERENCES dim_grant(grant_id)"), ("month_key", V(7)), ("spend", "INT"), ("budget", "INT")], gsm)
    # revenue, cost and margin by product / service line / income source, by month
    by_ml = {}
    for r_ in gl:
        if r_[1] == "nfp":
            mo = f"{str(r_[0])[:4]}-{str(r_[0])[4:6]}"
            lab = acct_label[r_[2]]
            by_ml.setdefault(mo, {})
            by_ml[mo][lab] = by_ml[mo].get(lab, 0) + r_[3]
    lm = h["lines"] + history.nfp_line_month(by_ml, history.HIST + ["2026-08", "2026-09", "2026-10"])
    tbl("fact_line_month", "Revenue, direct cost and gross margin (before overheads: not profit) by product or service line (trades, services) or income source (not-for-profit), by month, Oct 2024 to Sep 2026 plus October to date. Trades direct cost = materials, subcontractors and technician time at $68/h (wages and all on-costs); services = contractors and consultant time at $60/h (wages and all on-costs); not-for-profit = the cost of raising it. status = Locked / Provisional / Incomplete.",
        [("org_id", V(12) + " REFERENCES dim_org(org_id)"), ("month_key", V(7)), ("month_status", V(12)), ("line", V(40)), ("items", "INT"),
         ("revenue", "INT"), ("direct_cost", "INT"), ("gross_margin", "INT")], lm)
    check_history(res, lm)
    build.line_month, build.nfp_by_month, build.gsm = lm, by_ml, gsm

    # ---- the balance sheet and cash flow at every month end (month_end.py), with the history's profit checked against the ledger
    import month_end
    closes, bal_m, cf_m = month_end.build(res)
    led = {}
    for r_ in gl:
        mo = f"{str(r_[0])[:4]}-{str(r_[0])[4:6]}"
        led[(r_[1], mo)] = led.get((r_[1], mo), 0) + r_[3]
    for org, c in closes.items():
        for mo, p_ in c["pnl"].items():
            got = p_["surplus"] if org == "nfp" else p_["npat"]
            if got != led.get((org, mo), 0):
                raise SystemExit(f"month_end {org} {mo}: profit {got} isn't the ledger's {led.get((org, mo), 0)}")
    tbl("fact_balance_month", "Every balance-sheet line at every month end, 31 Oct 2024 to 30 Sep 2026 (whole dollars; assets, liabilities and equity all positive). "
        "August and September 2026 are the locked statements; earlier months are closed the same way (month_end.py) and join them at 31 July 2026 to the dollar. "
        "Totals and subtotals aren't stored: add the lines up (dim_account.section).",
        [("org_id", V(10) + " REFERENCES dim_org(org_id)"), ("month_key", V(7)), ("account_id", "INT REFERENCES dim_account(account_id)"), ("amount", "INT")],
        [[o, m, acct[(o, "bsr", line)], a] for o, m, line, a in bal_m])
    tbl("fact_cash_flow_month", "Every cash-flow line for every month, Nov 2024 to Sep 2026 (direct method: in +, out -). Cash at the start of the month + these = "
        "cash at the end (fact_balance_month). Each line is what was earned or incurred less the change in what's owed.",
        [("org_id", V(10) + " REFERENCES dim_org(org_id)"), ("month_key", V(7)), ("account_id", "INT REFERENCES dim_account(account_id)"), ("amount", "INT")],
        [[o, m, acct[(o, "cfr", line)], a] for o, m, line, a in cf_m])
    build.closes = closes
    build.balance_daily = bal
    tbl("fact_grant_position", "Each grant at 30 Sep 2026: received, spent, budget to date, still to spend. balance = received - spent (+ in advance, - receivable).",
        [("grant_id", V(10) + " REFERENCES dim_grant(grant_id)"), ("date_key", "INT"), ("received_to_date", "INT"), ("spent_to_date", "INT"),
         ("budget_to_date", "INT"), ("spend_vs_budget_pct", "DECIMAL(6,1)"), ("still_to_spend", "INT"), ("balance", "INT"), ("months_left", "INT")], gpos)
    return T


def check_history(res, lm):
    """The line table agrees with the locked statements for August and September."""
    problems = []
    for org, labels in (("trades", ["Maintenance contracts", "Installations", "Call-outs and repairs"]), ("services", ["Projects", "Retainers", "Training"])):
        pnl_ = res[org]["out"]["pnl"]
        rev_rows = pnl_[1:next(i for i, rw in enumerate(pnl_) if rw["label"] == "Total revenue")]
        for i, mo in enumerate(fm.PERIODS):
            got = sum(r[5] for r in lm if r[0] == org and r[1] == mo)
            exp = sum(rw["values"][i] for rw in rev_rows)
            if got != exp:
                problems.append(f"line revenue {org} {mo}: {got} vs {exp}")
    for i, mo in enumerate(fm.PERIODS):
        got = sum(r[5] for r in lm if r[0] == "nfp" and r[1] == mo)
        r_ = res["nfp"]["out"]["r"][mo]
        exp = r_["grant_income"] + r_["other_income"]["Donations"] + r_["other_income"]["Fundraising events"] + r_["other_income"]["Program fees"]
        if got != exp:
            problems.append(f"line income nfp {mo}: {got} vs {exp}")
    if problems:
        raise SystemExit("History checks FAILED:\n  " + "\n  ".join(problems))


def check(res, acct, gl, ts, cf, bal):
    problems = []
    inv = {v: k for k, v in acct.items()}
    for org in ["trades", "services", "nfp"]:
        out = res[org]["out"]
        for k_, rows_, facts in [("pnl", out["pnl"], gl), ("cfr", out["cfr"], cf)]:
            for rw in rows_:
                if (org, k_, rw["label"]) not in acct or rw["values"] is None:
                    continue
                aid = acct[(org, k_, rw["label"])]
                posted = [f for f in facts if f[2] == aid]
                if not posted and rw["level"] != "detail" and k_ == "pnl" and not (rw["label"] in ("Depreciation", "Interest") or rw["label"].startswith("Income tax")):
                    continue
                if k_ == "cfr" and rw["level"] != "detail":
                    continue
                for i, mo in enumerate(fm.PERIODS):
                    tot = sum(f[3] for f in posted if str(f[0]).startswith(mo.replace("-", "")))
                    if tot != rw["values"][i]:
                        problems.append(f"{org} {k_} '{rw['label']}' {mo}: daily {tot} vs statement {rw['values'][i]}")
        for mo in fm.PERIODS:
            end = key(fm.MONTH_END[mo])
            b = next(x for x in bal if x[0] == end and x[1] == org)
            if b[2] != out["bs"][mo]["cash"]:
                problems.append(f"{org} daily cash {mo}: {b[2]} vs balance sheet {out['bs'][mo]['cash']}")
            if org != "nfp" and b[3] != out["bs"][mo]["debtors"]:
                problems.append(f"{org} daily debtors {mo}")
        low = min(x[2] for x in bal if x[1] == org)
        if low < 0:
            problems.append(f"{org} daily cash goes negative ({low})")
    for j in res["trades"]["out"]["jobs"]:
        if j["month"] in fm.PERIODS:
            h = sum(r[4] for r in ts if r[2] == j["job"] and str(r[0])[:6] == j["month"].replace("-", ""))
            if abs(h - j["hours"]) > 1e-9:
                problems.append(f"timesheet {j['job']} {j['month']}: {h} vs {j['hours']}")
    for x in res["services"]["out"]["engagements"]:
        h = sum(r[4] for r in ts if r[3] == x["code"] and str(r[0])[:6] == x["month"].replace("-", ""))
        if abs(h - x["hours"]) > 1e-9:
            problems.append(f"timesheet {x['code']} {x['month']}")
    if problems:
        raise SystemExit("Daily data checks FAILED:\n  " + "\n  ".join(problems[:40]))


if __name__ == "__main__":
    T = build(fm.build())
    for name, (desc, cols, rows, _) in T.items():
        print(f"{name:24} {len(rows):6} rows")
    print("All daily checks passed.")
