#!/usr/bin/env python3
"""
org_separation.py — prove the sample organisations are never mixed. Trades, services and the not-for-profit are
separate, unrelated businesses: no number, total, chart, ranking or working may combine two of them.

    python3 tools/3_publish_site/tests/org_separation.py          (Windows: py tools\\3_publish_site\\tests\\org_separation.py)

Checks, from the data up:
  1. Data: every row in every organisation's folder carries that organisation's org_id; every fact row's account,
     job, engagement or grant belongs to the same organisation; ids and line names never repeat across organisations
     (so a database join or a Power BI slicer can't merge them).
  2. Reports, every period: each block of a report is one organisation, and its numbers tie to that organisation's
     own ledger (growth year to date is checked against each business alone, and must not equal the combined figure).
     Every working in a multi-business report names its business.
  3. Site: the growth card shows each business as its own group, and each group's headline ties to that business.
  4. Power BI prompts: one business per page, a locked org filter, and measures that go blank unless one org is in view.
Prints PROBLEMS: [] when everything passes (and exits 1 otherwise).
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import winutf8; winutf8.ensure()   # noqa: E402,E702  Windows: run in UTF-8 mode

FOLDERS = {"trades": "SME trades", "services": "SME services", "nfp": "Not-for-profit"}
NAMES = {"trades": "Trades", "services": "Services"}


def main():
    from fourthsheet.build import load_data, periods_for, run_report
    from fourthsheet.source import data_root
    probs = []
    root = Path(data_root()) / "Month-end dashboard"

    # ---------------------------------------------------------------- 1. data
    tables = defaultdict(dict)                     # {table: {org: rows}}
    for org, folder in FOLDERS.items():
        for f in sorted((root / folder).glob("*.csv")):
            with open(f, newline="", encoding="utf-8") as fh:
                tables[f.stem][org] = list(csv.DictReader(fh))
    for t, by in tables.items():
        for org, rows in by.items():
            col = "org_id" if rows and "org_id" in rows[0] else "org" if rows and "org" in rows[0] else None
            if col:
                wrong = [r for r in rows if r[col] != org]
                if wrong:
                    probs.append((t, org, f"{len(wrong)} rows belong to another organisation", wrong[0][col]))
    owner = {}
    for org, rows in tables["dim_account"].items():
        for r in rows:
            if r["account_id"] in owner:
                probs.append(("dim_account", "account_id used by two organisations", r["account_id"]))
            owner[r["account_id"]] = org
    for t, by in tables.items():
        for org, rows in by.items():
            if rows and "account_id" in rows[0] and t != "dim_account":
                bad = [r for r in rows if r["account_id"] and owner.get(r["account_id"]) != org]
                if bad:
                    probs.append((t, org, f"{len(bad)} rows post to another organisation's account", bad[0]["account_id"]))
    ids = {}
    for key, table in (("job_id", "dim_job"), ("engagement_id", "dim_engagement"), ("grant_id", "dim_grant")):
        for org, rows in tables.get(table, {}).items():
            for r in rows:
                if (key, r[key]) in ids and ids[(key, r[key])] != org:
                    probs.append((table, f"{key} used by two organisations", r[key]))
                ids[(key, r[key])] = org
    for t, by in tables.items():
        for org, rows in by.items():
            for key in ("job_id", "engagement_id", "grant_id"):
                if rows and key in rows[0]:
                    bad = [r for r in rows if r[key] and ids.get((key, r[key]), org) != org]
                    if bad:
                        probs.append((t, org, f"{len(bad)} rows point at another organisation's {key}", bad[0][key]))
    lines = {org: {r["line"] for r in rows} for org, rows in tables["fact_line_month"].items()}
    for a in lines:
        for b in lines:
            if a < b and lines[a] & lines[b]:
                probs.append(("fact_line_month", f"line names shared by {a} and {b}", sorted(lines[a] & lines[b])))

    # ---------------------------------------------------------------- 2. reports
    D = load_data()
    nreports = 0
    for slug in sorted(__import__("fourthsheet.catalogue", fromlist=["REPORTS"]).REPORTS):
        for per in periods_for(slug, D):
            r = run_report(slug, per, D)
            nreports += 1
            orgs = [b.get("org") or r["org"] for b in r["blocks"]]
            if any(o not in FOLDERS for o in orgs):
                probs.append((slug, per, "a block with no single organisation", orgs))
            if len(r["blocks"]) > 1:
                if len(set(orgs)) != len(orgs):
                    probs.append((slug, per, "two blocks for the same organisation", orgs))
                for b, org in zip(r["blocks"], orgs):
                    for sp in supports_in(b):
                        if NAMES.get(org) and not sp["title"].startswith(NAMES[org]):
                            probs.append((slug, per, org, "a working that doesn't name its business", sp["title"]))
            if slug == "growth":
                from fourthsheet.catalogue import SERVICE_LINES, TRADE_LINES, line_table
                from fourthsheet.period import Period
                P = Period(per, D["trades"].months)
                own = {o: line_table(D, P, o, ls)[-1][1] for o, ls in (("trades", TRADE_LINES), ("services", SERVICE_LINES))}
                for b, org in zip(r["blocks"], orgs):
                    ytd = [sp for sp in supports_in(b) if sp["title"].endswith(("all lines: year to date", "all lines: year to date against the same period last year"))]
                    if not ytd:
                        probs.append((slug, per, org, "no year-to-date working for the whole business"))
                        continue
                    got = ytd[0]["xl"]["rows"][0]["values"][0]
                    if round(got) != round(own[org]) or round(got) == round(sum(own.values())):
                        probs.append((slug, per, org, "year-to-date revenue doesn't tie to this business alone", got, own))
                for g in (r.get("card") or {}).get("groups", []):
                    org = {"Trades": "trades", "Services": "services"}.get(g["name"])
                    if not org:
                        probs.append((slug, per, "card group that isn't one business", g["name"]))
                    elif money_in(g["sub"]) and round(money_in(g["sub"])[0]) != round(own[org]):
                        probs.append((slug, per, "card group doesn't tie to its business", g["name"], g["sub"], own[org]))

    # ---------------------------------------------------------------- 4. Power BI prompts
    from fourthsheet.source import data_root as _dr
    pbi = Path(_dr()).parent / "Data documentation" / "Power BI"
    for f in sorted(pbi.glob("* - Power BI prompt.md")):
        t = f.read_text(encoding="utf-8")
        for need in ("One business per page", "dim_org[org_id]", "HASONEVALUE(dim_org[org_id])", "Page-level filter"):
            if need not in t:
                probs.append((f.name, "missing", need))
        for m in re.finditer(r"^([^=\n`-][^=\n]*?)\s*=\s*(SUM|SUMX|LASTNONBLANKVALUE|MEDIANX|AVERAGE|COUNTROWS|LOOKUPVALUE)\(", t, re.M):
            if m.group(1).strip() != "Org check":
                probs.append((f.name, "a measure without the one-organisation guard", m.group(1).strip()))

    print(f"{sum(len(v) for by in tables.values() for v in by.values())} data rows in {len(tables)} tables, {nreports} report runs and "
          f"{len(list(pbi.glob('* - Power BI prompt.md')))} Power BI prompts checked. PROBLEMS: {probs}")
    if probs:
        sys.exit(1)


def supports_in(b):
    """Every working in a block (headline numbers, bars, series points, insights), however deeply nested."""
    out = []
    def walk(x):
        if isinstance(x, dict):
            if "xl" in x and "title" in x and "formula" in x:
                out.append(x)
                return
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(b["sections"])
    return out


def money_in(text):
    return [float(m.replace(",", "")) for m in re.findall(r"\$([\d,]+)", text or "")]


if __name__ == "__main__":
    main()
