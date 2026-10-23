"""
document.py — write "Database tables and star schema.md" (OneDrive, Data documentation/): every table that loads
into the database (its file(s), rows, grain, columns, types, keys, links and an example row), and for each one the
best-practice place in a star schema.

    python3 tools/2_load_azure/database/document.py

The facts come from schema.sql and the CSVs, so the document is always current; the star-schema advice is in
STAR (by table) and DESIGN (by subject) below.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import re
import sys
from datetime import date
from pathlib import Path

import winutf8; winutf8.ensure()   # noqa: E402  Windows: run in UTF-8 mode

import data_status as ds              # noqa: E402
from database import load, schema  # noqa: E402

# role now -> what it becomes in the star schema (and why)
STAR = {
    # ---- conformed dimensions
    "dim_date": ("Dimension (conformed)", "Keep as **dim_date** (date_key yyyymmdd). Move day_status, month_status, month_locked_on and status_as_at out to **ops.period_status**: they change every run, and a dimension shouldn't. Add a month-start key so monthly facts join to the same calendar."),
    "dim_org": ("Dimension (conformed)", "Keep as **dim_org** with a surrogate org_key. It's the client (tenant) key: row-level security filters every fact on it once there are real clients."),
    "dim_account": ("Dimension", "Keep as **dim_account** with a surrogate account_key, a unique (org_id, account_id) business key, and the statement > section > line hierarchy as columns. Drop the subtotal/total rows from the dimension (is_postable = 0): totals are calculated, not stored. Make it type 2 (valid_from/valid_to) if the chart of accounts is remapped."),
    "dim_job": ("Dimension", "Keep as **dim_job** (surrogate job_key). Add customer_key, contract_key (maintenance jobs) and product_line so every job rolls up to a line without a lookup table. Add an 'unknown job' row (key −1) for postings with no job."),
    "dim_engagement": ("Dimension", "Keep as **dim_engagement** (surrogate engagement_key) with customer_key and engagement_type as the product line. Rates (hourly_rate, fixed_fee) are type 2: a rate change starts a new row."),
    "dim_grant": ("Dimension", "Keep as **dim_grant** (surrogate grant_key). Split funder into **dim_funder** and program into **dim_program** (a program outlives each grant round: Youth outreach 2023-25 and 2025-27 are the same program)."),
    "dim_contract": ("Dimension (outrigger)", "Fold into **dim_job** (contract attributes on the maintenance-contract jobs) or keep as **dim_contract** referenced from dim_job. The monthly fee, hours and materials are the contract's terms: type 2 when they're renegotiated."),
    "dim_customer": ("Dimension", "Keep as **dim_customer** (surrogate customer_key), type 2 on region and usual carrier so old deliveries keep the region they had. Conform it with the trades/services customers (one customer dimension per client)."),
    "dim_supplier": ("Dimension", "Keep as **dim_supplier** (surrogate supplier_key), type 2 on usual carrier and transit days."),
    "dim_carrier": ("Dimension", "Keep as **dim_carrier** with a surrogate carrier_key; the facts carry the key, not the carrier's name."),
    # ---- facts
    "fact_gl_daily": ("Fact (transaction)", "The centre of the finance star: **fact_gl** at one row per posting (org, day, account, job/engagement/grant), keys only + amount DECIMAL(19,4) + load_id. Every P&L, balance sheet and cash flow is a view over it. Clustered columnstore index. Missing job/engagement/grant = the −1 'not applicable' member, never NULL."),
    "fact_cash_daily": ("Fact (transaction)", "Fold into **fact_gl** (cash-flow lines are just accounts), or keep as **fact_cash** with the same keys if the bank feed arrives separately. Reconcile to fact_gl's cash account every day."),
    "fact_balance_daily": ("Fact (periodic snapshot)", "Becomes **fact_balance_snapshot** at one row per org, day and balance account (unpivot cash_at_bank and unpaid_invoices into account rows). Better still, derive it as a running total of fact_gl and keep the snapshot only for speed."),
    "fact_balance_month": ("Fact (periodic snapshot)", "Keep as **fact_balance_month_snapshot** (org_key, month_key, account_key, amount): the month-end close, every balance-sheet line. Once fact_gl carries opening journals, check each month against the running total of fact_gl (they must tie to the dollar), then keep this as the locked record of each close."),
    "fact_cash_flow_month": ("Fact (derived, monthly)", "Don't store once fact_cash is complete: **rpt.cash_flow_month** = fact_cash summed by month and cash-flow account. Until then keep it, and check opening cash + the month's lines = closing cash (fact_balance_month)."),
    "period_lock": ("Fact (transaction, entered)", "Keep as **ops.period_lock** (org_key, month_key, locked_at, locked_by, note; key org_key + month_key): entered by people, never regenerated. **ops.period_status** (a view: locked when locked_at is set) replaces the status columns on dim_date."),
    "fact_timesheet_daily": ("Fact (transaction)", "Becomes **fact_time** at one row per person, day and job/engagement: date_key, org_key, **employee_key** (add a dim_employee: role, team, cost rate, type 2), job_key or engagement_key, hours, cost (hours × the rate in force). Utilisation and time-not-charged come straight from it."),
    "fact_job_month": ("Fact (derived, monthly)", "Don't store: build **rpt.job_month** as a view (revenue and materials from fact_gl by job, hours from fact_time, cost at the dim rate). Call-out revenue is two ledger accounts, 'Call-outs: technician time' and 'Call-outs: materials charged' (cost × 1.3), so the view keeps both columns. Storing it means two copies of the truth."),
    "fact_engagement_month": ("Fact (derived, monthly)", "Don't store the revenue/cost columns: they come from fact_time and fact_gl. Keep WIP as **fact_wip_snapshot** (engagement, month end, unbilled value): a balance at a date is a periodic snapshot."),
    "fact_invoice": ("Fact (accumulating snapshot)", "Becomes **fact_invoice** with role-playing dates (invoice_date_key, due_date_key, paid_date_key), customer_key, job_key/engagement_key, amount, days_to_pay. One row per invoice, updated when it's paid. Debtor ageing is a view."),
    "fact_line_month": ("Fact (derived, monthly)", "Don't store: **rpt.line_month** view (fact_gl revenue + direct cost by dim_job/dim_engagement product line). The month_status column belongs in ops.period_status."),
    "fact_grant_instalment": ("Fact (transaction)", "Keep as **fact_grant_receipt** (grant_key, date_key, amount). Reconcile to fact_gl's grant-income cash."),
    "fact_grant_spend_month": ("Fact (plan + actual)", "Split: spend is actual (from fact_gl, tagged with the grant); budget is a plan, so **fact_grant_budget** at grant × month. Actual vs budget is a view."),
    "fact_grant_position": ("Fact (derived snapshot)", "Don't store: **rpt.grant_position** view (received to date, spent to date, budget to date, still to spend, months left) for any date."),
    "fact_delivery_out": ("Fact (accumulating snapshot)", "Keep as **fact_delivery_out**: role-playing dates (order, promised, delivered → dim_date), customer_key, carrier_key, a small junk dimension **dim_delivery_status** (status × in_full × late_reason), measures cartons, order_value, days_late. delivered_time → a time-of-day key if it's analysed."),
    "fact_delivery_in": ("Fact (accumulating snapshot)", "Keep as **fact_delivery_in**: po/due/arrived date keys, supplier_key, carrier_key, the same status junk dimension, measures lines, lines_short, po_value, days_late."),
    # ---- drivers, plans, settings
    "driver_month": ("Fact (driver, monthly)", "Becomes **fact_driver** (org_key, month date_key, driver_key, value) with **dim_driver** (name, unit, source). Drivers that are really transactions (marketing spend, new customers) should come from their own facts instead: new customers = first job per customer."),
    "cost_rate": ("Reference (rates)", "Becomes **dim_rate** or attributes on dim_employee, type 2 (valid_from/valid_to): costs must use the rate in force at the time, not today's."),
    "target": ("Reference (targets)", "Becomes **fact_target** (org, target_key, valid_from, value) or a per-job/engagement target on the dimension (from the quote). Effective-dated so past months judge against the target they had."),
    "opening_balance": ("Fact (opening)", "Load as an opening journal into **fact_gl** (one posting per balance account on the opening date), so every balance is a sum of fact_gl from the start."),
    "commentary": ("Content", "Keep as **content.commentary** (org, month, subject, text, author, approved). It's written words, not data: no star, but keyed to the month and subject it explains."),
    "kpi_workings": ("Derived", "Don't store: **rpt.kpi_workings** view (the inputs and calculation for each headline number), so the workings can never disagree with the number."),
    "simulation_parameter": ("Settings (sample data only)", "Move to **ops.simulation_parameter**: it drives the invented data, not the reporting. Not part of the star."),
    "model_statements": ("Derived (statements)", "Don't store: **rpt.statement** views over fact_gl × dim_account (P&L, balance sheet, cash flow), with subtotals calculated."),
    "model_assumptions": ("Settings (sample data only)", "Move to **ops**: the assumptions behind the invented model. Real clients' equivalents are dim_rate, fact_target and fact_driver."),
    "model_fourth_sheet_kpis": ("Derived", "Don't store: **rpt.fourth_sheet_kpis** view (or DAX measures in Power BI)."),
    # ---- mock-up feeds (presentation)
    "template_pnl": ("Presentation (mock-up)", "Don't store: a **rpt.pnl_vs_budget** view over fact_gl and a **fact_budget** (org, month, account, amount). what_drove_it → content.commentary."),
}
for n in ("display_boardroom_cost_of_sale", "display_boardroom_kpis", "display_boardroom_revenue_monthly", "display_reception_kpis",
          "display_reception_orders_by_week", "display_reception_today", "display_warehouse_kpis", "display_warehouse_overdue_deliveries",
          "display_warehouse_picks_by_hour"):
    STAR[n] = ("Presentation (mock-up screen)", "Don't store: a **rpt.** view per screen over the facts (orders, picks, deliveries, revenue vs budget). "
               "Picks by hour needs a **fact_pick** (order line, picker, timestamp → date_key + time_key).")
for n in ("report_payroll_by_team", "report_payroll_hours_vs_jobs", "report_payroll_kpis", "report_payroll_overtime_by_week",
          "report_purchasing_kpis", "report_purchasing_late_orders", "report_purchasing_on_time_by_supplier", "report_purchasing_unit_cost_index",
          "report_sales_cancellations_by_reason", "report_sales_kpis", "report_sales_revenue_monthly", "report_sales_top_customers"):
    area = n.split("_")[1]
    feed = {"payroll": "fact_time + a fact_payroll (pay run lines: ordinary, overtime, on-costs) with dim_employee",
            "purchasing": "fact_purchase_order_line (PO, supplier, item, due/received dates, qty, unit cost) with dim_supplier and dim_item",
            "sales": "fact_sales_order_line (order, customer, product, dates, value, cancelled + reason) with dim_customer and dim_product"}[area]
    STAR[n] = ("Presentation (mock-up report)", f"Don't store: a **rpt.** view over {feed}.")

# ---- operations tables added for the reports (calls, callbacks, people helped, overtime, volunteers, runway)
STAR.update({
    "dim_volunteer": ("Dimension", "Keep as **dim_volunteer** (surrogate volunteer_key, codes only, no names). main_program and started are attributes; type 2 if a volunteer's main program changes."),
    "fact_call": ("Fact (transaction)", "Keep as **fact_call** at one row per call: date_key, org_key, a time-of-day key (hour, staffed or not) instead of hour_of_day, an outcome key; measures answered (0/1) and wait_seconds. Answer rate and wait come straight from it."),
    "fact_enquiry": ("Fact (accumulating snapshot)", "Keep as **fact_enquiry** at one row per enquiry with role-playing dates (received, responded), channel and enquiry type as small dimensions (or one junk dimension), job_key once it becomes a job; measures minutes_to_callback and within_target."),
    "fact_service_daily": ("Fact (periodic snapshot)", "Becomes **fact_service** at program × day: date_key, org_key, **program_key** (add a dim_program shared with grants and volunteers), a reason key; measures people_helped and people_not_reached."),
    "fact_shift_daily": ("Fact (transaction)", "Fold into **fact_time** (see fact_timesheet_daily) at person × day: employee_key (technicians become rows in dim_employee), ordinary and overtime hours, an overtime-reason key."),
    "fact_volunteer_shift": ("Fact (transaction)", "Keep as **fact_volunteer_shift** at one row per shift: date_key, org_key, volunteer_key, program_key (shared dim_program); measure hours. Value of volunteer time is hours × a rate in a view."),
    "report_cash_forecast_daily": ("Fact (periodic snapshot, forecast)", "Keep as **fact_cash_forecast** at made-on date × forecast date × org: two role-playing date keys and the cash lines as measures. Forecast accuracy is a view joining fact_cash_daily on the forecast date."),
})

# ---- the three datasets (tools/1_build_data/datasets.py): each already close to a star; advice is the tidy-up to finish it
STAR.update({
    # Retail
    "retail.dim_date": ("Dimension (conformed)", "Keep as **retail.dim_date**; better, conform with one company-wide dim_date (same date_key) so retail, health, legal and finance share a calendar."),
    "retail.dim_store": ("Dimension", "Keep as **dim_store** (surrogate store_key). current_sales_rep_id makes it type 2 territory history: when a store changes rep, start a new row so past sales stay with the rep who made them. Retailer and channel can be a dim_retailer outrigger."),
    "retail.dim_product": ("Dimension", "Keep as **dim_product** (surrogate product_key) with brand and pack size as the hierarchy. unit_price is a list price that changes: type 2, or a separate price list fact."),
    "retail.dim_employee": ("Dimension", "Keep as **dim_employee**, type 2 on role and territory; end_date and status describe the employment, not the row."),
    "retail.dim_carrier": ("Dimension", "Keep as **dim_carrier** (surrogate carrier_key)."),
    "retail.dim_delivery_status": ("Dimension (small)", "Fold with on_time / in_full / difot flags into one junk dimension **dim_delivery_outcome**, so the fact carries one key instead of five columns."),
    "retail.dim_cancellation_reason": ("Dimension (small)", "Keep as **dim_cancellation_reason** with category and controllable as attributes; facts use −1 for 'not cancelled'."),
    "retail.dim_sales_channel": ("Dimension (small)", "Keep as **dim_sales_channel**; the default discount is an attribute, the actual discount is a measure on the sale."),
    "retail.dim_transaction_source": ("Dimension (small)", "Fold into a junk dimension with channel if both stay small, or keep as **dim_transaction_source**."),
    "retail.dim_promotion": ("Dimension", "Keep as **dim_promotion** (surrogate key, −1 'no promotion'). Scope (retailer, state, store type, SKU) is a bridge if a promotion can cover several of each."),
    "retail.fact_sales": ("Fact (transaction)", "The centre of the retail star: **fact_sales** at one row per order line, keys only (date, store, product, rep, channel, promotion, source, order) + qty, gross and net sales, discount = gross − net. Clustered columnstore."),
    "retail.fact_sales_order": ("Fact (accumulating snapshot)", "Keep as **fact_sales_order** with role-playing dates (ordered, requested, cancelled) and the order status as a key; order_total stays a view over fact_sales (it equals the sum of the lines)."),
    "retail.fact_delivery": ("Fact (accumulating snapshot)", "Keep as **fact_delivery** with role-playing dates (dispatched, scheduled, delivered), carrier_key, the delivery outcome junk key, and measures qty dispatched, received, damaged, rejected. DIFOT % is a measure."),
    "retail.fact_budget_product_month": ("Fact (plan)", "Keep as **fact_budget** at product × month (month's first date_key). Actual vs budget is a view joining fact_sales at the same grain."),
    # Health
    "health.dim_date": ("Dimension (conformed)", "Conform with the company-wide **dim_date**."),
    "health.dim_provider": ("Dimension", "Keep as **dim_provider** (surrogate key), type 2 on FTE and specialty."),
    "health.dim_service_type": ("Dimension", "Keep as **dim_service_type**; the standard fee and Medicare rebate change every July: type 2 (valid_from/to) so old appointments keep the fee in force."),
    "health.fact_appointment": ("Fact (transaction)", "Keep as **fact_appointment** at one row per booking: date and booking date keys, provider, service type, patient (add a **dim_patient**, de-identified), a status/billing-type junk key; measures fee, rebate, out of pocket, wait days, satisfaction."),
    "health.fact_claim": ("Fact (accumulating snapshot)", "Keep as **fact_claim** with submitted and paid date keys, a claim status/rejection reason junk key, and claim amount; days to pay is a measure."),
    # Legal
    "legal.dim_date": ("Dimension (conformed)", "Conform with the company-wide **dim_date** (court vacations as an attribute)."),
    "legal.dim_client": ("Dimension", "Keep as **dim_client** (surrogate key) with segment."),
    "legal.dim_fee_earner": ("Dimension", "Keep as **dim_fee_earner**, type 2 on role, hourly rate and office, so past work keeps the rate it was charged at."),
    "legal.dim_office": ("Dimension", "Keep as **dim_office**; the facts carry office_key only (done: the repeated office names were removed from the facts)."),
    "legal.dim_practice_area": ("Dimension (small)", "Keep as **dim_practice_area**."),
    "legal.dim_referral_source": ("Dimension (small)", "Keep as **dim_referral_source**."),
    "legal.dim_matter": ("Dimension", "Keep as **dim_matter** (surrogate key) with client, practice area, fee earner, referral and office keys; open/close dates and status make it type 2 or move them to fact_matter."),
    "legal.fact_matter": ("Fact (accumulating snapshot)", "Keep as **fact_matter**: one row per matter with open/close date keys and the claim, settlement, fees, disbursements, collected and written-off measures (recalculated from the detail, so they agree)."),
    "legal.fact_work": ("Fact (transaction)", "Keep as **fact_work**: one row per timecard (date, matter, fee earner, office keys; hours, value at standard rate). Unbilled work = work without a billing row."),
    "legal.fact_billing": ("Fact (transaction)", "Keep as **fact_billing**: one row per timecard billed (billing date, matter, fee earner; hours, rate, amount, write-off). Realisation = billed ÷ work value."),
    "legal.fact_disbursement": ("Fact (transaction)", "Keep as **fact_disbursement** (date, matter, office; amount)."),
    "legal.fact_fee_earner_budget_month": ("Fact (plan)", "Keep as **fact_fee_earner_budget** at fee earner × month: budget hours and revenue. Utilisation vs target and revenue vs budget are views."),
})

DESIGN = """
## The target: four stars that share their dimensions

Best practice (Kimball): facts hold keys and numbers at the finest grain available; dimensions hold the descriptions;
everything else (statements, KPIs, screens, workings) is a **view in `rpt`**, so there is one copy of the truth.

```
                       dim_date (conformed: every date and month)      dim_org (conformed: the client / tenant)
                                   │                                          │
  FINANCE           fact_gl ───────┼── dim_account ── dim_job ── dim_engagement ── dim_grant ─ dim_program, dim_funder
  (one row per                     │        └ opening balances load as journals; cash flow = accounts
   posting)                        │
  TIME & JOBS       fact_time ─────┼── dim_employee (new) ── dim_job / dim_engagement ── dim_rate (type 2)
                    fact_invoice ──┼── dim_customer   (role-playing dates: invoiced, due, paid)
                    fact_wip_snapshot (month-end unbilled work)
  GRANTS            fact_grant_receipt ── fact_grant_budget ── dim_grant          (actual spend comes from fact_gl)
  DELIVERIES        fact_delivery_out ── dim_customer ── dim_carrier ── dim_delivery_status (junk)
                    fact_delivery_in  ── dim_supplier ── dim_carrier
  PLANS             fact_driver ── dim_driver · fact_target · fact_budget (org × month × account)

  rpt (views)       statements, line_month, job_month, grant_position, kpi_workings, fourth_sheet_kpis, screens
  ops               period_status (Locked / Provisional / Incomplete), load_run, load_table, simulation settings
  content           commentary (written notes keyed to month and subject)
```

**Rules for every table**
1. **Surrogate keys**: an INT IDENTITY key on every dimension (`org_key`, `account_key`, ...); the source's own ID is kept as the business key with a UNIQUE constraint. Facts carry only surrogate keys.
2. **Unknown members**: every dimension has a −1 row ("Not applicable" / "Unknown"). Fact keys are NOT NULL.
3. **Grain first**: write each fact's grain in one sentence before building it (e.g. "one row per posting per day"). Never mix grains in one table.
4. **Type 2 history** where the past must stay as it was: rates, targets, customer regions, account mappings (`valid_from`, `valid_to`, `is_current`).
5. **Money as DECIMAL(19,4)**, one sign convention (income +, cost −, as the ledger), never floats. Percentages are calculated, not stored.
6. **Dates as `date_key` INT yyyymmdd** joined to dim_date; monthly facts use the month's first day. Role-playing dates get their own key columns.
7. **No derived tables**: anything that can be calculated from a fact is a view (or a DAX measure), so it can't drift.
8. **Status lives in `ops.period_status`**, written at month-end close, not in dim_date or the facts.
9. **Every row records its load** (`load_id` → ops.load_run), so any number can be traced to the file and run it came from.
10. **Performance and security**: clustered columnstore on the big facts (fact_gl, fact_time, fact_delivery_out); foreign keys on; row-level security on org_key once there's more than one client.

**Build order:** dim_date, dim_org → dim_account, dim_customer, dim_supplier, dim_carrier, dim_employee → dim_job, dim_engagement, dim_grant (+ program, funder) → fact_gl (with opening journals) → fact_time, fact_invoice → grants, deliveries, plans → rpt views (check each against today's tables: the statements must tie to the cent) → switch the report builder and Power BI to the views → retire the derived tables.
"""


BUILD_ORDER = ["dim_date", "dim_org", "period_lock", "dim_account", "dim_customer", "dim_supplier", "dim_carrier", "dim_contract", "dim_job",
               "dim_engagement", "dim_grant", "cost_rate", "target", "opening_balance", "fact_gl_daily", "fact_cash_daily",
               "fact_balance_daily", "fact_balance_month", "fact_cash_flow_month", "fact_timesheet_daily", "fact_invoice", "fact_job_month", "fact_engagement_month", "fact_line_month",
               "fact_grant_instalment", "fact_grant_spend_month", "fact_grant_position", "fact_delivery_out", "fact_delivery_in",
               "driver_month", "commentary", "kpi_workings", "model_statements", "model_fourth_sheet_kpis", "model_assumptions",
               "simulation_parameter", "template_pnl"]

MCP_RULES = """You are connected through the SQL database MCP to the Azure SQL database **thefourthsheet** (server
thefourthsheet-sql.database.windows.net), signed in as me. We are building a Kimball star schema from the loaded tables.

Ground rules for everything in this session:
1. Read before you write: inspect the source table(s) in `dbo` (columns, types, row counts, a few rows) first.
2. Never change, drop or delete anything in `dbo`, `ops` or `stage`. Build only in schema `star` (tables) and `rpt` (views);
   create those schemas if they don't exist.
3. Before creating anything, show me the DDL and the load query, and wait for my OK.
4. Dimensions: an INT IDENTITY surrogate key (`<name>_key`), the source ID kept as the business key with a UNIQUE constraint,
   a -1 'Unknown / Not applicable' row, and `valid_from`, `valid_to`, `is_current` where I say type 2.
5. Facts: surrogate keys only (NOT NULL, -1 for none), amounts DECIMAL(19,4) with the ledger's sign convention, `date_key` INT
   yyyymmdd joined to star.dim_date, a `load_id` column, foreign keys on, clustered columnstore on facts over 10,000 rows.
6. Anything that can be calculated from a fact is a VIEW in `rpt`, not a table.
7. After building, prove it: row counts and SUMs of every amount must equal the source in `dbo` (to the cent), and every
   foreign key must resolve. Show me the reconciliation query and its result. If anything doesn't tie, stop and tell me.
8. No dynamic SQL built from data values, no new logins or users, no permission changes.
Reply "Ready" when you've read this."""


def prompt(n, t, adv):
    target = (re.findall(r"\*\*([^*]+)\*\*", adv) or [n])[0]
    view = adv.startswith("Don't store")
    cols = ", ".join(c for c, _ in t.columns)
    return (f"Using the SQL database MCP, build {target} from `dbo.{n}` ({cols}). "
            f"Design: {adv.replace('**', '')} "
            + ("Create it as a view in `rpt`, over the `star` tables where they exist (otherwise over `dbo`), and show that it returns the same rows and totals as "
               f"`dbo.{n}` for every month in it." if view else
               f"Create it in `star`, load it from `dbo.{n}` (and the star dimensions it needs), then reconcile: row count and the SUM of every amount against `dbo.{n}`, and no orphan keys.")
            + " Follow the ground rules: show me the DDL and load first and wait for my OK.")


def describe():
    out = {}
    for f in schema.schema_files():
        text = f.read_text(encoding="utf-8")
        out |= {m.group(2): m.group(1).strip() for m in re.finditer(r"-- (.*?)\s+\[Data/[^\]]*\]\nCREATE TABLE ((?:[a-z_]+\.)?[a-z_]+)", text)}
    return out


def area(n):
    if "." in n:
        return {"retail": "Retail dataset", "health": "Health dataset", "legal": "Legal dataset"}[n.split(".")[0]]
    for pre, a in (("display_", "Mock-up screens"), ("report_", "Mock-up reports"), ("template_", "Mock-up reports"), ("model_", "Home dashboard model")):
        if n.startswith(pre):
            return a
    if n in ("dim_customer", "dim_supplier", "dim_carrier", "fact_delivery_in", "fact_delivery_out"):
        return "Deliveries"
    if n in ("dim_date", "dim_org", "target", "simulation_parameter", "period_lock"):
        return "Common"
    return "Month-end (finance, jobs, engagements, grants)"


def main():
    ts = schema.tables()
    order = schema.load_order(ts)
    desc = describe()
    missing = [n for n in order if n not in STAR]
    if missing:
        raise SystemExit(f"No star-schema advice written for: {', '.join(missing)} (add it to STAR in tools/2_load_azure/database/document.py)")
    info = {}
    for n in order:
        files, rows, _ = load.read_files(ts[n])
        info[n] = (files, rows)
    root = schema.data_root()
    L = ["# Database tables and star schema", "",
         f"Generated by `tools/2_load_azure/database/document.py` on {ds.strf(date.today(), '%-d %B %Y')} from `schema.sql` and the CSVs in `Data/`. "
         f"{len(order)} tables, {sum(len(r) for _, r in info.values()):,} rows. Sample data (invented).", "",
         "Part 1 is every table as it loads today: its file(s), rows, columns, types, keys and links. Part 2 is the best-practice "
         "star schema each one should become. Loading order is dimensions first, then the facts that point at them "
         "(`python3 tools/2_load_azure/database/load.py`).", "",
         "## Contents", "", "| Area | Table | Rows | Today | In the star schema |", "| --- | --- | ---: | --- | --- |"]
    for n in sorted(order, key=lambda x: (area(x), x)):
        role, adv = STAR[n]
        short = re.findall(r"\*\*([^*]+)\*\*", adv)
        target = ("Don't store: " + short[0]) if adv.startswith("Don't store") and short else (short[0] if short else "")
        L.append(f"| {area(n)} | [{n}](#{n.replace('_', '_')}) | {len(info[n][1]):,} | {role} | {target} |")
    L += ["", DESIGN.strip(), "",
          "## Building it with Claude (prompts for the SQL database MCP)", "",
          "Connect Claude to the database through a SQL MCP server (signed in with your Microsoft account, as everything else; no password). "
          "Paste the ground rules first, then the table prompts in this order, one at a time, checking each reconciliation before the next. "
          "Each table's own prompt is also under it, below.", "", "**1. Ground rules (paste first):**", "", "```text", MCP_RULES, "```", "",
          "**2. Then, in this order:** " + " → ".join(f"[{n}](#{n})" for n in BUILD_ORDER if n in ts) + ". "
          "The Retail, Health and Legal datasets are separate stars: for each, dimensions first, then facts, in the order listed below. "
          "The mock-up screen and report tables come last (views over the facts above; several need source facts that don't exist yet: "
          "picks, payroll, purchase orders, sales orders).", "",
          "**3. Finally:** \"Using the SQL database MCP, list every object in `star` and `rpt` with its row count, rerun every reconciliation "
          "from this session in one query, and show any that don't tie.\"", "",
          "**Next question users will ask: which technician, which day, which customer?** Out of scope for this test, but easy once the star "
          "schema is in: add `dim_employee` to fact_time and `customer_key` to dim_job / fact_invoice (the source systems already hold both), "
          "and every call-out, job and invoice drills to the technician, the date and time, and the customer, with no new reporting work.", "",
          "## Every table", ""]
    for n in sorted(order, key=lambda x: (area(x), x)):
        t = ts[n]
        files, rows = info[n]
        role, adv = STAR[n]
        pk = re.findall(r"^\s*([a-z_]+) [A-Z]+[^,\n]*PRIMARY KEY", t.ddl, re.M)
        refs = {c: r.replace("dbo.", "") for c, r in re.findall(r"^\s*([a-z_]+) [A-Z]+[^,\n]*REFERENCES ((?:[a-z_]+\.)?[a-z_]+)", t.ddl, re.M)}
        ex = rows[0] if rows else [None] * len(t.columns)
        L += [f"### {n}", "", desc.get(n, ""), "",
              f"- **Area:** {area(n)} · **Rows:** {len(rows):,} · **Today:** {role}",
              "- **File(s):** " + ", ".join(f"`{f.relative_to(root)}`" for f in files),
              f"- **Primary key:** {', '.join(pk) if pk else 'none'} · **Links to:** {', '.join(sorted(set(refs.values()))) or 'nothing'}", "",
              "| Column | Type | Key | Example |", "| --- | --- | --- | --- |"]
        for (c, k), v in zip(t.columns, ex):
            key = "PK" if c in pk else (f"→ {refs[c]}" if c in refs else "")
            sval = "" if v is None else str(v)
            L.append(f"| {c} | {k} | {key} | {sval[:60] + ('…' if len(sval) > 60 else '')} |")
        L += ["", f"**Star schema:** {adv}", "", "**Prompt for Claude (SQL MCP):**", "", "```text", prompt(n, t, adv), "```", ""]
    out = schema.schema_file().parent / "Database tables and star schema.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(order)} tables)")
    return out


if __name__ == "__main__":
    main()
