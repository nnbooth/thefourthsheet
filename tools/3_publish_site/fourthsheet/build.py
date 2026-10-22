"""
build.py — run a report for a period, and write it out.

    data = load_data()                                   # from the data source (CSV folder today)
    r = run_report("job-margins", "2026-06", data)       # the report, worked out for June 2026
    write_files(r, ["xlsx", "pdf", "pptx"])              # Excel, PDF and PowerPoint, built from scratch

Every file is generated in code from the report (no templates): Excel cell by cell with formulas
(openpyxl), the PDF as an HTML page printed by headless Chrome, PowerPoint slide by slide with native charts
(python-pptx). The website gets the same report as data, for every period, so its Period dropdown works.
"""

import json
from pathlib import Path

import data_status as ds
import readable_json

from .catalogue import NEEDS_CASH, REPORTS, cash_months
from .period import CURRENT, Period
from .source import load

REPO = Path(__file__).resolve().parents[3]
EXPORTS = REPO / "media" / "exports" / "reports"
FIRST_PERIOD_GAP = 12        # a period needs a year of history before it (year-on-year comparisons)


def load_data(src=None):
    src, D = load(src)
    from .catalogue import engagements, jobs
    D["_src"] = src
    D["_jobs"] = jobs(src)
    D["_engagements"] = engagements(src)
    D["_targets"] = {t["target"]: t["value"] for t in src.table("nfp", "target")}
    D["_current_grants"] = {i["grant_id"] for i in src.table("nfp", "fact_grant_instalment")}
    D["_grant_first"] = min(r["month_key"] for r in src.table("nfp", "fact_grant_spend_month"))
    return D


def periods_for(slug, D):
    """The periods a report can be run for, newest first."""
    months = D["trades"].months
    if slug in NEEDS_CASH:
        ok = cash_months(D)
    else:
        ok = months[FIRST_PERIOD_GAP:]
    if slug == "cost-to-win":       # needs the month's count of new customers
        ok = [m for m in ok if m in D["trades"].drivers["New customers (first job ever)"]]
    return [m for m in reversed(ok) if m <= CURRENT]


def default_period(slug, D):
    """The most recent locked month: what a report shows unless asked otherwise (a month that's over but not locked yet
    is still offered, never the default). If no month is locked yet, the latest month that's over."""
    ps = periods_for(slug, D)
    return (next((m for m in ps if ds.month_status(m)[0] == "Locked"), None)
            or next(m for m in ps if ds.month_status(m)[0] != "Incomplete"))


def run_report(slug, period, D):
    if slug not in REPORTS:
        raise SystemExit(f"No report called {slug!r}. Reports: {', '.join(REPORTS)}")
    if period not in periods_for(slug, D):
        raise SystemExit(f"{slug} can't be run for {period}. Periods with enough data: {', '.join(sorted(periods_for(slug, D)))}")
    P = Period(period, D["trades"].months)
    r = REPORTS[slug](D, P)
    r["periods"] = [Period(m, D["trades"].months).option() for m in periods_for(slug, D)]
    r["default_period"] = default_period(slug, D)
    return r


def out_dir(r):
    return EXPORTS / r["period"]


def write_files(r, formats, out=None):
    """Excel / PDF / PowerPoint for one report and period. Returns the paths written."""
    import build_reports as br
    if r["slug"] in br.TEMPLATED:
        print(f"  {r['slug']}: no files to build; its downloads are made from assets/exports/templates/ when someone clicks Export")
        return []
    out = Path(out) if out else out_dir(r)
    out.mkdir(parents=True, exist_ok=True)
    done = []
    for part in br.file_parts(r):        # one set of files per business
        f = br.file_name(part)
        if "xlsx" in formats:
            review = br.write_xlsx(part, out)
            done.append((out / f"{f}.xlsx", " | ".join(review)))
        if "pptx" in formats:
            br.write_pptx(part, out)
            done.append((out / f"{f}.pptx", ""))
        if "pdf" in formats:
            br.write_pdfs([part], out)
            done.append((out / f"{f}.pdf", ""))
    return done


def site_payload(r):
    import build_reports as br
    return br.page_payload([r])[r["slug"]]


def write_site(all_runs, merge=False, source=None):
    """data/reports/<slug>.json (every period of one report, loaded by its page and its featured chart) and
    data/reports/cards.json (what the report cards draw, for every report and period).
    merge: only the reports in all_runs change; the others in cards.json are kept as they are.
    source: the data source the runs read (named in each file's "source")."""
    import build_reports as br
    import exportkit as ek
    d = REPO / "data" / "reports"
    d.mkdir(parents=True, exist_ok=True)
    cards_file = d / "cards.json"
    cards = json.loads(cards_file.read_text(encoding="utf-8"))["reports"] if merge and cards_file.exists() else {}
    for slug, runs in all_runs.items():
        by_period = {}
        for r in runs:
            parts = br.file_parts(r)
            per = ek.period_name(r["period"], r["period_status"] == "Incomplete")
            meta = lambda p_: ek.export_meta({k: f"media/exports/reports/{r['period']}/{br.file_name(p_)}.{k}" for k in ("xlsx", "pdf", "pptx")},
                                             p_["business"], br.SHORT.get(r["slug"], r["slug"]), per)
            if slug not in br.TEMPLATED:           # templated reports have no files to describe (br.page_payload names them)
                r["exports_meta"] = meta(parts[0])
                r["_parts"] = [{"file": br.file_name(p_), "label": p_["blocks"][0].get("label") if len(parts) > 1 else None, "meta": meta(p_)} for p_ in parts]
            by_period[r["period"]] = site_payload(r)
        default = runs[0]["default_period"]
        write_json(d / f"{slug}.json", {"note": f"GENERATED by tools/3_publish_site/fourthsheet from {source_words(source)}. Invented sample data. Don't edit by hand.",
                                        "default": default, "by_period": by_period})
        cards[slug] = {"default": default, "by_period": {p: card_payload(x) for p, x in by_period.items()}}
    return write_json(cards_file, {"note": "GENERATED by tools/3_publish_site/fourthsheet: what each report card draws, every period. Don't edit by hand.",
                                   "reports": {s: cards[s] for s in sorted(cards)}})


def card_payload(p):
    """Only what a report's card draws (script.js drawCard): its answer, its periods, its own card if it has one, else the
    first headline number and the last 12 months of its month chart (first line and measure) or the values of its bar
    chart (first view). Filters at All."""
    out = {key: p[key] for key in ("slug", "answer", "period", "periods", "card") if key in p}
    if "card" in p:
        out["blocks"] = [{"sections": []}]       # drawCard still looks for sections before it uses the card
        return out
    secs = [x["by"].get("All") or next(iter(x["by"].values())) if x["type"] == "vary" else x for x in p["blocks"][0]["sections"]]
    k = next((x for x in secs if x["type"] == "kpis"), None)
    first = next((x for x in secs if x["type"] in ("bars", "series")), None)
    keep = []
    if k:
        keep.append({"type": "kpis", "items": [{f: k["items"][0][f] for f in ("value", "label", "tone", "sub") if f in k["items"][0]}]})
    if first and first["type"] == "series":
        dims = first.get("dims") or {"line": ["All"], "measure": [[next(iter(first["views"])).split("|")[1], ""]]}
        key = f"{dims['line'][0]}|{dims['measure'][0][0]}"
        v = first["views"][key]
        keep.append({"type": "series", "labels": first["labels"][-12:], "status": first["status"][-12:],
                     "dims": {"line": dims["line"][:1], "measure": dims["measure"][:1]},
                     "views": {key: {"values": v["values"][-12:], "format": v["format"]}}})
    elif first:
        ch = first["chart"]
        v0 = ch["views"][0] if ch.get("views") else ch
        v = {f: v0[f] for f in ("values", "format", "target") if v0.get(f) is not None}
        keep.append({"type": "bars", "chart": {"labels": ch["labels"], **({"plain": True} if ch.get("plain") else {}), "views": [v]}})
    out["blocks"] = [{"sections": keep}]
    return out


def write_json(f, o):
    """A readable JSON data file, rewritten only if it changed. Returns its size."""
    text = readable_json.dumps(o) + "\n"
    if not f.exists() or f.read_text(encoding="utf-8") != text:
        f.write_text(text, encoding="utf-8")
    return len(text.encode())


def source_words(src):
    """What a site file says it was built from. No machine paths: the repo is public."""
    from .source import SqlSource
    return "the database (Azure SQL, thefourthsheet)" if isinstance(src, SqlSource) else "the CSV files" if src else "the data"


LAST_DATA = None


def build_all(formats=("xlsx", "pdf", "pptx"), quiet=False):
    """Every report for every period it can run for: the website's data and pages, and every download.
    Returns the reports at their default periods (for the cards and the Power BI prompts)."""
    import build_reports as br
    global LAST_DATA
    D = LAST_DATA = load_data()          # kept, so later steps reuse it rather than re-read files OneDrive is still syncing
    runs = {slug: [run_report(slug, p, D) for p in periods_for(slug, D)] for slug in REPORTS}
    defaults = [next(r for r in rs if r["period"] == r["default_period"]) for rs in runs.values()]
    br.write_pages(defaults)
    br.write_cards(defaults)
    br.write_explainer()
    flat = [r for rs in runs.values() for r in rs]
    files = [part for r in flat if r["slug"] not in br.TEMPLATED for part in br.file_parts(r)]   # one set of downloads per business (templated reports: none)
    for r in files:
        if "xlsx" in formats:
            review = br.write_xlsx(r, out_dir(r))
            if not quiet and r["period"] == r["default_period"]:
                print(f"  {br.file_name(r)}.xlsx: " + " | ".join(review))
        if "pptx" in formats:
            br.write_pptx(r, out_dir(r))
    if "pdf" in formats:
        br.write_pdfs(files)
    if set(formats) == {"xlsx", "pdf", "pptx"}:      # a full build: any download no report produces any more is removed
        made = {(out_dir(r) / f"{br.file_name(r)}.{fmt}").resolve() for r in files for fmt in formats}
        stale = [p for p in EXPORTS.rglob("*") if p.is_file() and p.suffix in (".xlsx", ".pdf", ".pptx") and p.resolve() not in made]
        for p in stale:
            p.unlink()
        for d in sorted(EXPORTS.glob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        if stale:
            print(f"  removed {len(stale)} download(s) no report produces any more")
    size = write_site(runs, source=D["_src"])          # after the files, so the Export menu can say how many pages and slides they have
    from .dashboard_months import build as dashboard_months      # the home dashboard for every month (checks September against the model)
    n_months = dashboard_months(D)
    print(f"  {len(runs)} reports × their periods = {len(flat)} runs, each as Excel, PDF and PowerPoint (media/exports/reports/<period>/); "
          f"data/reports/<report>.json + cards.json ({size // 1024} KB); home dashboard: {n_months} months")
    if set(formats) == {"xlsx", "pdf", "pptx"}:      # every download must say what the site says: stop the build if one doesn't
        import subprocess
        import sys as _sys
        root = EXPORTS.parents[2]
        chk = subprocess.run([_sys.executable, "-I", str(root / "tools/3_publish_site/tests/exports_match.py"), str(root)], capture_output=True, text=True)
        print("  " + chk.stdout.strip().replace("\n", "\n  "))
        if chk.returncode:
            raise SystemExit("A download doesn't match the site (above). Nothing should be committed until it does.")
    return defaults
