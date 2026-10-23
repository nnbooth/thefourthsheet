#!/usr/bin/env python3
"""
sample_data.py — the sample data behind every mock-up dashboard and report.

ONE place for the invented "Sample Co" numbers shown on the website:
  - the home-page dashboard: three sample organisations' P&L, balance sheet,
    cash flow and fourth sheet (calculated by tools/1_build_data/financial_model.py; the
    website's data/dashboard.json and Excel/PDF exports are written later, in stage 3)
  - the live-display screens (warehouse, reception, boardroom)
  - the report previews (sales, purchasing, payroll and overtime)
  - the management-pack template (profit and loss)

Run from the repo root:   python3 tools/1_build_data/sample_data.py
STAGE 1 of 3: this program only makes the raw data. It does not touch the website (that is 3_publish_site/build_site.py)
and does not touch Azure (that is 2_load_azure/database/load.py).
It writes, into the OneDrive Data folder (one subfolder per task; not git):
  - one CSV per table (tidy: one row per thing, plain numbers, ISO dates)
  - schema.sql with a CREATE TABLE for each CSV (works in Azure SQL / SQL
    Server and PostgreSQL)
  - it also checks the key figures still appear in the mock-up pages, so the
    pictures and the data don't drift apart. If you change a number here,
    change the mock-up (tools/mockups/*.html or DASH_DATA in script.js) too.

All money is AUD. All data is invented sample data.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import csv
import os
import sys
from datetime import date, timedelta
from pathlib import Path
import winutf8; winutf8.ensure()   # Windows: run in UTF-8 mode (the tools write characters like ¢ and ▲)

REPO = Path(__file__).resolve().parent.parent.parent
# Data lives in OneDrive, not in git (set FOURTH_SHEET_DATA to use another folder).
def _data_root():
    """The Fourth Sheet's OneDrive Data folder, on a Mac or a Windows PC."""
    if os.getenv("FOURTH_SHEET_DATA"):
        return Path(os.getenv("FOURTH_SHEET_DATA")).expanduser()
    from sync_media import onedrive_root      # one finder for every tool: Mac or PC, personal or business OneDrive
    return onedrive_root() / "Data"


DATA_ROOT = _data_root()
DOCS = DATA_ROOT.parent / "Data documentation"     # schema.sql and table descriptions (Data/ holds data only)

# Which folder of Data/ each table goes in: one folder per task, plus Common for shared tables.
FOLDERS = [
    ("Common", ("dim_date", "dim_org", "target", "simulation_parameter", "period_lock")),
    ("Deliveries map", ("dim_customer", "dim_supplier", "dim_carrier", "fact_delivery_out", "fact_delivery_in")),
    ("Live displays", ("display_",)),
    ("Reports", ("report_",)),
    ("Management pack template", ("template_",)),
    ("Month-end dashboard", ("",)),       # everything else: the three sample organisations
]
OUT = DATA_ROOT     # kept for older references
# The month-end dashboard's three sample organisations each get their own folder.
ORG_FOLDERS = {"trades": "SME trades", "services": "SME services", "nfp": "Not-for-profit"}
SINGLE_ORG = {"fact_job_month": "trades", "fact_engagement_month": "services", "fact_grant_instalment": "nfp",
              "fact_grant_position": "nfp", "fact_grant_spend_month": "nfp"}     # tables without an org column


def org_splits(name, cols, rows):
    """For a month-end table: {org: rows}. Uses the org column, or the table's single organisation."""
    if name in SINGLE_ORG:
        return {SINGLE_ORG[name]: rows}
    i = cols.index("org_id") if "org_id" in cols else cols.index("org")
    return {o: [r for r in rows if r[i] == o] for o in ORG_FOLDERS}
MONTHS_2026 = [date(2026, m, 1) for m in range(1, 13)]

# ---------------------------------------------------------------- the data
# Each entry: table name -> (description, columns, rows)

def weeks(start, n):
    return [start + timedelta(weeks=i) for i in range(n)]

TABLES = {}
DDL = {}   # explicit column types and keys (the star schema); other tables are inferred

def table(name, description, columns, rows):
    TABLES[name] = (description, columns, rows)

# --- Home-page dashboard: generated from tools/1_build_data/financial_model.py (see main()),
#     so the statements always add up. Tables: model_*.

# Report mock-ups show SEPTEMBER 2026 (the last locked month). The live screens show TODAY, Tue 6 Oct 2026, as at 2pm.
# --- Live display: warehouse floor (today = 6 Oct 2026)
TODAY = date(2026, 10, 6)
table("display_warehouse_kpis", "Warehouse screen: today's despatch KPIs.",
      ["kpi", "value", "target", "unit"],
      [["Orders picked", 142, 180, "lines"], ["On time, in full", 94, 95, "percent"], ["Late inbound deliveries", 3, 0, "deliveries"]])
table("display_warehouse_picks_by_hour", "Warehouse screen: lines picked per hour today (sums to 142).",
      ["pick_date", "hour_start", "lines_picked"],
      [[TODAY.isoformat(), f"{h:02d}:00", v] for h, v in zip(range(7, 15), [12, 17, 21, 24, 19, 23, 16, 10])])
table("display_warehouse_overdue_deliveries", "Warehouse screen: overdue inbound deliveries.",
      ["supplier", "item", "days_late"],
      [["Supplier A", "Steel coil", 2], ["Supplier B", "Fasteners", 1], ["Supplier C", "Packaging", 1]])

# --- Live display: reception
table("display_reception_kpis", "Reception screen: headline numbers as at 6 Oct 2026.",
      ["kpi", "value", "of_total", "unit", "period"],
      [["Orders shipped", 1248, None, "orders", "last 30 days"], ["Delivered on time", 96, None, "percent", "last 30 days"],
       ["Team in today", 24, 31, "people", "today"]])
table("display_reception_orders_by_week", "Reception screen: orders shipped by week.",
      ["week_start", "week_label", "orders_shipped"],
      [[w.isoformat(), f"W{i + 1}", v] for i, (w, v) in enumerate(zip(weeks(date(2026, 8, 17), 7), [168, 182, 175, 196, 188, 207, 214]))])
table("display_reception_today", "Reception screen: today's list.",
      ["item", "count"],
      [["Deliveries expected", 6], ["Visitors booked", 4], ["Open jobs on the floor", 37]])

# --- Live display: boardroom management pack (September 2026, year to date)
budget = [440, 448, 455, 460, 465, 470, 474, 478, 485, 495, 500, 505]
actual = [438, 452, 470, 478, 476, 488, 492, 494, 502, None, None, None]
forecast = [None] * 8 + [502, 520, 528, 541]
table("display_boardroom_kpis", "Boardroom screen: management pack KPIs, year to date September 2026.",
      ["kpi", "value", "unit", "comparison"],
      [["Revenue vs budget", 2.8, "percent", "$4.29M actual vs $4.18M budget"],
       ["True gross margin", 31.4, "percent", "-2.1 pts after freight and wastage"],
       ["Customer churn", 4.1, "percent", "+0.6 pts on last quarter"],
       ["Forecast vs budget", 1.8, "percent", "rolling 12 months, driver-based"]])
table("display_boardroom_revenue_monthly", "Boardroom screen: revenue by month, $k. Actual Jan-Sep (sums to 4,290), budget Jan-Dec (Jan-Sep sums to 4,175), forecast Sep-Dec (from September's actual).",
      ["month", "actual_aud_k", "budget_aud_k", "forecast_aud_k"],
      [[m.isoformat(), a, b, f] for m, a, b, f in zip(MONTHS_2026, actual, budget, forecast)])
table("display_boardroom_cost_of_sale", "Boardroom screen: what a sale really costs, as a share of revenue (sums to 100).",
      ["component", "pct_of_revenue"],
      [["Materials", 36.0], ["Labour", 20.6], ["Freight", 6.5], ["Wastage", 3.5], ["Returns", 2.0], ["Left as margin", 31.4]])

# --- Report preview: sales (September 2026)
sales_months = MONTHS_2026[3:9]
table("report_sales_kpis", "Sales report: KPIs for September 2026.",
      ["kpi", "value", "unit", "comparison"],
      [["Revenue", 412300, "AUD", "+6.1% on last month"], ["Orders", 1248, "orders", "+3.4% on last month (1,207)"],
       ["Cancellation rate", 3.8, "percent", "+0.9 pts on last month"], ["Weighted pipeline", 1100000, "AUD", "next 90 days"]])
table("report_sales_revenue_monthly", "Sales report: revenue by month (chart shows $k).",
      ["month", "revenue_aud"],
      [[m.isoformat(), v] for m, v in zip(sales_months, [348000, 362000, 371000, 355000, 388600, 412300])])
table("report_sales_top_customers", "Sales report: top customers, September 2026.",
      ["customer", "revenue_aud", "change_vs_last_year_pct", "cancellation_pct"],
      [["Customer A", 68000, 12, 1.2], ["Customer B", 54000, 4, 2.0], ["Customer C", 41000, -9, 7.5], ["Customer D", 37000, 21, 0.8],
       ["Customer E", 29000, -3, 3.1], ["Customer F", 24000, 7, 1.9], ["Customer G", 19000, -14, 9.2]])
table("report_sales_cancellations_by_reason", "Sales report: cancelled orders by reason (47 of 1,248 = 3.8%).",
      ["reason", "orders_cancelled"],
      [["Late delivery", 19], ["Price", 13], ["Out of stock", 9], ["Changed mind", 6]])

# --- Report preview: purchasing (September 2026)
table("report_purchasing_kpis", "Purchasing report: KPIs for September 2026.",
      ["kpi", "value", "unit", "comparison"],
      [["Spend", 286000, "AUD", "September"], ["Delivered on time", 91, "percent", "-3 pts on last month"],
       ["Late purchase orders", 14, "orders", "+5 on last month"], ["Price variance", 4.2, "percent", "paid vs purchase order price"]])
table("report_purchasing_on_time_by_supplier", "Purchasing report: on-time delivery by supplier.",
      ["supplier", "on_time_pct"],
      [[f"Supplier {s}", v] for s, v in zip("ABCDEF", [78, 96, 84, 92, 97, 99])])
table("report_purchasing_late_orders", "Purchasing report: all 14 late purchase orders (the preview shows the worst 7).",
      ["po_number", "supplier", "days_late", "value_aud"],
      [["PO-1042", "Supplier A", 9, 18400], ["PO-1057", "Supplier C", 6, 6100], ["PO-1061", "Supplier A", 4, 11000],
       ["PO-1066", "Supplier D", 3, 2700], ["PO-1070", "Supplier B", 2, 4900], ["PO-1072", "Supplier C", 2, 1800],
       ["PO-1075", "Supplier E", 1, 3300], ["PO-1076", "Supplier B", 1, 2100], ["PO-1078", "Supplier F", 1, 900],
       ["PO-1079", "Supplier A", 1, 5600], ["PO-1081", "Supplier D", 1, 1400], ["PO-1082", "Supplier C", 1, 3000],
       ["PO-1084", "Supplier E", 1, 2200], ["PO-1085", "Supplier A", 1, 4400]])
table("report_purchasing_unit_cost_index", "Purchasing report: unit cost index by month (April = 100).",
      ["month", "freight_index", "steel_index"],
      [[m.isoformat(), f, s] for m, f, s in zip(sales_months, [100, 101, 104, 107, 109, 115], [100, 99, 101, 100, 103, 104])])

# --- Report preview: payroll and overtime (September 2026)
table("report_payroll_kpis", "Payroll and overtime report: KPIs for September 2026.",
      ["kpi", "value", "unit", "comparison"],
      [["Labour cost", 198000, "AUD", "September"], ["Overtime hours", 412, "hours", "+18% on last month"],
       ["Overtime share", 9.6, "percent", "of 4,292 hours worked"], ["Labour per job", 143, "AUD", "+$11 on last month (1,383 jobs)"]])
pay_weeks = weeks(date(2026, 8, 24), 6)
table("report_payroll_overtime_by_week", "Payroll and overtime report: overtime hours by week (sums to 412).",
      ["week_start", "week_label", "overtime_hours"],
      [[w.isoformat(), f"W{i + 1}", v] for i, (w, v) in enumerate(zip(pay_weeks, [58, 61, 66, 72, 74, 81]))])
table("report_payroll_by_team", "Payroll and overtime report: overtime, jobs and labour per job by team.",
      ["team", "overtime_hours", "jobs_completed", "labour_per_job_aud"],
      [["Fabrication", 168, 412, 171], ["Assembly", 97, 388, 139], ["Despatch", 74, 520, 96], ["Maintenance", 49, 63, 228], ["Office", 24, None, None]])
table("report_payroll_hours_vs_jobs", "Payroll and overtime report: hours worked vs jobs completed, indexed (W1 = 100).",
      ["week_start", "week_label", "hours_index", "jobs_index"],
      [[w.isoformat(), f"W{i + 1}", h, j] for i, (w, h, j) in enumerate(zip(pay_weeks, [100, 102, 105, 109, 111, 116], [100, 101, 101, 102, 101, 103]))])

# --- Template: management pack, profit and loss (September 2026)
pnl = [["Revenue", 412300, 398000, "Two new customers; volume up 5%"],
       ["Materials", 156700, 151200, "Steel price up 4% from 1 Sep"],
       ["Freight", 28900, 23500, "Fuel levy; three urgent shipments"],
       ["Wastage", 16400, 12000, "Rework on one large job"],
       ["Gross margin", 210300, 211300, "Volume gains eaten by freight and wastage"],
       ["Wages", 98600, 101000, "Overtime down 40 hours"],
       ["Overheads", 61200, 60000, "Annual software renewal"],
       ["Net profit", 50500, 50300, "On budget, but margin needs watching"]]
INCOME = {"Revenue", "Gross margin", "Net profit"}
def variance(line, a, b):  # positive = favourable
    return a - b if line in INCOME else b - a
table("template_pnl", "Management pack template: profit and loss, actual against budget, September 2026. Variance is favourable when positive.",
      ["month", "line", "actual_aud", "budget_aud", "variance_aud", "variance_pct", "what_drove_it"],
      [[date(2026, 9, 1).isoformat(), l, a, b, variance(l, a, b), round(100 * variance(l, a, b) / b, 1), n] for l, a, b, n in pnl])

# ---------------------------------------------------------------- checks

def check_totals():
    """The numbers that are meant to add up, do."""
    t = {k: v[2] for k, v in TABLES.items()}
    assert sum(r[2] for r in t["display_warehouse_picks_by_hour"]) == 142
    assert sum(r[1] for r in t["display_boardroom_revenue_monthly"][:9]) == 4290
    assert sum(r[2] for r in t["display_boardroom_revenue_monthly"][:9]) == 4175
    assert round(sum(r[1] for r in t["display_boardroom_cost_of_sale"]), 1) == 100.0
    assert sum(r[1] for r in t["report_sales_cancellations_by_reason"]) == 47 and round(100 * 47 / 1248, 1) == 3.8
    assert sum(r[2] for r in t["report_payroll_overtime_by_week"]) == 412
    assert sum(r[1] for r in t["report_payroll_by_team"]) == 412
    assert round(198000 / sum(r[2] for r in t["report_payroll_by_team"] if r[2])) == 143
    p = {r[1]: r for r in t["template_pnl"]}
    for col in (2, 3):
        assert p["Gross margin"][col] == p["Revenue"][col] - p["Materials"][col] - p["Freight"][col] - p["Wastage"][col]
        assert p["Net profit"][col] == p["Gross margin"][col] - p["Wages"][col] - p["Overheads"][col]

# Key figures that must still appear in each mock-up page
MOCKUP_CHECKS = {
    "tools/mockups/warehouse.html": ["142", "180", "94", "steel coil"],
    "tools/mockups/reception.html": ["1,248", "96", "24", "31"],
    "tools/mockups/boardroom.html": ["+2.8%", "$4.29M", "$4.18M", "31.4%", "38 days", "+1.8%", "· September"],
    "tools/mockups/report-sales.html": ["$412k", "1,248", "3.8%", "[19, 13, 9, 6]", "<b>September</b>", "['Apr','May','Jun','Jul','Aug','Sep']"],
    "tools/mockups/report-purchasing.html": ["$286k", "91%", "+4.2%", "PO-1042"],
    "tools/mockups/report-payroll.html": ["$198k", "412", "9.6%", "$143"],
    "tools/mockups/template-excel.html": ["412,300", "210,300", "50,500", "· September", "from 1 Sep"],
}

def check_mockups():
    missing = []
    for path, needles in MOCKUP_CHECKS.items():
        text = (REPO / path).read_text()
        missing += [f"{path}: {n}" for n in needles if n not in text]
    if missing:
        sys.exit("Mock-ups and sample data disagree:\n  " + "\n  ".join(missing))

# ---------------------------------------------------------------- output

def sql_type(values):
    vals = [v for v in values if v is not None]
    if all(isinstance(v, int) for v in vals):
        return "INT"
    if all(isinstance(v, (int, float)) for v in vals):
        return "DECIMAL(14,2)"
    if all(isinstance(v, str) and len(v) == 10 and v[4] == "-" and v[7] == "-" for v in vals):
        return "DATE"
    return f"VARCHAR({max(20, max(len(str(v)) for v in vals) + 20)})"

def folder_for(name):
    for folder, keys in FOLDERS:
        if any(name == k or (k.endswith("_") and name.startswith(k)) or k == "" for k in keys):
            return folder


def main():
    import data_status as ds
    import period_lock          # which months are locked: read by every status label, so it comes first
    added = period_lock.seed_history([f"{y}-{m:02d}" for y in (2024, 2025, 2026) for m in range(1, 13) if "2024-10" <= f"{y}-{m:02d}" <= "2026-09"],
                                     ds.history_lock_day)
    if added:
        print(f"Period-lock register: added the sample history's closes ({added} rows) to {period_lock.path()}")
    table("period_lock", "The period-lock register: one row per organisation and month, saying when the month was locked (closed) "
          "and by whom. Locked once locked_at is on or before the run; a reopened month has locked_at blank and a note saying why "
          "(Provisional once it's over, like a month never locked). Entered by people (tools/lock_period.py), never generated: the "
          "build only adds the sample history's closes (Oct 2024 to Sep 2026) where a month has no row, and keeps every row anyone entered.",
          period_lock.COLUMNS, [[r[c] or None for c in period_lock.COLUMNS] for r in period_lock.read().values()])
    import financial_model      # the driver-based model
    import model_tables         # ...as CSV rows for the dashboard tables
    import warehouse            # the same model as a daily star schema for a cloud database
    res = financial_model.build()   # runs every check; stops here if anything doesn't add up
    tables = model_tables.csv_tables(res)
    wh = warehouse.build(res)
    for name, (desc, cols, rows, ddl) in wh.items():
        table(name, desc, cols, rows)
        DDL[name] = ddl
    import operations           # the non-financial data: enquiries, overtime, people helped, calls for help, volunteers
    res_ = res
    jobs_all = res_["trades"]["out"]["jobs"] + warehouse.build.history["jobs"]
    for name, (desc, cols, rows, ddl) in operations.build(res_, jobs_all, wh["fact_timesheet_daily"][2], wh["fact_grant_spend_month"][2], wh["dim_grant"][2]).items():
        table(name, desc, cols, rows)
        DDL[name] = ddl
    import drivers              # supporting files for every input that isn't a transaction
    for name, (desc, cols, rows, ddl) in drivers.build(res, warehouse.build.account_ids).items():
        table(name, desc, cols, rows)
        DDL[name] = ddl
    import deliveries           # deliveries in and out, for the map on examples.html
    for name, (desc, cols, rows, ddl) in deliveries.tables(deliveries.build()).items():
        table(name, desc, cols, rows)
        DDL[name] = ddl
    for name, (desc, cols, rows) in tables.items():
        table(name, desc, cols, rows)
    check_totals()
    check_mockups()
    DOCS.mkdir(parents=True, exist_ok=True)
    for folder, _ in FOLDERS:
        (DATA_ROOT / folder).mkdir(parents=True, exist_ok=True)
        for old in (DATA_ROOT / folder).rglob("*.csv"):
            old.unlink()   # tables that no longer exist don't linger
    for sub in ORG_FOLDERS.values():
        (DATA_ROOT / "Month-end dashboard" / sub).mkdir(parents=True, exist_ok=True)
    files = 0
    schema = ["-- Sample Co tables for The Fourth Sheet mock-ups. Generated by tools/1_build_data/sample_data.py.",
              "-- Works in Azure SQL / SQL Server and PostgreSQL. Load each CSV into the table of the same name.",
              "-- Create (and load) the dim_ tables before the fact_ tables: the facts reference them.", ""]
    order = sorted(TABLES, key=lambda n: (0 if n == "dim_org" else 1 if n.startswith("dim_") else 2 if n in ("driver_month", "cost_rate", "target", "opening_balance", "kpi_workings", "commentary", "simulation_parameter") else 3 if n.startswith("fact_") else 4))
    for name in order:
        desc, cols, rows = TABLES[name]
        folder = folder_for(name)
        if folder == "Month-end dashboard":
            parts = org_splits(name, cols, rows)
            if sum(len(v) for v in parts.values()) != len(rows):
                sys.exit(f"{name}: rows lost when splitting by organisation")
            targets = [(DATA_ROOT / folder / ORG_FOLDERS[o] / f"{name}.csv", part) for o, part in parts.items() if part]
        else:
            targets = [(DATA_ROOT / folder / f"{name}.csv", rows)]
        for path, part in targets:
            with open(path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows([["" if v is None else v for v in r] for r in part])
            files += 1
        types = [t for _, t in DDL[name]] if name in DDL else [sql_type([r[i] for r in rows]) for i in range(len(cols))]
        where = (f"Data/Month-end dashboard/<organisation>/{name}.csv (one file per organisation; load them all into this table)"
                 if folder_for(name) == "Month-end dashboard" else f"Data/{folder_for(name)}/{name}.csv")
        schema.append(f"-- {desc}  [{where}]")
        schema.append(f"CREATE TABLE {name} (\n" + ",\n".join(f"    {c} {t}" for c, t in zip(cols, types)) + "\n);\n")
    (DOCS / "schema.sql").write_text("\n".join(schema))
    write_readme()
    files += write_cash_forecast()        # derived from the data just written, so it comes after it (and goes in the schema too)
    counts = {f: sum(folder_for(n) == f for n in TABLES) for f, _ in FOLDERS}
    print(f"Wrote {len(TABLES)} tables as {files} CSVs to {DATA_ROOT}/ (" + ", ".join(f"{f}: {c}" for f, c in counts.items()) + f"); schema.sql and README to {DOCS}/")

def write_cash_forecast():
    """report_cash_forecast_daily: the 13-week cash forecast behind 'Will cash cover payroll next month?', one row per day,
    for every date it was made on (each period's end, or today). Built by tools/3_publish_site/fourthsheet (cash_forecast) from the
    tables above, so it ties to the ledger. Loaded like any other table; Power BI draws it after the actual cash."""
    from fourthsheet.build import load_data, periods_for
    from fourthsheet.catalogue import cash_forecast
    from fourthsheet.period import Period
    D = load_data()          # reads the CSVs just written
    cols = ["forecast_made_on", "forecast_date", "org_id", "unpaid_invoices_collected", "new_work_collected", "wages",
            "suppliers_and_overheads", "tax_interest_finance", "cash_at_bank"]
    rows = []
    for mo in sorted(periods_for("cash-payroll", D)):
        F = cash_forecast(D, Period(mo, D["trades"].months))
        for d in F["days"]:
            x = F["flows"][d]
            rows.append([F["asat"].isoformat(), d.isoformat(), "trades", *[round(x[k], 2) for k in ("old", "new", "wages", "suppliers", "other")], round(F["cash"][d], 2)])
    with open(DATA_ROOT / "Reports" / "report_cash_forecast_daily.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    with open(DOCS / "schema.sql", "a") as f:
        f.write("\n-- Cash forecast, 13 weeks a day at a time, for each date it was made on (SME trades). Money out is negative.  "
                "[Data/Reports/report_cash_forecast_daily.csv]\nCREATE TABLE report_cash_forecast_daily (\n    forecast_made_on DATE,\n    forecast_date DATE,\n"
                "    org_id VARCHAR(20),\n" + ",\n".join(f"    {c} DECIMAL(14,2)" for c in cols[3:]) + ",\n    PRIMARY KEY (forecast_made_on, forecast_date, org_id)\n);\n")
    return 1


GROUPS = [
    ("Cloud database: daily star schema behind the home-page dashboard", "dim_"),
    ("", "fact_"),
    ("Supporting files: drivers, rates, targets, opening balances, workings and commentary", "driver_month"),
    ("", "cost_rate"), ("", "target"), ("", "opening_balance"), ("", "kpi_workings"), ("", "commentary"), ("", "simulation_parameter"),
    ("Home-page dashboard model (index.html, data/dashboard.json, media/exports/)", "model_"),
    ("Live-display screens (media/mockups/display-*.png)", "display_"),
    ("Report previews (media/mockups/report-*.png)", "report_"),
    ("Management-pack template (media/mockups/template-excel.png)", "template_"),
]

def write_readme():
    lines = [
        "# Sample data: what each table holds",
        "",
        "The invented \"Sample Co\" numbers behind every mock-up dashboard and report on the website.",
        "**Generated by `tools/1_build_data/sample_data.py`; don't edit these files by hand.** Change the numbers in that script",
        "(and the matching mock-up), then run `python3 tools/1_build_data/sample_data.py`.",
        "",
        "- One CSV per table: a header row, plain numbers (no `$` or commas), ISO dates (`2026-10-01`), empty = no value.",
        "- All money is AUD. Columns ending `_aud_k` are thousands of dollars.",
        "- The CSVs are in `Data/`, one folder per task (Common holds the shared tables such as `dim_date`). This folder",
        "  (`Data documentation/`) holds `schema.sql`, with a `CREATE TABLE` for every CSV (Azure SQL / SQL Server and PostgreSQL), and this README.",
        "",
        "## Built for a cloud database, and for drilling down",
        "",
        "Everything here is meant to live in a cloud database and be rebuilt in Power BI or any other reporting tool.",
        "The home-page dashboard's numbers are stored as a **star schema at daily grain** (`dim_` and `fact_` tables):",
        "",
        "- `fact_gl_daily` holds every P&L posting by day, tagged with its job, engagement or grant. Summed by month it equals",
        "  the P&L on the website to the dollar (checked every time the data is generated).",
        "- `fact_cash_daily` and `fact_balance_daily` give cash movements and closing cash / unpaid invoices for every day; the",
        "  month-end values equal the balance sheet.",
        "- `fact_timesheet_daily` gives hours by day against each job or engagement.",
        "- `dim_date` carries the whole drill path: financial year > quarter > month > week (`week_start`, Monday) > day, plus",
        "  working days and Brisbane public holidays. Join any fact on `date_key` and drill from the year to a single day.",
        "",
        "Database: Azure SQL `thefourthsheet` on server `thefourthsheet-sql.database.windows.net` (names in Config/database.env). Check it exists with `python3 tools/2_load_azure/database/azure_setup.py` before loading.",
        "",
        "## Loading into a database",
        "",
        "1. Run `schema.sql` to create the tables (Common first: the other tables reference `dim_date` and `dim_org`).",
        "2. Load each CSV into the table with the same name, for example:",
        "   - **PostgreSQL:** `\\copy report_sales_kpis FROM 'report_sales_kpis.csv' CSV HEADER`",
        "   - **Azure SQL / SQL Server:** the Import Flat File wizard (SSMS / Azure Data Studio), or `BULK INSERT ... WITH (FORMAT = 'CSV', FIRSTROW = 2)`",
        "   - **Power BI / Excel:** Get Data > Text/CSV.",
        "",
        "## Tables",
        "",
    ]
    for folder, _ in FOLDERS:
        names = [n for n in TABLES if folder_for(n) == folder]
        lines.append(f"### Data/{folder}/" + (" (one subfolder per organisation: " + ", ".join(ORG_FOLDERS.values()) + "; each holds its own rows of these tables)" if folder == "Month-end dashboard" else ""))
        lines.append("")
        lines.append("| Table | What it is | Columns |")
        lines.append("| --- | --- | --- |")
        for name in names:
            desc, cols, rows = TABLES[name]
            lines.append(f"| `{name}` | {desc} | {', '.join(f'`{c}`' for c in cols)} |")
        lines.append("")
    (DOCS / "README.md").write_text("\n".join(lines))

if __name__ == "__main__":
    main()
