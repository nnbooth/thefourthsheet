#!/usr/bin/env python3
"""
datasets.py — the Retail, Health and Legal datasets: trimmed, made synthetic, brought up to date, checked, and
written as CSVs (OneDrive Data/<dataset>/) with a schema for the database (Data documentation/schema-<dataset>.sql).

    python3 tools/1_build_data/datasets.py              all three
    python3 tools/1_build_data/datasets.py retail       one

Always reads the ORIGINALS from OneDrive Archive/Dataset originals/ (copied there on the first run), so it can be
re-run safely and never edits its own output. What it does:

  Retail  (was one 64 MB workbook, Jul 2021 to Jul 2026, 476 stores, ~750,000 fact rows)
    - one CSV per table, snake_case columns, date_key as INT yyyymmdd, other dates as DATE
    - trimmed to Oct 2024 onwards and about a quarter of the stores (every retailer, state, channel and rep kept);
      whole orders are kept with all their sales lines and deliveries; budgets scaled to the stores kept
    - names made synthetic: retailers, stores, carriers (and tracking links), people, retailer promotions
    - facts carry keys (carrier_id, delivery_status_id, cancellation reason_id) instead of names
    - brought up to 6 Oct 2026: new orders, sales and deliveries modelled on the same weeks a year earlier;
      deliveries not due yet stay open; old 'in transit' deliveries are completed
  Health  (Jan 2023 to Jun 2026)
    - provider names made synthetic; dim_date loses the legal-only court vacation column
    - brought up to 6 Oct 2026 (appointments and claims modelled on the same weeks a year earlier);
      old pending claims are settled; claims not yet paid stay pending
  Legal   (Jan 2023 to Dec 2026: it ran into the future)
    - fee earner names made synthetic; repeated office and practice-area names dropped from the facts and
      dim_matter (they're in their own dimensions: a star schema keeps descriptions in one place)
    - nothing after 6 Oct 2026 except budgets (plans); work not yet billed stays as unbilled work
    - new matters opened Jul to Oct 2026, modelled on a year earlier
    - each matter's totals recalculated from its work, invoices and disbursements, so they always agree
Every dataset is checked before it's written: unique keys, every key resolves, totals agree, nothing dated after
the 'as at' time except plans. Purchasing is left as it is (not used in its current form).
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import math
import pickle
import random
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
import winutf8; winutf8.ensure()   # Windows: run in UTF-8 mode (the tools write characters like ¢ and ▲)

import pandas as pd

from ids import scattered

import data_status as ds              # noqa: E402
from sync_media import onedrive_root  # noqa: E402

AS_AT = pd.Timestamp(ds.AS_AT)
TODAY = pd.Timestamp(ds.AS_AT.date())
YEAR = timedelta(days=364)            # a year later on the same weekday
ROOT = onedrive_root()
DATA, DOCS = ROOT / "Data", ROOT / "Data documentation"
ORIG = ROOT / "Archive" / "Dataset originals"


def archive_originals():
    """First run: copy the originals into Archive (the Retail workbook is moved out of Data/: data folders hold CSVs)."""
    for name, pattern in (("Retail", "*.xlsx"), ("Health", "*.csv"), ("Legal", "*.csv")):
        dest = ORIG / name
        if dest.exists() and any(dest.iterdir()):
            continue
        dest.mkdir(parents=True, exist_ok=True)
        for f in (DATA / name).glob(pattern):
            shutil.copy2(f, dest / f.name)
            if (dest / f.name).stat().st_size != f.stat().st_size:
                raise SystemExit(f"Copy of {f} didn't complete; nothing was changed.")
        print(f"  originals of {name} kept in {dest}")
    for f in (DATA / "Retail").glob("*.xlsx"):
        if (ORIG / "Retail" / f.name).exists() and (ORIG / "Retail" / f.name).stat().st_size == f.stat().st_size:
            f.unlink()
            print(f"  {f.name} moved out of Data/Retail (the original is in Archive; Data/ holds CSVs)")


# ------------------------------------------------------------------ writing + schema

def sql_type(s):
    v = s.dropna()
    if v.empty:
        return "VARCHAR(50)"
    if pd.api.types.is_bool_dtype(v):
        return "BIT"
    if pd.api.types.is_integer_dtype(v):
        return "BIGINT" if v.abs().max() > 2_000_000_000 else "INT"
    if pd.api.types.is_float_dtype(v):
        if (v == v.round(0)).all():
            return "INT"
        dp = 2 if (v.round(2) == v).all() else 4 if (v.round(4) == v).all() else 6
        return f"DECIMAL({18 if dp < 6 else 12},{dp})"
    if pd.api.types.is_datetime64_any_dtype(v):
        return "DATE"
    txt = v.astype(str)
    return f"VARCHAR({max(10, int(math.ceil(txt.str.len().max() * 1.5 / 10) * 10))})"


def write(dataset, tables, keys, refs, notes):
    """tables: {name: DataFrame}; keys: {name: pk column}; refs: {(table, column): (table, column)}; notes: {name: description}."""
    out = DATA / dataset.capitalize()
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.csv"):
        if old.stem not in tables:
            old.unlink()
    ddl = [f"-- {dataset.capitalize()} dataset (synthetic). Generated by tools/1_build_data/datasets.py. Load with tools/2_load_azure/database/load.py.",
           f"-- Every table lives in schema {dataset}; dimensions are created before the facts that reference them.", ""]
    rows = 0
    for name, df in tables.items():
        df = df.copy()
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].dt.strftime("%Y-%m-%d")
        df.to_csv(out / f"{name}.csv", index=False)
        rows += len(df)
        cols = []
        for c in tables[name].columns:
            t = sql_type(tables[name][c])
            if keys.get(name) == c:
                t += " PRIMARY KEY"
            if (name, c) in refs:
                rt, rc = refs[(name, c)]
                t += f" REFERENCES {dataset}.{rt}({rc})"
            cols.append(f"    {c} {t}")
        ddl.append(f"-- {notes.get(name, name)}  [Data/{dataset.capitalize()}/{name}.csv]")
        ddl.append(f"CREATE TABLE {dataset}.{name} (\n" + ",\n".join(cols) + "\n);\n")
    (DOCS / f"schema-{dataset}.sql").write_text("\n".join(ddl), encoding="utf-8")
    print(f"  {dataset}: {len(tables)} tables, {rows:,} rows -> {out}; schema-{dataset}.sql")


def renumber(T, keys, refs, table, col, new):
    """Give a key realistic numbers everywhere it appears: its own table, every column that references it, and any other
    table that uses it as its key. new: a function from the old values (sorted, i.e. in the order they were created) to
    the new ones. Returns {old: new}."""
    old = sorted(T[table][col].dropna().unique())
    m = dict(zip(old, new(old)))
    where = {(table, col)} | {(t, c) for (t, c), (rt, rc) in refs.items() if (rt, rc) == (table, col)} \
        | {(t, col) for t in T if col in T[t].columns}            # a column with the same name is the same key, declared or not
    for t, c in where:
        T[t][c] = T[t][c].map(lambda v: m.get(v, v))
    return m


def shifted(by, fmt=None):
    """Transaction numbers: a running sequence that started long before the data, so shift it up (the gaps stay)."""
    def f(old):
        if fmt:
            pre, width = fmt
            return [f"{pre}{int(str(v)[len(pre):]) + by:0{width}d}" for v in old]
        return [int(v) + by for v in old]
    return f


def spread(start, seed, gap, fmt="{}"):
    """Master records: numbers issued over years with others in between, in the order these were created."""
    return lambda old: [fmt.format(v) for v in scattered(len(old), start, seed, gap)]


def check(dataset, tables, keys, refs, dated=()):
    problems = []
    for name, k in keys.items():
        if tables[name][k].duplicated().any():
            problems.append(f"{name}.{k} isn't unique")
        if tables[name][k].isna().any():
            problems.append(f"{name}.{k} has blanks")
    for (t, c), (rt, rc) in refs.items():
        bad = ~tables[t][c].dropna().isin(tables[rt][rc])
        if bad.any():
            problems.append(f"{t}.{c}: {bad.sum()} value(s) not in {rt}.{rc}, e.g. {tables[t][c].dropna()[bad].iloc[0]}")
    for t, c in dated:
        late = tables[t][c].dropna() > AS_AT
        if late.any():
            problems.append(f"{t}.{c}: {late.sum()} dated after the 'as at' time")
    if problems:
        raise SystemExit(f"{dataset}: checks failed, nothing written:\n  " + "\n  ".join(problems))


def date_dim(start, end, extra=None):
    d = pd.DataFrame({"date": pd.date_range(start, end)})
    d.insert(0, "date_key", d.date.dt.strftime("%Y%m%d").astype(int))
    d["year"], d["month_num"], d["day"] = d.date.dt.year, d.date.dt.month, d.date.dt.day
    d["month_name"], d["quarter"] = d.date.dt.strftime("%B"), "Q" + d.date.dt.quarter.astype(str)
    d["day_name"] = d.date.dt.strftime("%A")
    d["is_weekend"] = (d.date.dt.weekday >= 5).astype(int)
    d["financial_year"] = "FY" + (d.year + (d.month_num >= 7)).astype(str)
    d["fy_quarter"] = "FQ" + (((d.month_num - 7) % 12) // 3 + 1).astype(str)
    d["iso_week"] = d.date.dt.isocalendar().week.astype(int)
    d["month_key"] = d.date.dt.strftime("%Y-%m")
    return d


def key(ts):
    return ts.dt.strftime("%Y%m%d").astype(int)


# ======================================================================= RETAIL

RETAILERS = {"Coles": "Brightway Supermarkets", "Woolworths": "Greenfield Grocers", "IGA": "Local Larder", "FoodWorks": "Corner Pantry",
             "Foodland": "Harbourside Foodmarket", "Ritchies": "Bayline Grocers", "Drakes": "Southvale Fresh", "Shell Coles Express": "Fuelpoint Express",
             "BP Connect": "Roadstop Connect", "Ampol Foodary": "Kestrel Food Stop", "United Petroleum": "Unity Fuel", "7-Eleven": "Daybreak Convenience",
             "OTR": "Overland Stop", "Night Owl": "Nightjar Convenience"}
SHORT = {"Coles": "Brightway", "Woolies": "Greenfield", "Woolworths": "Greenfield", "IGA": "Local Larder", "Drakes": "Southvale", "Night Owl": "Nightjar"}
CARRIERS = {"StarTrack": ("Swiftline Express", "SWF"), "Toll": ("Ridgeway Freight", "RDG"), "TNT": ("Comet Couriers", "CMT"),
            "Australia Post": ("Postmark National", "PMK"), "Linfox": ("Longhaul Logistics", "LHL"), "DHL": ("Globelink Express", "GLB")}
PEOPLE = ["Avery Quill", "Bram Ketteridge", "Cass Penhallow", "Dace Mordaunt", "Elsie Varnham", "Fenn Okoro-Blythe", "Greer Tallis", "Hollis Breck",
          "Ines Calloway", "Jory Wexford", "Kit Ambrose", "Lark Hennessey", "Mace Dunmore", "Nell Faraday", "Orrin Pike", "Pip Lachlan-Rowe",
          "Quinn Ashby", "Rory Stellan", "Sable Corrigan", "Tamsin Holt", "Uma Brightwater", "Vaughn Elsworth", "Wren Castellan", "Yara Kingsmill"]
STORE_SHARE = 0.25
RETAIL_START = pd.Timestamp("2024-10-01")


def retail_sheets():
    src = ORIG / "Retail" / "retaildata.xlsx"
    cache = Path.home() / ".cache" / "fourthsheet" / f"retaildata-{int(src.stat().st_mtime)}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    import openpyxl
    print("  reading the retail workbook (about a minute, once) ...")
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    out = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        df = pd.DataFrame([r for r in rows[1:] if any(v is not None for v in r)], columns=[str(c).lower() for c in rows[0]])
        out[ws.title] = df
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(out))
    return out


def retail():
    S = retail_sheets()
    rnd = random.Random(2026)
    sales, orders, deliv = S["FACT_Sales"].copy(), S["FACT_SalesOrders"].copy(), S["FACT_Deliveries"].copy()
    store, prod, emp = S["DIM_Store"].copy(), S["DIM_Product"].copy(), S["DIM_Employee"].copy()
    carrier, status, reason = S["DIM_Carrier"].copy(), S["DIM_DeliveryStatus"].copy(), S["DIM_CancellationReason"].copy()
    promo, channel, source, budget = S["DIM_Promotion"].copy(), S["DIM_SalesChannel"].copy(), S["DIM_TransactionSource"].copy(), S["BUDGET_ProductMonth"].copy()
    for df in (sales, orders, deliv, promo, emp):
        for c in df.columns:
            if c.endswith("date") or c == "date_key":
                df[c] = pd.to_datetime(df[c])

    # 1. window, and about a quarter of the stores (every retailer x state kept; every active rep kept)
    orders = orders[orders.order_date >= RETAIL_START]
    live = store[store.store_id.isin(orders.store_id)]
    keep = set()
    for _, g in live.groupby(["retailer", "state"]):
        ids = sorted(g.store_id)
        keep |= set(rnd.sample(ids, max(1, round(len(ids) * STORE_SHARE))))
    for rep in sorted(set(orders.sales_rep_id)):
        if not orders[(orders.sales_rep_id == rep) & orders.store_id.isin(keep)].shape[0]:
            keep.add(orders[orders.sales_rep_id == rep].store_id.value_counts().index[0])
    all_net = sales[sales.order_id.isin(orders.order_id)].groupby("sku_code").net_sales.sum()
    orders = orders[orders.store_id.isin(keep)]
    sales = sales[sales.order_id.isin(orders.order_id)]
    deliv = deliv[deliv.order_id.isin(orders.order_id)]
    kept_net = sales.groupby("sku_code").net_sales.sum()
    share = (kept_net / all_net).fillna(STORE_SHARE)

    # 2. finish deliveries the original left open (they'd have arrived by now)
    open_ = deliv.delivery_status.isin(["In Transit", "Scheduled"]) & (deliv.scheduled_delivery_date <= TODAY - timedelta(days=3))
    deliv.loc[open_, "actual_delivery_date"] = deliv.loc[open_, "scheduled_delivery_date"]
    deliv.loc[open_, "qty_received"] = deliv.loc[open_, "qty_dispatched"]
    deliv.loc[open_, ["qty_damaged", "qty_rejected"]] = 0
    deliv.loc[open_, ["delivery_status"]] = "Delivered"
    deliv.loc[open_, ["is_complete", "on_time_flag", "in_full_flag", "difot_flag"]] = "Y"
    done = deliv.groupby("order_id").is_complete.apply(lambda s: (s == "Y").all())
    orders.loc[orders.order_status.isin(["Shipped", "Processing"]) & orders.order_id.map(done).fillna(False), "order_status"] = "Completed"

    # 3. up to 6 Oct 2026: the same weeks a year earlier, a year on (same weekday), with new IDs
    last = orders.order_date.max()
    src = orders[(orders.order_date > last - YEAR) & (orders.order_date <= TODAY - YEAR)].copy()
    num = lambda s: s.str.extract(r"(\d+)$")[0].astype(int)
    o_next, s_next, d_next = num(S["FACT_SalesOrders"].order_id).max() + 1, num(S["FACT_Sales"].transaction_id).max() + 1, num(S["FACT_Deliveries"].delivery_id).max() + 1
    omap = {oid: f"ORD-{o_next + i:07d}" for i, oid in enumerate(sorted(src.order_id))}
    pnext = num(promo.promo_id).max() + 1
    new_promos, pmap = [], {}
    used = sales[sales.order_id.isin(src.order_id)].promo_id.dropna().unique()
    for i, pid in enumerate(sorted(used)):
        p = promo[promo.promo_id == pid].iloc[0].copy()
        p["promo_id"] = f"PRM-{pnext + i:03d}"
        p["promo_name"] = p.promo_name.replace("2025", "2026") if "2025" in p.promo_name else p.promo_name + " 2026"
        p["start_date"], p["end_date"] = p.start_date + YEAR, p.end_date + YEAR
        pmap[pid] = p.promo_id
        new_promos.append(p)
    promo = pd.concat([promo, pd.DataFrame(new_promos)], ignore_index=True)
    reps = emp.set_index("employee_id")
    cur_rep = store.set_index("store_id").current_sales_rep_id

    new_o = src.copy()
    new_o["order_id"] = new_o.order_id.map(omap)
    for c in ("date_key", "order_date", "requested_delivery_date", "cancellation_date"):
        new_o[c] = new_o[c] + YEAR
    new_o["sales_rep_id"] = [cur_rep.get(s_) if pd.notna(reps.end_date.get(r)) and reps.end_date.get(r) < d else r
                             for r, s_, d in zip(new_o.sales_rep_id, new_o.store_id, new_o.order_date)]
    new_s = sales[sales.order_id.isin(src.order_id)].copy()
    new_s["transaction_id"] = [f"TXN-{s_next + i:07d}" for i in range(len(new_s))]
    new_s["order_id"] = new_s.order_id.map(omap)
    new_s["date_key"] = new_s.date_key + YEAR
    new_s["promo_id"] = new_s.promo_id.map(pmap)
    new_s["sales_rep_id"] = new_s.order_id.map(new_o.set_index("order_id").sales_rep_id)
    new_d = deliv[deliv.order_id.isin(src.order_id)].copy()
    new_d["delivery_id"] = [f"DEL-{d_next + i:07d}" for i in range(len(new_d))]
    new_d["order_id"] = new_d.order_id.map(omap)
    new_d["sales_rep_id"] = new_d.order_id.map(new_o.set_index("order_id").sales_rep_id)
    for c in ("dispatch_date", "scheduled_delivery_date", "actual_delivery_date"):
        new_d[c] = new_d[c] + YEAR
    not_yet = new_d.actual_delivery_date > TODAY
    new_d.loc[not_yet, "delivery_status"] = ["In Transit" if d <= TODAY else "Scheduled" for d in new_d.loc[not_yet, "dispatch_date"]]
    new_d.loc[not_yet, ["actual_delivery_date", "qty_received", "qty_damaged", "qty_rejected", "on_time_flag", "in_full_flag", "difot_flag"]] = None
    new_d.loc[not_yet, "is_complete"] = "N"
    new_d.loc[new_d.dispatch_date > TODAY, "dispatch_date"] = pd.NaT
    open_orders = set(new_d.loc[not_yet, "order_id"])
    first_dispatch = new_d.groupby("order_id").dispatch_date.min()
    oo = new_o.order_id.isin(open_orders) & (new_o.order_status != "Cancelled")
    new_o.loc[oo, "order_status"] = ["Shipped" if pd.notna(first_dispatch.get(o)) else "Processing" for o in new_o.loc[oo, "order_id"]]
    orders, sales, deliv = pd.concat([orders, new_o]), pd.concat([sales, new_s]), pd.concat([deliv, new_d])
    promo["is_active"] = ((promo.start_date <= TODAY) & (promo.end_date >= TODAY)).map({True: "Y", False: "N"})
    promo = promo[(promo.end_date >= RETAIL_START) | promo.promo_id.isin(sales.promo_id)]

    # 4. synthetic names, and keys instead of names in the facts
    store = store[store.store_id.isin(keep)].copy()
    store["store_name"] = [n.replace(r, RETAILERS[r], 1) for n, r in zip(store.store_name, store.retailer)]
    store["retailer"] = store.retailer.map(RETAILERS)
    def promo_text(t):
        for k in sorted(set(RETAILERS) | set(SHORT), key=len, reverse=True):
            t = t.replace(k, RETAILERS.get(k) if k in RETAILERS and "," in t else SHORT.get(k, RETAILERS.get(k)))
        return t
    promo["promo_name"] = promo.promo_name.map(promo_text)
    promo["retailer"] = promo.retailer.map(lambda t: ",".join(RETAILERS.get(x.strip(), x.strip()) for x in str(t).split(",")))
    promo["notes"] = promo.notes.fillna("").map(promo_text)
    cid = carrier.set_index("carrier_name").carrier_id
    carrier["tracking_url_template"] = [f"https://tracking.example.com/{CARRIERS[n][1].lower()}/{{tracking}}" for n in carrier.carrier_name]
    deliv["tracking_number"] = [CARRIERS[c][1] + str(t)[3:] if pd.notna(t) else t for c, t in zip(deliv.carrier, deliv.tracking_number)]
    deliv["carrier_id"] = deliv.carrier.map(cid)
    carrier["carrier_name"] = carrier.carrier_name.map(lambda n: CARRIERS[n][0])
    # status names in the deliveries don't all match the status table: map them (Delivered -> late / on time / early, agreeing
    # with the source's on-time flag; Scheduled -> Pending; Late - Full -> Late) and add Backordered, which the table didn't have
    status = pd.concat([status, pd.DataFrame([{"status_id": "DEL-09", "delivery_status": "Backordered", "status_category": "Open",
                                               "is_complete": "N", "counts_for_difot": "N"}])], ignore_index=True)
    sid = status.set_index("delivery_status").status_id.to_dict()
    def status_id(st, sched, actual, on_time):
        if st == "Delivered":      # agree with the source's on-time flag (what DIFOT counts), which follows the dates
            st = "Late" if on_time == "N" else "Early" if actual < sched else "On Time"
        return sid[{"Late - Full": "Late", "Scheduled": "Pending"}.get(st, st)]
    deliv["delivery_status_id"] = [status_id(st, a_, b_, f) for st, a_, b_, f in
                                   zip(deliv.delivery_status, deliv.scheduled_delivery_date, deliv.actual_delivery_date, deliv.on_time_flag)]
    # cancellation reasons are written sometimes as the code (CXL-06), sometimes as the name: both map to the code
    rid = reason.set_index("cancellation_reason").reason_id.to_dict() | {r: r for r in reason.reason_id}
    orders["cancellation_reason_id"] = orders.cancellation_reason.map(lambda x: rid[x] if pd.notna(x) else None)
    # orders marked cancelled but delivered and completed: the deliveries win (not cancelled)
    clash = (orders.is_cancelled == "Y") & (orders.order_status != "Cancelled")
    orders.loc[clash, ["is_cancelled"]] = "N"
    orders.loc[clash, ["cancellation_date", "cancellation_reason_id"]] = None
    print(f"  retail data fixes: {len(deliv):,} delivery statuses keyed to the status table, {orders.cancellation_reason_id.notna().sum():,} cancellation reasons keyed, "
          f"{clash.sum():,} orders marked cancelled but delivered set to not cancelled")
    deliv = deliv.drop(columns=["carrier", "delivery_status"])
    orders = orders.drop(columns=["cancellation_reason"])
    names = dict(zip(emp.employee_name, PEOPLE))
    emp["employee_name"] = emp.employee_name.map(names)

    # 5. budgets: the months in range, the rest of FY2027 from the year before (+3%), scaled to the stores kept
    budget["month_start"] = pd.to_datetime(budget.calendar_year.astype(str) + "-" + budget.month_num.astype(str) + "-01")
    have = set(zip(budget.sku_code, budget.month_start))
    add = []
    for _, b in budget[(budget.month_start >= pd.Timestamp("2025-07-01")) & (budget.month_start < pd.Timestamp("2026-07-01"))].iterrows():
        ms = b.month_start + pd.DateOffset(years=1)
        if (b.sku_code, ms) not in have:
            add.append({**b, "month_start": ms, "fiscal_year": "FY2027", "calendar_year": ms.year,
                        "budget_qty": round(b.budget_qty * 1.03), "budget_revenue": round(b.budget_revenue * 1.03)})
    budget = pd.concat([budget, pd.DataFrame(add)], ignore_index=True)
    budget = budget[(budget.month_start >= RETAIL_START) & (budget.month_start <= pd.Timestamp("2027-06-01"))].copy()
    budget["budget_qty"] = (budget.budget_qty * budget.sku_code.map(share)).round().astype(int)
    budget["budget_revenue"] = (budget.budget_revenue * budget.sku_code.map(share)).round().astype(int)
    budget.insert(0, "month_key", key(budget.month_start))
    budget = budget.drop(columns=["month_start"])

    # 6. tidy types and keys
    for df, cols in ((sales, ["date_key"]), (orders, ["date_key"])):
        for c in cols:
            df[c] = key(df[c])
    orders = orders.sort_values("order_id"); sales = sales.sort_values("transaction_id"); deliv = deliv.sort_values("delivery_id")
    deliv = deliv[["delivery_id", "order_id", "store_id", "sales_rep_id", "carrier_id", "delivery_status_id", "dispatch_date", "scheduled_delivery_date",
                   "actual_delivery_date", "qty_dispatched", "qty_received", "qty_damaged", "qty_rejected", "tracking_number", "is_complete",
                   "on_time_flag", "in_full_flag", "difot_flag"]]
    dd = date_dim("2024-10-01", "2027-06-30")
    T = {"dim_date": dd, "dim_store": store, "dim_product": prod, "dim_employee": emp, "dim_carrier": carrier, "dim_delivery_status": status,
         "dim_cancellation_reason": reason, "dim_sales_channel": channel, "dim_transaction_source": source, "dim_promotion": promo,
         "fact_sales_order": orders, "fact_sales": sales, "fact_delivery": deliv, "fact_budget_product_month": budget}
    keys = {"dim_date": "date_key", "dim_store": "store_id", "dim_product": "sku_code", "dim_employee": "employee_id", "dim_carrier": "carrier_id",
            "dim_delivery_status": "status_id", "dim_cancellation_reason": "reason_id", "dim_sales_channel": "channel_code",
            "dim_transaction_source": "source_id", "dim_promotion": "promo_id", "fact_sales_order": "order_id", "fact_sales": "transaction_id",
            "fact_delivery": "delivery_id"}
    refs = {("dim_store", "current_sales_rep_id"): ("dim_employee", "employee_id"), ("dim_product", "marketing_manager_id"): ("dim_employee", "employee_id"),
            ("fact_sales_order", "date_key"): ("dim_date", "date_key"), ("fact_sales_order", "store_id"): ("dim_store", "store_id"),
            ("fact_sales_order", "source_id"): ("dim_transaction_source", "source_id"), ("fact_sales_order", "sales_rep_id"): ("dim_employee", "employee_id"),
            ("fact_sales_order", "cancellation_reason_id"): ("dim_cancellation_reason", "reason_id"),
            ("fact_sales", "date_key"): ("dim_date", "date_key"), ("fact_sales", "store_id"): ("dim_store", "store_id"), ("fact_sales", "sku_code"): ("dim_product", "sku_code"),
            ("fact_sales", "source_id"): ("dim_transaction_source", "source_id"), ("fact_sales", "sales_rep_id"): ("dim_employee", "employee_id"),
            ("fact_sales", "order_id"): ("fact_sales_order", "order_id"), ("fact_sales", "channel_code"): ("dim_sales_channel", "channel_code"),
            ("fact_sales", "promo_id"): ("dim_promotion", "promo_id"),
            ("fact_delivery", "order_id"): ("fact_sales_order", "order_id"), ("fact_delivery", "store_id"): ("dim_store", "store_id"),
            ("fact_delivery", "sales_rep_id"): ("dim_employee", "employee_id"), ("fact_delivery", "carrier_id"): ("dim_carrier", "carrier_id"),
            ("fact_delivery", "delivery_status_id"): ("dim_delivery_status", "status_id"),
            ("fact_budget_product_month", "sku_code"): ("dim_product", "sku_code"), ("fact_budget_product_month", "month_key"): ("dim_date", "date_key")}
    # realistic numbers: staff numbers issued over the years; orders, sales lines and dispatches from long-running sequences
    renumber(T, keys, refs, "dim_employee", "employee_id", spread(30418, "retail-employee", (3, 60), "E{}"))
    renumber(T, keys, refs, "fact_sales_order", "order_id", shifted(478_000, ("ORD-", 7)))
    renumber(T, keys, refs, "fact_sales", "transaction_id", shifted(7_214_000, ("TXN-", 7)))
    renumber(T, keys, refs, "fact_delivery", "delivery_id", shifted(306_000, ("DEL-", 7)))
    check("retail", T, keys, refs, dated=[("fact_sales_order", "order_date"), ("fact_delivery", "actual_delivery_date"), ("fact_delivery", "dispatch_date")])
    tot = sales.groupby("order_id").total_sales.sum()
    gap = (orders.set_index("order_id").order_total - tot).abs()
    if gap.max() > 0.01 or (~orders.order_id.isin(sales.order_id)).any():
        raise SystemExit("retail: an order's total doesn't equal its sales lines, or an order has no lines; nothing written")
    if set(RETAILERS) & set(" ".join(store.store_name) .split()) - {"IGA"} or any(k in " ".join(promo.promo_name) for k in ("Coles", "Woolies", "Woolworths", "Drakes", "Night Owl")):
        raise SystemExit("retail: a real retailer name is still in the data; nothing written")
    notes = {"dim_store": "Stores (a quarter of the original 476, every retailer and state kept). Synthetic retailers.",
             "fact_sales": "Sales lines: one row per product on an order. Total_sales = qty x unit price; net_sales after discounts (0 for free goods).",
             "fact_delivery": "Deliveries: one row per dispatch (an order can ship in two). Open deliveries (not yet arrived) have no actual date. Status keyed to dim_delivery_status (the source's 'Delivered' split by its own on-time flag: late, on time, or early where it arrived before schedule).",
             "fact_sales_order": "Orders: one row per order. order_total = the sum of its sales lines. Orders the source marked cancelled but which were delivered are not cancelled; reasons keyed to dim_cancellation_reason.",
             "fact_budget_product_month": "Budget by product and month (month_key = the month's first day, yyyymmdd), scaled to the stores kept.",
             "dim_date": "Calendar, 1 Oct 2024 to 30 Jun 2027 (financial year July to June)."}
    write("retail", T, keys, refs, notes)


# ======================================================================= HEALTH

PROVIDERS = ["Dr Avery Lindqvist", "Dr Rowan Achterberg", "Tobin Marchetti", "Halcyon Reyes", "Dr Linus Okonkwo-Hale", "Ottilie Farrant",
             "Sienna Vasquez-Moor", "Mirren Caddick", "Dr Nico Thackeray", "Greta Vanstone", "Sorrel Inglewood"]


def health():
    H = ORIG / "Health"
    prov, svc = pd.read_csv(H / "dim_provider.csv"), pd.read_csv(H / "dim_service_type.csv")
    appt, claim = pd.read_csv(H / "fact_appointments.csv", parse_dates=["date", "booking_date"]), pd.read_csv(H / "fact_claims.csv", parse_dates=["submission_date", "payment_date"])
    prov["name"] = PROVIDERS[:len(prov)]
    # old pending claims would have been settled by now
    old = (claim.claim_status == "Pending") & (claim.submission_date < TODAY - timedelta(days=30))
    claim.loc[old, "claim_status"] = "Paid"
    claim.loc[old, "payment_date"] = claim.loc[old, "submission_date"] + timedelta(days=7)
    # up to 6 Oct 2026, modelled on the same weeks a year earlier
    last = appt.date.max()
    src = appt[(appt.date > last - YEAR) & (appt.date <= TODAY - YEAR)].copy()
    amap = {a: appt.appointment_id.max() + 1 + i for i, a in enumerate(sorted(src.appointment_id))}
    new_a = src.copy()
    new_a["appointment_id"] = new_a.appointment_id.map(amap)
    new_a["date"], new_a["booking_date"] = new_a.date + YEAR, new_a.booking_date + YEAR
    new_c = claim[claim.appointment_id.isin(src.appointment_id)].copy()
    new_c["claim_id"] = range(claim.claim_id.max() + 1, claim.claim_id.max() + 1 + len(new_c))
    new_c["appointment_id"] = new_c.appointment_id.map(amap)
    new_c["submission_date"], new_c["payment_date"] = new_c.submission_date + YEAR, new_c.payment_date + YEAR
    new_c = new_c[new_c.submission_date <= TODAY]
    unpaid = new_c.payment_date > TODAY
    new_c.loc[unpaid, "claim_status"], new_c.loc[unpaid, "payment_date"] = "Pending", pd.NaT
    appt, claim = pd.concat([appt, new_a], ignore_index=True), pd.concat([claim, new_c], ignore_index=True)
    dd = date_dim("2023-01-01", "2026-12-31")
    appt.insert(1, "date_key", key(appt.date))
    T = {"dim_date": dd, "dim_provider": prov, "dim_service_type": svc, "fact_appointment": appt, "fact_claim": claim}
    keys = {"dim_date": "date_key", "dim_provider": "provider_id", "dim_service_type": "service_type_id", "fact_appointment": "appointment_id", "fact_claim": "claim_id"}
    refs = {("fact_appointment", "date_key"): ("dim_date", "date_key"), ("fact_appointment", "provider_id"): ("dim_provider", "provider_id"),
            ("fact_appointment", "service_type_id"): ("dim_service_type", "service_type_id"), ("fact_claim", "appointment_id"): ("fact_appointment", "appointment_id")}
    # realistic numbers: provider numbers issued over the years; appointments and claims from the practice system's running sequences
    renumber(T, keys, refs, "dim_provider", "provider_id", spread(2140, "health-provider", (5, 40)))
    renumber(T, keys, refs, "fact_appointment", "patient_id", spread(210_400, "health-patient", (1, 9)))
    renumber(T, keys, refs, "fact_appointment", "appointment_id", shifted(418_276))
    renumber(T, keys, refs, "fact_claim", "claim_id", shifted(96_140))
    check("health", T, keys, refs, dated=[("fact_appointment", "date"), ("fact_claim", "submission_date"), ("fact_claim", "payment_date")])
    notes = {"fact_appointment": "Appointments: one row per booking, Jan 2023 to 6 Oct 2026, with what was charged and rebated.",
             "fact_claim": "Medicare/DVA claims: one per bulk-billed or DVA appointment. Pending = not paid yet.",
             "dim_provider": "Practitioners (synthetic names).", "dim_date": "Calendar, 2023 to 2026."}
    write("health", T, keys, refs, notes)


# ======================================================================= LEGAL

EARNERS = ["Imogen Cradock", "Thaddeus Wren", "Marisol Penrose", "Esme Holloway", "Corin Ashdown", "Ewan Strathmore", "Delphine Arkwright",
           "Caspian Moorcroft", "Evander Pyke", "Beatrix Lockhart", "Ellis Ravensworth", "Montague Fairlie", "Jasper Quillon", "Iona Blackwood",
           "Zinnia Hartigan", "Nikolai Ferncastle"]
GEO = ["office_name", "city", "state", "postcode", "country"]


def legal():
    L = ORIG / "Legal"
    R = lambda n, **k: pd.read_csv(L / f"{n}.csv", **k)
    client, fe, office, area, referral = R("dim_client"), R("dim_fee_earner"), R("dim_office_location"), R("dim_practice_area"), R("dim_referral_source")
    dmat = R("dim_matter", parse_dates=["open_date", "close_date"])
    fmat = R("fact_matter", parse_dates=["open_date", "close_date"])
    work = R("fact_work_performed", parse_dates=["work_date", "ledger_date"])
    bill = R("fact_billing", parse_dates=["billing_date", "ledger_date"])
    disb = R("fact_disbursements", parse_dates=["disbursement_date", "ledger_date"])
    budget = R("fact_fee_earner_budget_monthly")
    dd = R("dim_date", parse_dates=["date"])
    fe["name"] = EARNERS[:len(fe)]
    fe = fe.drop(columns=[c for c in GEO + ["latitude", "longitude"] if c in fe.columns])
    # collection rate per matter (kept when totals are recalculated)
    rate = (fmat.amount_collected / (fmat.legal_fees_billed + fmat.disbursements_paid).replace(0, pd.NA)).fillna(0.5)
    rate.index = fmat.matter_id
    # nothing after the 'as at' time (budgets are plans and stay)
    work = work[work.work_date <= TODAY]
    bill = bill[(bill.billing_date <= TODAY) & bill.timecard_id.isin(work.timecard_id)]
    disb = disb[disb.disbursement_date <= TODAY]
    # new matters Jul to 6 Oct 2026, modelled on those opened a year earlier
    src = dmat[(dmat.open_date > dmat.open_date.max() - YEAR + timedelta(days=1)) & (dmat.open_date <= TODAY - YEAR)]
    src = src[src.open_date > pd.Timestamp("2025-06-28")]
    mmap = {m: dmat.matter_id.max() + 1 + i for i, m in enumerate(sorted(src.matter_id))}
    nd = src.copy()
    nd["matter_id"] = nd.matter_id.map(mmap)
    nd["matter_reference"] = nd.matter_id.map(lambda m: f"MAT-{m:05d}")
    nd["matter_name"] = nd.matter_id.map(lambda m: f"Matter {m:05d}")
    nd["open_date"], nd["close_date"], nd["status"] = nd.open_date + YEAR, pd.NaT, "Open"
    nf = fmat[fmat.matter_id.isin(src.matter_id)].copy()
    nf["matter_id"] = nf.matter_id.map(mmap)
    nf["open_date"], nf["close_date"], nf["status"], nf["settlement_value"] = nf.open_date + YEAR, pd.NaT, "Open", None
    tmap, wsrc = {}, R("fact_work_performed", parse_dates=["work_date", "ledger_date"])
    nw = wsrc[wsrc.matter_id.isin(src.matter_id)].copy()
    nw["work_date"], nw["ledger_date"] = nw.work_date + YEAR, nw.ledger_date + YEAR
    nw = nw[nw.work_date <= TODAY]
    for i, t in enumerate(sorted(nw.timecard_id)):
        tmap[t] = work.timecard_id.max() + 1 + i
    nw["timecard_id"], nw["matter_id"] = nw.timecard_id.map(tmap), nw.matter_id.map(mmap)
    bsrc = R("fact_billing", parse_dates=["billing_date", "ledger_date"])
    nb = bsrc[bsrc.timecard_id.isin(tmap)].copy()
    nb["billing_date"], nb["ledger_date"] = nb.billing_date + YEAR, nb.ledger_date + YEAR
    nb = nb[nb.billing_date <= TODAY]
    nb["billing_id"] = range(bill.billing_id.max() + 1, bill.billing_id.max() + 1 + len(nb))
    nb["timecard_id"], nb["matter_id"] = nb.timecard_id.map(tmap), nb.matter_id.map(mmap)
    nb["invoice_number"] = [f"INV-{m:05d}-{d:%Y%m}" for m, d in zip(nb.matter_id, nb.billing_date)]
    dsrc = R("fact_disbursements", parse_dates=["disbursement_date", "ledger_date"])
    ndb = dsrc[dsrc.matter_id.isin(src.matter_id)].copy()
    ndb["disbursement_date"], ndb["ledger_date"] = ndb.disbursement_date + YEAR, ndb.ledger_date + YEAR
    ndb = ndb[ndb.disbursement_date <= TODAY]
    ndb["disbursement_id"] = range(disb.disbursement_id.max() + 1, disb.disbursement_id.max() + 1 + len(ndb))
    ndb["matter_id"] = ndb.matter_id.map(mmap)
    ndb["invoice_number"] = [f"DISB-{m:05d}-{i:02d}" for i, m in enumerate(ndb.matter_id, 1)]
    for m_old, m_new in mmap.items():
        rate[m_new] = min(rate.get(m_old, 0.35), 0.35)
    dmat, fmat = pd.concat([dmat, nd], ignore_index=True), pd.concat([fmat, nf], ignore_index=True)
    work, bill, disb = pd.concat([work, nw], ignore_index=True), pd.concat([bill, nb], ignore_index=True), pd.concat([disb, ndb], ignore_index=True)
    # every matter's totals from its own detail
    fees = bill.groupby("matter_id").billed_amount.sum()
    wo = bill.groupby("matter_id").writeoff_amount.sum()
    dp = disb.groupby("matter_id").disbursement_amount.sum()
    fmat["legal_fees_billed"] = fmat.matter_id.map(fees).fillna(0).round(2)
    fmat["write_off_amount"] = fmat.matter_id.map(wo).fillna(0).round(2)
    fmat["disbursements_paid"] = fmat.matter_id.map(dp).fillna(0).round(2)
    fmat["amount_collected"] = ((fmat.legal_fees_billed + fmat.disbursements_paid) * fmat.matter_id.map(rate).fillna(0.5)).round(2)
    # one place for each description (star schema): drop the repeated office and practice-area names
    dmat = dmat.drop(columns=GEO + ["practice_area_name"])
    fmat, work, bill, disb, budget = (df.drop(columns=[c for c in GEO if c in df.columns]) for df in (fmat, work, bill, disb, budget))
    office = office.copy()
    cal = date_dim("2023-01-01", "2027-06-30")
    cal["is_court_vacation"] = cal.date.map(dict(zip(dd.date, dd.is_court_vacation))).fillna(False).astype(bool).astype(int)
    for df, c in ((work, "work_date"), (bill, "billing_date"), (disb, "disbursement_date")):
        df.insert(1, "date_key", key(df[c]))
    budget.insert(0, "month_key", (budget.year * 10000 + budget.month * 100 + 1).astype(int))
    T = {"dim_date": cal, "dim_client": client, "dim_fee_earner": fe, "dim_office": office, "dim_practice_area": area, "dim_referral_source": referral,
         "dim_matter": dmat, "fact_matter": fmat, "fact_work": work, "fact_billing": bill, "fact_disbursement": disb, "fact_fee_earner_budget_month": budget}
    keys = {"dim_date": "date_key", "dim_client": "client_id", "dim_fee_earner": "fee_earner_id", "dim_office": "office_id", "dim_practice_area": "practice_area_id",
            "dim_referral_source": "referral_source_id", "dim_matter": "matter_id", "fact_matter": "matter_id", "fact_work": "timecard_id",
            "fact_billing": "billing_id", "fact_disbursement": "disbursement_id", "fact_fee_earner_budget_month": "budget_id"}
    refs = {("dim_fee_earner", "primary_practice_area_id"): ("dim_practice_area", "practice_area_id"), ("dim_fee_earner", "office_id"): ("dim_office", "office_id"),
            ("dim_matter", "client_id"): ("dim_client", "client_id"), ("dim_matter", "practice_area_id"): ("dim_practice_area", "practice_area_id"),
            ("dim_matter", "fee_earner_id"): ("dim_fee_earner", "fee_earner_id"), ("dim_matter", "referral_source_id"): ("dim_referral_source", "referral_source_id"),
            ("dim_matter", "office_id"): ("dim_office", "office_id"), ("fact_matter", "matter_id"): ("dim_matter", "matter_id"),
            ("fact_work", "matter_id"): ("dim_matter", "matter_id"), ("fact_work", "fee_earner_id"): ("dim_fee_earner", "fee_earner_id"),
            ("fact_work", "date_key"): ("dim_date", "date_key"), ("fact_billing", "timecard_id"): ("fact_work", "timecard_id"),
            ("fact_billing", "matter_id"): ("dim_matter", "matter_id"), ("fact_billing", "date_key"): ("dim_date", "date_key"),
            ("fact_disbursement", "matter_id"): ("dim_matter", "matter_id"), ("fact_disbursement", "date_key"): ("dim_date", "date_key"),
            ("fact_fee_earner_budget_month", "fee_earner_id"): ("dim_fee_earner", "fee_earner_id"), ("fact_fee_earner_budget_month", "month_key"): ("dim_date", "date_key")}
    # realistic numbers: client, matter and staff numbers issued over the years; timecards, bills and disbursements from running
    # sequences; and every reference built from them (matter reference and name, client name, invoice numbers) rebuilt to match
    renumber(T, keys, refs, "dim_client", "client_id", spread(100_380, "legal-client", (2, 60)))
    renumber(T, keys, refs, "dim_matter", "matter_id", spread(18_240, "legal-matter", (1, 4)))
    renumber(T, keys, refs, "dim_fee_earner", "fee_earner_id", spread(112, "legal-fee-earner", (3, 21)))
    renumber(T, keys, refs, "fact_work", "timecard_id", shifted(2_604_118))
    renumber(T, keys, refs, "fact_billing", "billing_id", shifted(803_455))
    renumber(T, keys, refs, "fact_disbursement", "disbursement_id", shifted(61_207))
    renumber(T, keys, refs, "fact_fee_earner_budget_month", "budget_id", shifted(7_310))
    client["client_name"] = client.client_id.map(lambda c: f"Client {c}")
    dmat["matter_reference"] = dmat.matter_id.map(lambda m: f"MAT-{m}")
    dmat["matter_name"] = dmat.matter_id.map(lambda m: f"Matter {m}")
    bill["invoice_number"] = [f"INV-{m}-{d:%Y%m}" for m, d in zip(bill.matter_id, pd.to_datetime(bill.billing_date))]
    disb = disb.sort_values(["matter_id", "disbursement_date", "disbursement_id"])
    disb["invoice_number"] = [f"DISB-{m}-{n:02d}" for m, n in zip(disb.matter_id, disb.groupby("matter_id").cumcount() + 1)]
    disb = T["fact_disbursement"] = disb.sort_values("disbursement_id")
    check("legal", T, keys, refs, dated=[("fact_work", "work_date"), ("fact_billing", "billing_date"), ("fact_disbursement", "disbursement_date")])
    if (bill.groupby("timecard_id").size() > 1).any():
        raise SystemExit("legal: a timecard is billed twice; nothing written")
    notes = {"fact_work": "Time recorded: one row per timecard, Jan 2023 to 6 Oct 2026. Not yet billed = unbilled work.",
             "fact_billing": "Time billed: one row per timecard billed (or written off).",
             "fact_matter": "Each matter's totals, recalculated from its work, invoices and disbursements.",
             "dim_fee_earner": "Lawyers and staff (synthetic names).", "dim_date": "Calendar 2023 to Jun 2027, with court vacations."}
    write("legal", T, keys, refs, notes)


def main():
    archive_originals()
    pick = sys.argv[1:] or ["retail", "health", "legal"]
    for name in pick:
        {"retail": retail, "health": health, "legal": legal}[name]()


if __name__ == "__main__":
    main()
