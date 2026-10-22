#!/usr/bin/env python3
"""
powerbi_notes.py — a Power BI build PROMPT for each website report (for Claude with the Power BI MCP).

Writes OneDrive "Data documentation/Power BI/<report>.md" (internal notes, not site copy), generated
from the same report definitions as the website, so the two never drift. Each note covers the data
model, DAX measures, visuals section by section, the page slicer, drill-through to the workings,
data status, theme and export settings.

Run via tools/3_publish_site/build_site.py (after the reports are built).
"""

from pathlib import Path

import sync_media      # finds the OneDrive project folder (honours FOURTH_SHEET_DATA)

COMMON_MODEL = """## Data model (shared)

Load from the cloud database (or the CSVs in `Data/`, one folder per task):

- **dim_date** (`Data/Common`): mark as the date table on `calendar_date`. Drill path: `financial_year` > `fy_quarter` > `month_name` > `week_start` > `calendar_date`. Sort `month_name` by `month_key`.
- **Month** (calculated table) for month-grain facts: `Month = SUMMARIZE(dim_date, dim_date[month_key], dim_date[month_name], dim_date[financial_year], dim_date[month_status], dim_date[month_locked_on])`. Relate `Month[month_key]` 1-to-many to `dim_date[month_key]`, and to each month-grain fact's `month_key`.
- **dim_org** (`Data/Common`) 1-to-many to every fact's `org_id`. Each report page filters to its organisation.
- Data status: `dim_date[day_status]` and `dim_date[month_status]` (Locked / Provisional / Incomplete) drive formatting and the "as at" card.

Relationships are single-direction, one-to-many from dimension to fact. Hide the key columns in report view.
"""

THEME = """## Theme and formatting

- Theme JSON colours: data colour 1 `#0E9F6E` (green: on target, lines, areas), `#A7B0B8` (grey: below target), `#2F2F2F` (target lines), text `#25342A`, muted `#5F6F63`.
- Bar charts: horizontal (categories down the left), data labels on, gridlines off, sorted by the page's default measure. Keep the sort fixed when the measure changes (sort by the default measure's column, not the visible one).
- Area charts: line 3 px, area transparency about 75% fading to the axis (Power BI has no gradient fill: approximate with transparency, or use a Deneb/Vega-Lite visual for a true fade), straight lines (no smoothing), y-axis on from zero with light gridlines, data labels off, markers only on the highest and lowest points (conditional marker formatting by a `IsMaxMin` measure).
- Numbers: whole dollars, percentages 1 decimal place, negatives in brackets. Gross margin is always labelled *gross margin* (before overheads, not profit). Wages always include on-costs.
"""

EXPORT = """## Export and print

- Page size A4 landscape for PDF export. Put the business name and page name in a page header text box, and the file name, "Data retrieved <as at>" and page number in the footer (Power BI service: Export > PDF; or a paginated report for exact headers and footers).
- "Analyze in Excel" or export the underlying data from each visual; the Excel downloads on the website show the layout to aim for (data as values, every calculation a formula).
"""

# DAX for each report (measures beyond the shared ones)
MEASURES = {
    "cost-to-win": """```DAX
Marketing spend = CALCULATE(SUM(driver_month[value]), driver_month[driver] = "Marketing spend", driver_month[org_id] = "trades")
New customers   = CALCULATE(SUM(driver_month[value]), driver_month[driver] = "New customers (first job ever)", driver_month[org_id] = "trades")
Cost to win a customer = DIVIDE([Marketing spend], [New customers])
Cost to win, same month last year = CALCULATE([Cost to win a customer], DATEADD(dim_date[calendar_date], -12, MONTH))
Cost to win, last 12 months = CALCULATE(DIVIDE([Marketing spend], [New customers]), DATESINPERIOD(dim_date[calendar_date], MAX(dim_date[calendar_date]), -12, MONTH))
```
(August and September 2026 marketing come from the ledger, `fact_gl_daily` on the "Marketing" account; earlier months from `driver_month`.)""",
    "job-margins": """```DAX
Revenue        = SUM(fact_line_month[revenue])
Direct cost    = SUM(fact_line_month[direct_cost])
Gross margin   = [Revenue] - [Direct cost]
Gross margin % = DIVIDE([Gross margin], [Revenue])
Job gross margin (job) = SUMX(fact_job_month, fact_job_month[revenue] - fact_job_month[materials] - fact_job_month[subcontractors] - fact_job_month[labour_cost])
Job gross margin % (job) = DIVIDE([Job gross margin (job)], SUM(fact_job_month[revenue]))
Target gross margin % = LOOKUPVALUE(target[value], target[target], "Installation job margin")
Below target = IF([Job gross margin % (job)] < [Target gross margin %], 1, 0)   -- conditional colour: grey when 1
Overheads (Sep) = - CALCULATE(SUM(fact_gl_daily[amount]), dim_account[section] IN {"Operating expenses"} || dim_account[line] IN {"Depreciation", "Interest"})
Gross margin needed to cover overheads = DIVIDE([Overheads (Sep)] + [Technician time not charged], [Revenue])
```""",
    "growth": """```DAX
Revenue        = SUM(fact_line_month[revenue])
Gross margin   = SUM(fact_line_month[gross_margin])
Gross margin % = DIVIDE([Gross margin], [Revenue])
Revenue, same month last year = CALCULATE([Revenue], DATEADD(dim_date[calendar_date], -12, MONTH))
Growth, year on year = DIVIDE([Revenue] - [Revenue, same month last year], [Revenue, same month last year])
Revenue, last 12 months = CALCULATE([Revenue], DATESINPERIOD(dim_date[calendar_date], MAX(dim_date[calendar_date]), -12, MONTH))
Revenue, the 12 before  = CALCULATE([Revenue, last 12 months], DATEADD(dim_date[calendar_date], -12, MONTH))
Growth, last 12 months  = DIVIDE([Revenue, last 12 months], [Revenue, the 12 before]) - 1
```
Growth shows blank for the first 12 months (nothing to compare with): hide those months on the growth view rather than showing zeros.""",
    "cost-to-raise": """```DAX
Fundraising cost = - CALCULATE(SUM(fact_gl_daily[amount]), dim_account[line] IN {"Grant writing and reporting", "Donor campaigns", "Event costs"})
Money raised     = CALCULATE(SUM(fact_line_month[revenue]), fact_line_month[line] IN {"Grants", "Donations", "Fundraising events"})
Cost to raise a dollar (cents) = DIVIDE([Fundraising cost], [Money raised]) * 100
```
By source, use `fact_line_month` (`revenue` = raised, `direct_cost` = cost of raising it) with `line` on the slicer.""",
    "program-cost": """```DAX
Grant spending = SUM(fact_grant_spend_month[spend])
Monthly budget = SUM(fact_grant_spend_month[budget])
Share of program spending = DIVIDE([Grant spending], CALCULATE([Grant spending], ALL(dim_grant)))
Shared costs (Sep) = - CALCULATE(SUM(fact_gl_daily[amount]), dim_account[line] IN {"Program delivery wages (untied)", "Program costs (untied)", "Administration wages", "Occupancy", "Other administration"})
Full cost of the program = [Grant spending] + [Share of program spending] * [Shared costs (Sep)]
```
Only current grants have a full cost; finished grants appear in the spending-over-time view.""",
    "cash-payroll": """```DAX
Cash at bank (actual) = LASTNONBLANKVALUE(dim_date[calendar_date], SUM(fact_balance_daily[cash_at_bank]))
Unpaid invoices = CALCULATE(SUM(fact_invoice[amount]), fact_invoice[invoice_date] <= MAX(dim_date[calendar_date]), fact_invoice[paid_date] > MAX(dim_date[calendar_date]))
Days to pay (median) = MEDIANX(FILTER(fact_invoice, fact_invoice[paid_date] <= MAX(dim_date[calendar_date])), DATEDIFF(fact_invoice[invoice_date], fact_invoice[paid_date], DAY))
Last pay run = - CALCULATE(SUM(fact_cash_daily[amount]), dim_account[line] = "Payments to employees", LASTDATE(fact_cash_daily[date]))
```
The forecast itself (one row per day: expected money in and out, by kind) is built upstream from the same tables and loaded as `report_cash_forecast_daily` (Data/Reports; filter `forecast_made_on` to the latest); Power BI then draws actual + forecast on one line with the forecast lighter, and a constant line at one pay run.""",
    "callbacks": """```DAX
Enquiries = COUNTROWS(fact_enquiry)
Called back = CALCULATE(COUNTROWS(fact_enquiry), NOT ISBLANK(fact_enquiry[responded_at]))
Within 2 working hours = CALCULATE(COUNTROWS(fact_enquiry), fact_enquiry[within_target] = 1)
Share within target = DIVIDE([Within 2 working hours], [Called back])
Median wait (working minutes) = MEDIANX(FILTER(fact_enquiry, NOT ISBLANK(fact_enquiry[minutes_to_callback])), fact_enquiry[minutes_to_callback])
```""",
    "overtime": """```DAX
Overtime hours = SUM(fact_shift_daily[overtime_hours])
Ordinary hours = SUM(fact_shift_daily[ordinary_hours])
Overtime share = DIVIDE([Overtime hours], [Ordinary hours])
```""",
    "people-helped": """```DAX
People helped = SUM(fact_service_daily[people_helped])
Couldn't reach = SUM(fact_service_daily[people_not_reached])
Share reached = DIVIDE([People helped], [People helped] + [Couldn't reach])
```""",
    "calls": """```DAX
Calls = COUNTROWS(fact_call)
Calls while staffed = CALCULATE(COUNTROWS(fact_call), fact_call[outcome] <> "After hours: voicemail")
Answered = CALCULATE(COUNTROWS(fact_call), fact_call[answered] = 1)
Answered while staffed = DIVIDE([Answered], [Calls while staffed])
```
Time-of-day bands: a calculated column on fact_call from hour_of_day (Before 8:30am, 8:30 to 10am, 10am to noon, Noon to 2pm, 2 to 5pm, 5 to 8pm, After 8pm).""",
    "volunteers": """```DAX
Volunteer hours = SUM(fact_volunteer_shift[hours])
Volunteers = DISTINCTCOUNT(fact_volunteer_shift[volunteer_id])
Hours per volunteer = DIVIDE([Volunteer hours], [Volunteers])
```""",
    "runway": """```DAX
Cash at bank = LASTNONBLANKVALUE(dim_date[calendar_date], SUM(fact_balance_daily[cash_at_bank]))
Unspent grant money = CALCULATE(SUM(opening_balance[amount]), opening_balance[line] = "Grants received in advance (unspent)")   -- month ends: from model_statements
Owed to the ATO = CALCULATE(SUM(model_statements[amount_aud]), model_statements[statement_key] = "bs",
    model_statements[line] IN {"GST payable (net)", "PAYG withholding payable"})   -- GST and PAYG withheld, held until the BAS
Unrestricted cash = [Cash at bank] - [Unspent grant money] - [Owed to the ATO]
Monthly cash spending = - CALCULATE(SUM(fact_gl_daily[amount]), dim_account[section] <> "Income", dim_account[line] <> "Depreciation")
Runway (months) = DIVIDE([Unrestricted cash], [Monthly cash spending])
Reserves target (months) = LOOKUPVALUE(target[value], target[target], "Reserves (unrestricted cash runway)")
```""",
    "funding": """```DAX
Raised             = SUM(fact_line_month[revenue])
Cost of raising it = SUM(fact_line_month[direct_cost])
Left after costs   = [Raised] - [Cost of raising it]
Cost per dollar (cents) = DIVIDE([Cost of raising it], [Raised]) * 100
```""",
    "board": """```DAX
Income   = CALCULATE(SUM(model_statements[amount_aud]), model_statements[line] = "Total income")
Expenses = - CALCULATE(SUM(model_statements[amount_aud]), model_statements[line] = "Total expenses")
Surplus  = [Income] - [Expenses]
Surplus, year to date = CALCULATE([Surplus], DATESYTD(dim_date[calendar_date], "30/6"))
Spent against budget = DIVIDE(SUM(fact_grant_position[spent_to_date]), SUM(fact_grant_position[budget_to_date]))
```
The "what the board should note" and "decisions to make" text comes from `commentary`, written at month end.""",
}

VISUAL = {"kpis": "Card (new) visual, one card per headline number; reference label shows the comparison (August, last year). Drill-through to the Workings page.",
          "bars": "Clustered bar chart (horizontal). For a %/$ toggle use a field parameter ({views}) with a button slicer; keep the sort fixed. Target as an X-axis constant line (dashed, #2F2F2F) or, for $ targets, an error bar / marker series.",
          "series": "Area chart over Month (x) with the measure from a field parameter ({views}); see the theme notes. Months with month_status <> \"Locked\" in a lighter colour (conditional formatting by a status measure) or a dashed line segment via a second series.",
          "table": "Table or matrix; conditional formatting highlights the row selected in the page slicer.",
          "text": "Smart narrative (or a text box with dynamic values) for \"what it shows\"; a second for the action. Keep the wording as a flag, not an instruction.",
          "list": "Text box fed from the commentary table.",
          "definition": "Static text box (the gross margin definition), with a button linking to the explainer.",
          "insight": "Smart narrative tied to the bridge measures (gross margin → time not charged → overheads → profit before tax), with drill-through to the bridge workings.",
          "vary": "Responds to the page slicer: the same visual, filtered by it."}


def expected(r):
    """Numbers the finished Power BI page must show (taken from the website report), so Claude can check its build."""
    out = []
    for b in r["blocks"]:
        tag = f"{b['label']}: " if b.get("label") else ""
        for sec in b["sections"]:
            sub = (sec["by"].get("All") or next(iter(sec["by"].values()))) if sec["type"] == "vary" else sec
            if sub["type"] == "kpis":
                out += [f"- {tag}{k['label']} = {k['value']} ({k.get('sub', '')})" for k in sub["items"]]
            elif sub["type"] == "bars":
                ch = sub["chart"]
                v0 = (ch.get("views") or [ch])[0]
                f = v0.get("format", ch.get("format"))
                vals = ", ".join(f"{l} {v}{'%' if str(f).startswith('pct') else ''}" for l, v in zip(ch["labels"], v0["values"]))
                out.append(f"- {tag}{ch['title']}: {vals}")
            elif sub["type"] == "series":
                dims = sub.get("dims") or {}
                key = f"{(dims.get('line') or ['All'])[0]}|{(dims.get('measure') or [['']])[0][0]}"
                v = sub["views"].get(key)
                if v:
                    pts = [(l, x) for l, x in zip(sub["labels"], v["values"]) if x is not None]
                    out.append(f"- {tag}{sub['title']} ({v['label']}): {pts[0][0]} = {pts[0][1]}, {pts[-1][0]} = {pts[-1][1]}, {len(pts)} months")
            elif sub["type"] == "insight":
                out.append(f"- {tag}{sub['text']}")
    return "\n".join(out)


def guard_dax(text):
    """Every base measure returns blank unless exactly one organisation is in the filter context, so no total can ever
    add two businesses together (the sample businesses are separate and unrelated). Measures built on other measures inherit it."""
    import re
    out = []
    for line in text.split("\n"):
        m = re.match(r"^(\s*)([^=\n`]+?)\s*=\s*(.+)$", line)
        if m and not line.lstrip().startswith(("--", "```")) and not re.match(r"^\s*(Month|Org check)\b", m.group(2)):
            rhs, tail = (m.group(3).split("   --", 1) + [None])[:2]
            if re.search(r"\b(SUM|SUMX|CALCULATE|LASTNONBLANKVALUE|MEDIANX|AVERAGE|COUNTROWS|DISTINCTCOUNT|LOOKUPVALUE)\(", rhs) and "[" + "" not in rhs[:0]:
                refs_only = not re.search(r"\b(SUM|SUMX|LASTNONBLANKVALUE|MEDIANX|AVERAGE|COUNTROWS|DISTINCTCOUNT|LOOKUPVALUE)\(", rhs) and "CALCULATE([" in rhs.replace(" ", "")
                if not refs_only:
                    line = f"{m.group(1)}{m.group(2)} = IF(HASONEVALUE(dim_org[org_id]), {rhs.strip()})" + (f"   --{tail}" if tail else "")
        out.append(line)
    return "\n".join(out)


def note(r):
    """A prompt to paste into Claude with the Power BI MCP connected."""
    secs = []
    multi = len([b for b in r["blocks"] if b.get("org")]) > 1
    for b in r["blocks"]:
        org = b.get("org") or r.get("org")
        if b.get("label"):
            secs.append(f"\n### Page: {b['label']} ({b.get('business', r['business'])})")
        if org and (b.get("label") or not multi) and org in ("trades", "services", "nfp"):
            secs.append(f"- **Page-level filter: `dim_org[org_id] = \"{org}\"`**, locked and hidden from viewers. Everything on this page is this one business"
                        + ("; build the other business on its own page (duplicate this page and change only the filter)." if multi else "."))
        if b.get("filter"):
            opts = ", ".join(l for _, l in b["filter"]["options"])
            secs.append(f"- Slicer **{b['filter']['label']}** ({opts}): single select, default \"All\". Edit interactions so it filters EVERY visual on the page "
                        "(cards, bars, area chart, table, narrative). Nothing on the page may show a different selection.")
        for sec in b["sections"]:
            t = sec["type"]
            sub = sec["by"].get("All", next(iter(sec["by"].values()))) if t == "vary" else sec
            st = sub["type"]
            title = sub.get("title") or (sub.get("chart") or {}).get("title") or {"kpis": "Headline numbers", "text": "What it shows / what you'd do"}.get(st, st)
            views = ""
            if st == "bars" and sub["chart"].get("views"):
                views = " / ".join(v["label"] for v in sub["chart"]["views"])
            if st == "series":
                views = " / ".join(lab for _, lab in (sub.get("dims") or {}).get("measure", []))
            secs.append(f"- **{title}**{' (follows the slicer)' if t == 'vary' or sec.get('highlight_filter') else ''}: " + VISUAL.get(st, "").format(views=views or "the measures"))
    return f"""# Prompt: build "{r['question']}" in Power BI

Paste everything below into Claude with the Power BI MCP connected to the target model / report.

---

You are building {"one Power BI report page per business" if len([b for b in r["blocks"] if b.get("org")]) > 1 else "one Power BI report page"} that reproduces the website report "{r['question']}" (`report-{r['slug']}.html`) for {r['business']}. Use the Power BI MCP tools to create the model objects, measures and visuals. Work step by step and check each step before moving on.

**What the page answers:** {r['intro']}

**Rules (non-negotiable):**
- **One business per page.** The sample businesses (trades, services and the not-for-profit) are separate, unrelated organisations. Never add their numbers together, put them in one total, chart or table, or rank them against each other. Every page has a locked page-level filter on `dim_org[org_id]`, and every measure returns blank unless exactly one organisation is in view (`IF(HASONEVALUE(dim_org[org_id]), …)`, already written into the measures below).
- Gross margin is always labelled *gross margin* and never called profit: it is before overheads.
- Wages include their on-costs (super and leave). No payroll tax in the samples: both SMEs are under the Queensland threshold and the charity is exempt.
- Whole dollars; percentages to 1 decimal place; negatives in brackets.
- One slicer drives every visual on the page.
- Bars keep the same category order when the measure changes.

**Step 1: data model.**
{COMMON_MODEL.replace('## Data model (shared)', '').strip()}

**Step 2: measures.** Create these (adjust names to the model if tables are named differently, and tell me what you changed):

{guard_dax(MEASURES.get(r['slug'], ''))}

Then add `Org check = DISTINCTCOUNT(dim_org[org_id])` as a card on each page while you build: it must read 1 everywhere. Delete the card when the page is done.

**Step 3: visuals, top to bottom.**
{chr(10).join(secs)}

**Step 4: workings.** Add a drill-through page built on `kpi_workings` (`scope`, `subject`, `line_no`, `line`, `value`, `is_calculated`, `calculation`), filtered to the clicked item, lines in order, calculated lines in bold. Add a tooltip page for month points showing that month's inputs.

**Step 5: data status.** A card reading "September locked · October in progress" from `dim_date[month_status]`. Show locked months by default; the current month only where noted, lighter.

**Step 6: formatting.**
{THEME.replace('## Theme and formatting', '').strip()}

**Step 7: export settings.**
{EXPORT.replace('## Export and print', '').strip()}
"""


def write(reports):
    out = sync_media.onedrive_root() / "Data documentation" / "Power BI"
    out.mkdir(parents=True, exist_ok=True)
    for r in reports:
        (out / f"{r['slug']}.md").unlink(missing_ok=True)       # older notes format
        (out / f"{r['slug']} - Power BI prompt.md").write_text(note(r))
    print(f"  Power BI prompts: {len(reports)} in {out}")
