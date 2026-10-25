#!/usr/bin/env python3
"""
powerbi_statements.py — the Power BI framework for the profit and loss, balance sheet and cash flow: writes the Power BI
project (PBIP: a semantic model in TMDL and a report in PBIR, plain text, reviewed in git like code) to powerbi/.

  powerbi/Financial statements.pbip                    open this in Power BI Desktop
  powerbi/Financial statements.SemanticModel/         tables, relationships, measures, the "Period view" calculation group
  powerbi/Financial statements.Report/                pages: Profit and loss, Balance sheet, Cash flow, Checks

The statements are built from the layout tables (statement_line, statement_line_account: tools/1_build_data/
statement_lines.py), never from line names in DAX: one [Amount] measure works out every line of every statement for
any organisation, and the "Period view" calculation group turns it into this month, last month, year to date and the
changes. A new account or a new client's chart of accounts changes the data, not the model.

Columns and types come from schema.sql (stage 1), so the model never drifts from the database. The data comes from the
CSVs in the OneDrive Data folder or from Azure SQL: the DataSource parameter picks (Transform data > Edit parameters).
No data goes in git: the files hold the structure only.

Files are rewritten only when their content changes. Run on its own, or via build_site.py (step 5):
  python3 tools/3_publish_site/powerbi_statements.py
Check the result: python3 tools/3_publish_site/tests/powerbi_check.py
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import json
import uuid

import data_status as ds
import financial_model as fm

REPO = _T.parent
OUT = REPO / "powerbi"
NAME = "Financial statements"
NS = uuid.UUID("6c1f7e7a-4f4e-4c1b-9a59-7d0f1b4e5a10")      # lineage tags and ids are derived from names: stable between runs
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/"

# ------------------------------------------------------------------ the semantic model: which tables, from where

# (model table, source table, hidden columns, extra columns added in Power Query)
TABLES = [
    ("Date", "dim_date", {"date_key", "status_as_at", "fy_month_no", "day_of_week", "iso_week"}, []),
    ("Organisation", "dim_org", {"toggle_name", "about"}, []),
    ("Account", "dim_account", {"account_id", "org_id", "line_order", "is_postable"}, []),
    ("Statement line", "statement_line", {"line_key", "org_id", "line_order", "line_kind", "role", "show_when_zero", "line"},
     [("row_label", "text")]),
    ("Statement line account", "statement_line_account", {"org_id", "line_key", "account_id", "factor"}, []),
    ("GL", "fact_gl_daily", {"date_key", "org_id", "account_id", "amount"}, []),
    ("Balance", "fact_balance_month", {"org_id", "month_key", "account_id", "amount", "date_key"}, [("date_key", "int")]),
    ("Cash flow", "fact_cash_flow_month", {"org_id", "month_key", "account_id", "amount", "date_key"}, [("date_key", "int")]),
]
HIDDEN_TABLES = {"Statement line account", "GL", "Balance", "Cash flow"}
DESCRIPTIONS = {
    "Date": "The calendar (dim_date). Marked as the date table on calendar_date; the financial year runs July to June.",
    "Organisation": "The organisations that have statements (dim_org). Pick exactly one: every amount is blank otherwise.",
    "Account": "The chart of accounts (dim_account): every statement line with its code.",
    "Statement line": "What the statements print, in order (statement_line): put row_label on a matrix's rows and [Amount] in its values.",
    "Statement line account": "Which accounts make up each statement line, with a sign (statement_line_account). Read by [Amount] only.",
    "GL": "Daily profit and loss postings (fact_gl_daily): income +, costs -.",
    "Balance": "Every balance-sheet account at every month end (fact_balance_month), dated on the month's last day.",
    "Cash flow": "Every cash-flow line for every month (fact_cash_flow_month), dated on the month's last day.",
}
RELATIONSHIPS = [   # many side -> one side, single direction
    ("GL", "date_key", "Date", "date_key"), ("GL", "org_id", "Organisation", "org_id"), ("GL", "account_id", "Account", "account_id"),
    ("Balance", "date_key", "Date", "date_key"), ("Balance", "org_id", "Organisation", "org_id"), ("Balance", "account_id", "Account", "account_id"),
    ("Cash flow", "date_key", "Date", "date_key"), ("Cash flow", "org_id", "Organisation", "org_id"), ("Cash flow", "account_id", "Account", "account_id"),
    ("Statement line", "org_id", "Organisation", "org_id"),
    ("Statement line account", "line_key", "Statement line", "line_key"),
]
SORT_BY = {("Date", "month_name"): "month_key", ("Date", "day_name"): "day_of_week", ("Statement line", "row_label"): "line_order"}
TYPES = {"INT": ("int64", "Int64.Type", "0"), "VARCHAR": ("string", "type text", None), "DATE": ("dateTime", "type date", "d mmm yyyy"),
         "DECIMAL": ("double", "type number", "#,0.0")}
EXTRA_TYPES = {"text": "VARCHAR", "int": "INT"}

AMOUNT_FORMAT = "#,0;(#,0);-"
PCT_FORMAT = "0.0%;(0.0%);-"

# ------------------------------------------------------------------ the measures (DAX)

MEASURES = [
    ("Amount", """
VAR _kind = SELECTEDVALUE ( 'Statement line'[line_kind] )
VAR _statement = SELECTEDVALUE ( 'Statement line'[statement] )
VAR _plus = CALCULATETABLE ( VALUES ( 'Statement line account'[account_id] ), 'Statement line account'[factor] = 1 )
VAR _minus = CALCULATETABLE ( VALUES ( 'Statement line account'[account_id] ), 'Statement line account'[factor] = -1 )
VAR _first = MIN ( 'Date'[calendar_date] )
VAR _last = MAX ( 'Date'[calendar_date] )
VAR _pnl =
    CALCULATE ( SUM ( GL[amount] ), REMOVEFILTERS ( Account ), TREATAS ( _plus, Account[account_id] ) )
        - CALCULATE ( SUM ( GL[amount] ), REMOVEFILTERS ( Account ), TREATAS ( _minus, Account[account_id] ) )
VAR _flows =
    CALCULATE ( SUM ( 'Cash flow'[amount] ), REMOVEFILTERS ( Account ), TREATAS ( _plus, Account[account_id] ) )
        - CALCULATE ( SUM ( 'Cash flow'[amount] ), REMOVEFILTERS ( Account ), TREATAS ( _minus, Account[account_id] ) )
VAR _closing =
    CALCULATE ( SUM ( Balance[amount] ), REMOVEFILTERS ( Account ), TREATAS ( _plus, Account[account_id] ), 'Date'[calendar_date] = _last )
        - CALCULATE ( SUM ( Balance[amount] ), REMOVEFILTERS ( Account ), TREATAS ( _minus, Account[account_id] ), 'Date'[calendar_date] = _last )
VAR _opening =
    CALCULATE ( SUM ( Balance[amount] ), REMOVEFILTERS ( Account ), TREATAS ( _plus, Account[account_id] ), 'Date'[calendar_date] = _first - 1 )
VAR _hasData =
    SWITCH (
        _statement,
        "P&L", NOT ISEMPTY ( GL ),
        "Balance sheet", CALCULATE ( NOT ISEMPTY ( Balance ), 'Date'[calendar_date] = _last ),
        "Cash flow", NOT ISEMPTY ( 'Cash flow' )
    )
VAR _value =
    SWITCH (
        TRUE (),
        _kind = "opening_cash", _opening,
        _kind = "closing_cash" || _statement = "Balance sheet", _closing,
        _statement = "Cash flow", _flows,
        _pnl
    )
RETURN
    IF (
        HASONEVALUE ( Organisation[org_id] ) && NOT ISBLANK ( _kind ) && _hasData,
        IF (
            _kind = "heading",
            0,
            IF ( ISBLANK ( _value ) && SELECTEDVALUE ( 'Statement line'[show_when_zero] ) = 1, 0, _value )
        )
    )""", "Every line of every statement for the period in context: an account's own amount, or a subtotal as the sum of "
          "its accounts (statement_line_account). P&L and cash flow add up the period; the balance sheet is at the period's "
          "last day. Headings return 0 shown as blank, so their row prints.",
     """IF ( SELECTEDVALUE ( 'Statement line'[line_kind] ) = "heading", " ", \"""" + AMOUNT_FORMAT + """\" )"""),
    ("Statement title", """
VAR _org = SELECTEDVALUE ( Organisation[legal_name] )
VAR _month = SELECTEDVALUE ( 'Date'[month_name] )
RETURN
    IF ( ISBLANK ( _org ), "Pick one organisation", _org & IF ( NOT ISBLANK ( _month ), ", " & _month ) )""",
     "The page heading: the organisation and the month.", None),
    ("Month status", """
VAR _status = SELECTEDVALUE ( 'Date'[month_status] )
RETURN
    SWITCH (
        _status,
        "Locked", "Locked: the month is closed",
        "Provisional", "Provisional: the month is over but not yet locked",
        "Incomplete", "Incomplete: the month to date",
        _status
    )""", "Whether the numbers can still change (dim_date.month_status).", None),
    ("Balance sheet check", """
VAR _netAssets = CALCULATE ( [Amount], 'Statement line'[role] = "net_assets" )
VAR _equity = CALCULATE ( [Amount], 'Statement line'[role] = "equity" )
RETURN
    IF ( NOT ISBLANK ( _netAssets ), _netAssets - _equity )""",
     "Net assets less equity: 0 when the balance sheet balances.", AMOUNT_FORMAT),
    ("Cash flow check", """
VAR _opening = CALCULATE ( [Amount], 'Statement line'[role] = "opening_cash" )
VAR _change = CALCULATE ( [Amount], 'Statement line'[role] = "net_change" )
VAR _closing = CALCULATE ( [Amount], 'Statement line'[role] = "closing_cash" )
RETURN
    IF ( NOT ISBLANK ( _change ), _opening + _change - _closing )""",
     "Cash at the start + the net cash flow - cash at the end: 0 when the cash flow ends on the balance sheet's cash.", AMOUNT_FORMAT),
    ("Profit check", """
VAR _profit = CALCULATE ( [Amount], 'Statement line'[role] = "profit" )
VAR _ledger = IF ( HASONEVALUE ( Organisation[org_id] ), SUM ( GL[amount] ) )
RETURN
    IF ( NOT ISBLANK ( _ledger ), _profit - _ledger )""",
     "The P&L's bottom line less everything posted to the ledger: 0 when no account is missing from the layout.", AMOUNT_FORMAT),
]

# The "Period view" calculation group: (name, DAX, format string or None to keep the measure's)
_LAST = "VAR _last = MAX ( 'Date'[calendar_date] )\n"
_FY_START = _LAST + "VAR _start = DATE ( YEAR ( _last ) - IF ( MONTH ( _last ) < 7, 1, 0 ), 7, 1 )\n"
_YTD = "CALCULATE ( SELECTEDMEASURE (), DATESBETWEEN ( 'Date'[calendar_date], _start, _last ) )"
_LYTD = "CALCULATE ( SELECTEDMEASURE (), DATESBETWEEN ( 'Date'[calendar_date], EDATE ( _start, -12 ), EDATE ( _last, -12 ) ) )"
_LM = "CALCULATE ( SELECTEDMEASURE (), DATEADD ( 'Date'[calendar_date], -1, MONTH ) )"
_LY = "CALCULATE ( SELECTEDMEASURE (), DATEADD ( 'Date'[calendar_date], -1, YEAR ) )"
_JUNE = _LAST + "VAR _june = DATE ( YEAR ( _last ) - IF ( MONTH ( _last ) < 7, 1, 0 ), 6, 30 )\n"
PERIOD_VIEW = [
    ("This month", "SELECTEDMEASURE ()", None),
    ("Last month", _LM, None),
    ("Change on last month", f"SELECTEDMEASURE () - {_LM}", None),
    ("% change on last month", f"VAR _before = {_LM}\nRETURN\n    DIVIDE ( SELECTEDMEASURE () - _before, ABS ( _before ) )", PCT_FORMAT),
    ("Same month last year", _LY, None),
    ("Change on last year", f"SELECTEDMEASURE () - {_LY}", None),
    ("% change on last year", f"VAR _before = {_LY}\nRETURN\n    DIVIDE ( SELECTEDMEASURE () - _before, ABS ( _before ) )", PCT_FORMAT),
    ("Year to date", _FY_START + "RETURN\n    " + _YTD, None),
    ("Last year to date", _FY_START + "RETURN\n    " + _LYTD, None),
    ("Change on last year to date", _FY_START + f"RETURN\n    {_YTD} - {_LYTD}", None),
    ("At 30 June", _JUNE + "RETURN\n    CALCULATE ( SELECTEDMEASURE (), 'Date'[calendar_date] = _june )", None),
    ("Change since 30 June", _JUNE + "RETURN\n    SELECTEDMEASURE () - CALCULATE ( SELECTEDMEASURE (), 'Date'[calendar_date] = _june )", None),
]

# The report: (page, statement shown, the Period view columns)
PAGES = [
    ("Profit and loss", "P&L", ["This month", "Last month", "Change on last month", "Same month last year", "Change on last year",
                                "Year to date", "Last year to date", "Change on last year to date"]),
    ("Balance sheet", "Balance sheet", ["This month", "Last month", "Change on last month", "At 30 June", "Change since 30 June"]),
    ("Cash flow", "Cash flow", ["This month", "Last month", "Year to date", "Last year to date"]),
    ("Checks", None, None),
]
THEME = {
    "name": "The Fourth Sheet",
    "dataColors": ["#0E9F6E", "#A7B0B8", "#2F2F2F", "#5F6F63", "#7FCFB3", "#D9DEE2"],
    "foreground": "#25342A", "foregroundNeutralSecondary": "#5F6F63", "background": "#FFFFFF", "tableAccent": "#0E9F6E",
    "good": "#0E9F6E", "neutral": "#A7B0B8", "bad": "#2F2F2F",
    "textClasses": {"title": {"fontFace": "Segoe UI Semibold", "fontSize": 14, "color": "#25342A"},
                    "label": {"fontFace": "Segoe UI", "fontSize": 10, "color": "#25342A"}},
}


# ------------------------------------------------------------------ helpers

def tag(*parts):
    return str(uuid.uuid5(NS, "|".join(parts)))


RESERVED = {"Date"}      # DAX function names: always quoted, as Power BI writes them


def q(name):
    """A TMDL / DAX object name, quoted when it needs to be."""
    plain = name.replace("_", "").isalnum() and not name[0].isdigit() and name not in RESERVED
    return name if plain else "'" + name.replace("'", "''") + "'"


def block(text, tabs):
    """A multi-line expression, indented under its declaration."""
    return "\n".join(("\t" * tabs + ln) if ln.strip() else "" for ln in text.strip("\n").split("\n"))


def m_string(s):
    return '"' + s.replace('"', '""') + '"'


def schema_tables():
    from database import schema
    if not schema.schema_file().exists():
        raise SystemExit(f"No schema.sql at {schema.schema_file()}: run stage 1 first (python3 tools/1_build_data/sample_data.py)")
    return schema.tables()


def columns_for(src_cols, extra):
    out = [(c, t.split("(")[0]) for c, t in src_cols]
    names = {c for c, _ in out}
    out += [(c, EXTRA_TYPES[t]) for c, t in extra if c not in names]
    return out


def default_month():
    """The most recent locked month (what the website's reports open on), as dim_date's month_name."""
    from datetime import date
    y, m = ds.AS_AT.year, ds.AS_AT.month
    for _ in range(36):
        mo = f"{y}-{m:02d}"
        if ds.month_status(mo)[0] == "Locked":
            return date(y, m, 1).strftime("%b %Y"), mo
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    raise SystemExit("No locked month in the last three years: lock one (tools/lock_period.py)")


# ------------------------------------------------------------------ TMDL

def partition_m(model_name, src, cols, extra):
    types = ", ".join(f'{{"{c}", {TYPES[t][1]}}}' for c, t in cols if c not in {e for e, _ in extra})
    load = f'LoadTable("{src}", {{{types}}})'
    if model_name in ("Balance", "Cash flow"):
        return f"""let
    Source = {load},
    Dated = Table.AddColumn(Source, "date_key", each Number.From(Date.ToText(Date.EndOfMonth(Date.FromText([month_key] & "-01")), "yyyyMMdd")), Int64.Type)
in
    Dated"""
    if model_name == "Statement line":
        return f"""let
    Source = {load},
    // detail lines indented with an em space (Power BI trims ordinary leading spaces). A label shared by two
    // organisations (or two statements) must still sort by its own line_order: invisible zero-width spaces make every
    // row_label unique, so 'Sort by column' works and the matrix shows the plain label
    Orgs = List.Sort(List.Distinct(Source[org_id])),
    Statements = {{"P&L", "Balance sheet", "Cash flow"}},
    Labelled = Table.AddColumn(Source, "row_label", each (if [line_level] = "detail" then Character.FromNumber(8195) else "")
        & [line] & Text.Repeat(Character.FromNumber(8203), List.PositionOf(Orgs, [org_id]) * 3 + List.PositionOf(Statements, [statement])), type text)
in
    Labelled"""
    if model_name == "Organisation":
        return f"""let
    Source = {load},
    WithStatements = List.Distinct(LoadTable("statement_line", {{{{"org_id", type text}}}})[org_id]),
    Kept = Table.SelectRows(Source, each List.Contains(WithStatements, [org_id]))
in
    Kept"""
    return load


def table_tmdl(model_name, src, cols, hidden, extra):
    lines = []
    if model_name in DESCRIPTIONS:
        lines.append(f"/// {DESCRIPTIONS[model_name]}")
    lines += [f"table {q(model_name)}", f"\tlineageTag: {tag('table', model_name)}"]
    if model_name == "Date":
        lines.append("\tdataCategory: Time")
    if model_name in HIDDEN_TABLES:
        lines.append("\tisHidden")
    lines.append("")
    if model_name == "Statement line":
        for name, dax, desc, fmt in MEASURES:
            lines.append(f"\t/// {desc}")
            lines.append(f"\tmeasure {q(name)} =")
            lines.append(block(dax, 3))
            if fmt and fmt.startswith("IF"):
                lines.append(f"\t\tformatStringDefinition = {fmt}")
            elif fmt:
                lines.append(f"\t\tformatString: {fmt}")
            lines.append(f"\t\tlineageTag: {tag('measure', name)}")
            lines.append("")
    for c, t in cols:
        dtype, _, fmt = TYPES[t]
        lines.append(f"\tcolumn {q(c)}")
        lines.append(f"\t\tdataType: {dtype}")
        if model_name == "Date" and c == "calendar_date":
            lines.append("\t\tisKey")
        if c in hidden or model_name in HIDDEN_TABLES:
            lines.append("\t\tisHidden")
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        lines.append(f"\t\tlineageTag: {tag('column', model_name, c)}")
        lines.append("\t\tsummarizeBy: none")
        lines.append(f"\t\tsourceColumn: {c}")
        if (model_name, c) in SORT_BY:
            lines.append(f"\t\tsortByColumn: {SORT_BY[(model_name, c)]}")
        if dtype == "dateTime":
            lines += ["", "\t\tannotation UnderlyingDateTimeDataType = Date"]
        lines += ["", "\t\tannotation SummarizationSetBy = User", ""]
    lines.append(f"\tpartition {q(model_name)} = m")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    lines.append(block(partition_m(model_name, src, cols, extra), 4))
    lines += ["", "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(lines)


def period_view_tmdl():
    lines = ["/// Turns any measure into this month, last month, year to date and the changes. Put 'view' on a matrix's columns",
             "/// and filter it to the views the page needs. Every view works on the period in context (the Month slicer).",
             "table 'Period view'", f"\tlineageTag: {tag('table', 'Period view')}", "", "\tcalculationGroup", "\t\tprecedence: 1", ""]
    for i, (name, dax, fmt) in enumerate(PERIOD_VIEW):
        lines.append(f"\t\tcalculationItem {q(name)} =")
        lines.append(block(dax, 4))
        lines.append(f"\t\t\tordinal: {i}")
        if fmt:
            lines.append(f'\t\t\tformatStringDefinition = "{fmt}"')
        lines.append("")
    lines += ["\tcolumn view", "\t\tdataType: string", f"\t\tlineageTag: {tag('column', 'Period view', 'view')}", "\t\tsummarizeBy: none",
              "\t\tsourceColumn: Name", "\t\tsortByColumn: Ordinal", "", "\t\tannotation SummarizationSetBy = Automatic", "",
              "\tcolumn Ordinal", "\t\tdataType: int64", "\t\tisHidden", "\t\tformatString: 0", f"\t\tlineageTag: {tag('column', 'Period view', 'Ordinal')}",
              "\t\tsummarizeBy: sum", "\t\tsourceColumn: Ordinal", "", "\t\tannotation SummarizationSetBy = Automatic", ""]
    return "\n".join(lines)


def expressions_tmdl():
    from database import config
    d = config.DEFAULTS
    server = f"{d['SQL_SERVER']}.database.windows.net"
    load = """(name as text, types as list) as table =>
let
    FromSql = () => Sql.Database(SqlServer, SqlDatabase){[Schema = "dbo", Item = name]}[Data],
    // every <name>.csv anywhere under the Data folder: one per organisation for the month-end tables, combined
    FromCsv = () =>
        let
            Files = Table.SelectRows(Folder.Files(DataFolder), each Text.Lower([Name]) = Text.Lower(name) & ".csv"),
            Tables = List.Transform(Files[Content], each Table.PromoteHeaders(
                Csv.Document(_, [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]), [PromoteAllScalars = false])),
            Combined = if List.IsEmpty(Tables) then error "No " & name & ".csv under " & DataFolder else Table.Combine(Tables),
            Kept = Table.SelectColumns(Combined, List.Transform(types, each _{0})),
            Nulls = Table.ReplaceValue(Kept, "", null, Replacer.ReplaceValue, Table.ColumnNames(Kept))
        in
            Nulls,
    Raw = if DataSource = "Azure SQL" then Table.SelectColumns(FromSql(), List.Transform(types, each _{0})) else FromCsv(),
    Typed = Table.TransformColumnTypes(Raw, types, "en-AU")
in
    Typed"""
    params = [
        ("DataSource", '"CSV" meta [IsParameterQuery = true, List = {"CSV", "Azure SQL"}, DefaultValue = "CSV", Type = "Text", IsParameterQueryRequired = true]',
         "Where the data comes from: the CSVs in DataFolder, or the Azure SQL database."),
        ("DataFolder", m_string(r"C:\Users\you\OneDrive\Projects\The Fourth Sheet\Data") + ' meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]',
         "The OneDrive Data folder (with DataSource = CSV). Set it to this machine's path."),
        ("SqlServer", m_string(server) + ' meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]',
         "The Azure SQL server (with DataSource = Azure SQL). Sign in with your Microsoft account; no password is stored."),
        ("SqlDatabase", m_string(d["SQL_DATABASE"]) + ' meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]',
         "The Azure SQL database."),
    ]
    out = []
    for name, expr, desc in params:
        out += [f"/// {desc}", f"expression {name} = {expr}", f"\tlineageTag: {tag('expression', name)}", "", "\tannotation PBI_ResultType = Text", ""]
    out += ["/// Loads one table by name, typed: from the CSVs or from Azure SQL (DataSource).", "expression LoadTable =", block(load, 2),
            f"\tlineageTag: {tag('expression', 'LoadTable')}", "", "\tannotation PBI_ResultType = Function", ""]
    return "\n".join(out)


def model_tmdl(names):
    order = ["DataSource", "DataFolder", "SqlServer", "SqlDatabase", "LoadTable"] + names
    return "\n".join([
        "model Model", "\tculture: en-AU", "\tdefaultPowerBIDataSourceVersion: powerBI_V3", "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-AU", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
        "annotation __PBI_TimeIntelligenceEnabled = 0", "", f"annotation PBI_QueryOrder = {json.dumps(order)}", "",
    ] + [f"ref table {q(n)}" for n in names + ["Period view"]] + [""])


def relationships_tmdl():
    out = []
    for ft, fc, tt, tc in RELATIONSHIPS:
        out += [f"relationship {tag('relationship', ft, fc, tt, tc)}", f"\tfromColumn: {q(ft)}.{q(fc)}", f"\ttoColumn: {q(tt)}.{q(tc)}", ""]
    return "\n".join(out)


# ------------------------------------------------------------------ PBIR (the report)

def col(entity, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def measure(entity, prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def projection(field, entity, prop):
    return {"field": field, "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}


def in_filter(entity, prop, values):
    return {"Version": 2, "From": [{"Name": "t", "Entity": entity, "Type": 0}],
            "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": prop}}],
                                            "Values": [[{"Literal": {"Value": "'" + v.replace("'", "''") + "'"}}] for v in values]}}}]}


def container(name, x, y, w, h, z, visual, filters=None, page=""):
    v = {"$schema": SCHEMA + "item/report/definition/visualContainer/2.0.0/schema.json", "name": name,
         "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z}, "visual": visual}
    if filters:
        v["filterConfig"] = {"filters": [{"name": f"{page}{name}{i}", "field": col(e, p), "type": "Categorical", "filter": in_filter(e, p, vals),
                                          "isHiddenInViewMode": True} for i, (e, p, vals) in enumerate(filters)]}
    return v


def title(text, size="12"):
    return {"title": [{"properties": {"show": lit("true"), "text": lit("'" + text + "'"), "fontSize": lit(f"{size}D")}}]}


def slicer(entity, prop, group, selected, label):
    return {"visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [dict(projection(col(entity, prop), entity, prop), active=True)]}}},
            "objects": {"data": [{"properties": {"mode": lit("'Dropdown'")}}],
                        "selection": [{"properties": {"singleSelect": lit("true")}}],
                        "general": [{"properties": {"filter": {"filter": in_filter(entity, prop, [selected])}}}]},
            "visualContainerObjects": title(label, "10"),
            "syncGroup": {"groupName": group, "fieldChanges": True, "filterChanges": True},
            "drillFilterOtherVisuals": True}


def card(entity, prop, size):
    return {"visualType": "card",
            "query": {"queryState": {"Values": {"projections": [projection(measure(entity, prop), entity, prop)]}}},
            "objects": {"labels": [{"properties": {"fontSize": lit(f"{size}D")}}], "categoryLabels": [{"properties": {"show": lit("false")}}]},
            "drillFilterOtherVisuals": True}


def matrix():
    return {"visualType": "pivotTable",
            "query": {"queryState": {
                "Rows": {"projections": [dict(projection(col("Statement line", "row_label"), "Statement line", "row_label"), active=True)]},
                "Columns": {"projections": [dict(projection(col("Period view", "view"), "Period view", "view"), active=True)]},
                "Values": {"projections": [projection(measure("Statement line", "Amount"), "Statement line", "Amount")]}}},
            "objects": {"subTotals": [{"properties": {"rowSubtotals": lit("false"), "columnSubtotals": lit("false")}}],
                        "rowHeaders": [{"properties": {"fontSize": lit("10D")}}],
                        "values": [{"properties": {"fontSize": lit("10D")}}],
                        "columnHeaders": [{"properties": {"fontSize": lit("10D"), "alignment": lit("'Right'")}}]},
            "drillFilterOtherVisuals": True}


def checks_table():
    proj = [projection(col("Date", "month_name"), "Date", "month_name")] + \
           [projection(measure("Statement line", m), "Statement line", m) for m in ("Balance sheet check", "Cash flow check", "Profit check")]
    return {"visualType": "tableEx", "query": {"queryState": {"Values": {"projections": proj}},
                                               "sortDefinition": {"sort": [{"field": col("Date", "month_name"), "direction": "Descending"}]}},
            "visualContainerObjects": title("Every check should be - (zero) in every month"),
            "drillFilterOtherVisuals": True}


def report_files(month_label, org_label):
    files = {}
    base = f"{NAME}.Report"
    files[f"{base}/.platform"] = platform("Report")
    files[f"{base}/definition.pbir"] = {"$schema": SCHEMA + "item/report/definitionProperties/2.0.0/schema.json", "version": "4.0",
                                        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}}
    files[f"{base}/definition/version.json"] = {"$schema": SCHEMA + "item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}
    files[f"{base}/definition/report.json"] = {
        "$schema": SCHEMA + "item/report/definition/report/1.3.0/schema.json",
        "themeCollection": {"customTheme": {"name": "TheFourthSheet.json", "reportVersionAtImport": "5.59", "type": "RegisteredResources"}},
        "layoutOptimization": "None",
        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                              "items": [{"name": "TheFourthSheet.json", "path": "TheFourthSheet.json", "type": "CustomTheme"}]}],
        "settings": {"exportDataMode": "AllowSummarized", "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True}}
    files[f"{base}/StaticResources/RegisteredResources/TheFourthSheet.json"] = THEME
    ids = []
    for page, statement, views in PAGES:
        pid = tag("page", page).replace("-", "")[:20]
        ids.append(pid)
        p = f"{base}/definition/pages/{pid}"
        files[f"{p}/page.json"] = {"$schema": SCHEMA + "item/report/definition/page/1.4.0/schema.json", "name": pid, "displayName": page,
                                   "displayOption": "FitToPage", "height": 720, "width": 1280}
        vis = [container("title", 24, 12, 820, 52, 1000, card("Statement line", "Statement title", "18")),
               container("org", 24, 72, 360, 64, 3000, slicer("Organisation", "legal_name", "Organisation", org_label, "Organisation"))]
        if statement:
            vis += [container("status", 860, 12, 396, 52, 2000, card("Statement line", "Month status", "11")),
                    container("month", 400, 72, 220, 64, 4000, slicer("Date", "month_name", "Month", month_label, "Month")),
                    container("statement", 24, 148, 1232, 560, 5000, matrix(),
                              [("Statement line", "statement", [statement]), ("Period view", "view", views)], pid)]
        else:       # every month at once, so no Month slicer here
            vis.append(container("checks", 24, 148, 720, 560, 5000, checks_table()))
        for v in vis:
            files[f"{p}/visuals/{v['name']}/visual.json"] = v
    files[f"{base}/definition/pages/pages.json"] = {"$schema": SCHEMA + "item/report/definition/pagesMetadata/1.0.0/schema.json",
                                                    "pageOrder": ids, "activePageName": ids[0]}
    return files


def platform(kind):
    return {"$schema": SCHEMA + "gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": kind, "displayName": NAME}, "config": {"version": "2.0", "logicalId": tag("item", kind)}}


# ------------------------------------------------------------------ the numbers each page must show

def expected():
    """What each statement page must show for the default month, every organisation, worked out from the CSVs by the
    same rules as [Amount] and the Period view (a Python copy of the DAX). Markdown, for OneDrive (it's sample data)."""
    import csv
    from datetime import date, timedelta
    import sync_media
    data = sync_media.onedrive_root() / "Data" / "Month-end dashboard"

    def rows(name):
        out = []
        for f in sorted(data.glob(f"*/{name}.csv")):
            with open(f, newline="", encoding="utf-8") as fh:
                out += list(csv.DictReader(fh))
        return out

    def month_end(mo):
        y, m = int(mo[:4]), int(mo[5:])
        return date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)

    gl = [(r["org_id"], date(int(r["date_key"][:4]), int(r["date_key"][4:6]), int(r["date_key"][6:])), int(r["account_id"]), int(r["amount"]))
          for r in rows("fact_gl_daily")]
    bal = {(r["org_id"], month_end(r["month_key"]), int(r["account_id"])): int(r["amount"]) for r in rows("fact_balance_month")}
    cf = [(r["org_id"], month_end(r["month_key"]), int(r["account_id"]), int(r["amount"])) for r in rows("fact_cash_flow_month")]
    parts = {}
    for r in rows("statement_line_account"):
        parts.setdefault(int(r["line_key"]), []).append((int(r["account_id"]), int(r["factor"])))
    lines = sorted(rows("statement_line"), key=lambda r: (r["org_id"], r["statement"], int(r["line_order"])))

    def amount(ln, a, b):
        """[Amount] for one line over the dates a..b."""
        org, st, kind, p = ln["org_id"], ln["statement"], ln["line_kind"], parts.get(int(ln["line_key"]), [])
        has = {"P&L": any(o == org and a <= d <= b for o, d, *_ in gl), "Balance sheet": any(k[0] == org and k[1] == b for k in bal),
               "Cash flow": any(o == org and a <= d <= b for o, d, *_ in cf)}[st]
        if not has:
            return None
        if kind == "heading":
            return ""
        if kind == "opening_cash":
            v = sum(f * bal[(org, a - timedelta(days=1), x)] for x, f in p if (org, a - timedelta(days=1), x) in bal) \
                if any((org, a - timedelta(days=1), x) in bal for x, _ in p) else None
        elif kind == "closing_cash" or st == "Balance sheet":
            v = sum(f * bal[(org, b, x)] for x, f in p if (org, b, x) in bal) if any((org, b, x) in bal for x, _ in p) else None
        else:
            src = gl if st == "P&L" else cf
            hits = [f * amt for o, d, x, amt in src for x2, f in p if o == org and a <= d <= b and x == x2]
            v = sum(hits) if hits else None
        return 0 if v is None and ln["show_when_zero"] == "1" else v

    label, mo = default_month()
    end = month_end(mo)
    start = end.replace(day=1)
    fy = date(end.year - (end.month < 7), 7, 1)
    prev_end = start - timedelta(days=1)
    june = date(end.year - (end.month < 7), 6, 30)
    ly_end = month_end(f"{end.year - 1}-{end.month:02d}")
    views = {"This month": (start, end), "Last month": (prev_end.replace(day=1), prev_end), "Same month last year": (ly_end.replace(day=1), ly_end),
             "Year to date": (fy, end), "Last year to date": (fy.replace(year=fy.year - 1), ly_end), "At 30 June": (june, june)}
    money = lambda v: "" if v in (None, "") else "-" if v == 0 else f"({-v:,})" if v < 0 else f"{v:,}"    # noqa: E731
    out = [f"# Financial statements: what Power BI must show for {label}", "",
           "Generated by tools/3_publish_site/powerbi_statements.py from the CSVs, with the same rules as the [Amount] measure "
           "and the Period view. Open powerbi/Financial statements.pbip, pick the organisation and the month, and every number "
           "on the Profit and loss, Balance sheet and Cash flow pages should match these. Blank = the row doesn't show.", ""]
    names = {r["org_id"]: r["legal_name"] for r in csv.DictReader(open(data.parent / "Common" / "dim_org.csv", newline="", encoding="utf-8"))}
    for org in sorted({ln["org_id"] for ln in lines}):
        out += [f"## {names.get(org, org)}", ""]
        for page, st, cols in PAGES[:3]:
            cols = [c for c in cols if c in views]
            out += [f"### {page}", "", "| Line | " + " | ".join(cols) + " |", "|---|" + "---:|" * len(cols)]
            for ln in (x for x in lines if x["org_id"] == org and x["statement"] == st):
                vals = [amount(ln, *views[c]) for c in cols]
                if any(v is not None for v in vals):
                    name = f"**{ln['line']}**" if ln["line_level"] in ("heading", "key") else ln["line"]
                    out.append(f"| {name} | " + " | ".join(money(v) for v in vals) + " |")
            out.append("")
    return "\n".join(out)


def write_expected():
    import sync_media
    out = sync_media.onedrive_root() / "Data documentation" / "Power BI"
    out.mkdir(parents=True, exist_ok=True)
    f = out / "Financial statements - expected numbers.md"
    f.write_text(expected(), encoding="utf-8")
    return f


# ------------------------------------------------------------------ write

def build():
    """{relative path: text} for every file of the project."""
    st = schema_tables()
    files, names = {}, []
    sm = f"{NAME}.SemanticModel"
    for model_name, src, hidden, extra in TABLES:
        if src not in st:
            raise SystemExit(f"schema.sql has no table {src}: run stage 1 first")
        cols = columns_for(st[src].columns, extra)
        files[f"{sm}/definition/tables/{model_name}.tmdl"] = table_tmdl(model_name, src, cols, hidden, extra)
        names.append(model_name)
    files[f"{sm}/definition/tables/Period view.tmdl"] = period_view_tmdl()
    files[f"{sm}/definition/database.tmdl"] = "database\n\tcompatibilityLevel: 1601\n"
    files[f"{sm}/definition/model.tmdl"] = model_tmdl(names)
    files[f"{sm}/definition/expressions.tmdl"] = expressions_tmdl()
    files[f"{sm}/definition/relationships.tmdl"] = relationships_tmdl()
    files[f"{sm}/definition.pbism"] = {"$schema": SCHEMA + "item/semanticModel/definitionProperties/1.0.0/schema.json", "version": "4.0", "settings": {}}
    files[f"{sm}/.platform"] = platform("SemanticModel")
    files.update(report_files(default_month()[0], fm.TRADES["long_name"]))
    files[f"{NAME}.pbip"] = {"$schema": SCHEMA + "pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
                             "artifacts": [{"report": {"path": f"{NAME}.Report"}}], "settings": {"enableAutoRecovery": True}}
    return {k: (json.dumps(v, indent=2, ensure_ascii=False) + "\n" if isinstance(v, dict) else v) for k, v in files.items()}


def write(quiet=False):
    files = build()
    changed = 0
    for rel, text in files.items():
        path = OUT / rel
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        changed += 1
    # files this program wrote before that it no longer makes (a page or table taken out); Desktop's own files are left alone
    for path in [p for p in OUT.rglob("*") if p.is_file()]:
        rel = path.relative_to(OUT).as_posix()
        if rel not in files and (rel.endswith(".tmdl") or "/definition/pages/" in rel) and "/.pbi/" not in rel:
            path.unlink()
            changed += 1
    exp = write_expected()
    if not quiet:
        print(f"Power BI project: {len(files)} files in {OUT.relative_to(REPO)}/ ({changed} changed); the numbers it must show: {exp}")
    return changed


if __name__ == "__main__":
    write()
