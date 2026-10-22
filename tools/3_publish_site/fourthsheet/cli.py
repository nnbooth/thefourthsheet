"""
Run a report for a period, from the data, and build its Excel, PDF and PowerPoint from scratch.

    python3 tools/3_publish_site/report.py job-margins --period 2026-06
    python3 tools/3_publish_site/report.py board --period 2026-08 --format pdf --out ~/Desktop
    python3 tools/3_publish_site/report.py --list                      every report and the periods it can run for
    python3 tools/3_publish_site/report.py --all                       everything, for the website (what sample_data.py runs)
    python3 tools/3_publish_site/report.py board --site --source db    one report's website data, every period, from the database

Data comes from the CSV folder in OneDrive (or FOURTH_SHEET_DATA); the database will slot in behind the same
interface (fourthsheet/source.py).
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import argparse
import sys

from .build import build_all, default_period, load_data, periods_for, run_report, write_files, write_site
from .catalogue import REPORTS


def compare_sources():
    """The database must give exactly the same reports as the CSVs it was loaded from."""
    import json
    from .source import CsvSource, SqlSource
    a, b = load_data(CsvSource()), load_data(SqlSource())
    bad = n = 0
    for slug in REPORTS:
        for p in periods_for(slug, a):
            x = json.dumps(run_report(slug, p, a), sort_keys=True, default=str)
            y = json.dumps(run_report(slug, p, b), sort_keys=True, default=str)
            n += 1
            if x != y:
                bad += 1
                print(f"  DIFFERENT: {slug} {p}")
    print(f"{n} report runs compared, CSV against the database: {bad} different")
    if bad:
        raise SystemExit(1)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="report", description="Build a report from the data, for a period, as Excel, PDF and PowerPoint.")
    ap.add_argument("report", nargs="?", choices=list(REPORTS), help="which report")
    ap.add_argument("--period", help="YYYY-MM (default: the latest month that's over)")
    ap.add_argument("--format", default="xlsx,pdf,pptx", help="any of xlsx,pdf,pptx (default: all three)")
    ap.add_argument("--out", help="folder for the files (default: media/exports/reports/<period>/)")
    ap.add_argument("--list", action="store_true", help="list the reports and their periods")
    ap.add_argument("--all", action="store_true", help="build every report for every period (the website)")
    ap.add_argument("--source", choices=["csv", "db"], help="read the CSV folder (default) or the cloud database")
    ap.add_argument("--site", action="store_true", help="write one report's website data (every period) and leave the rest of the site alone")
    ap.add_argument("--compare-sources", action="store_true", help="run every report from the CSVs and from the database and check they match")
    a = ap.parse_args(argv)
    if a.source:
        import os
        os.environ["FOURTH_SHEET_SOURCE"] = a.source
    if a.compare_sources:
        compare_sources()
        return
    if a.all:
        build_all(tuple(a.format.split(",")))
        return
    D = load_data()
    if a.list or not a.report:
        for slug in REPORTS:
            ps = periods_for(slug, D)
            print(f"{slug:14} {ps[-1]} to {ps[0]}  (default {default_period(slug, D)})")
        if not a.report:
            return
    if a.site:
        runs = [run_report(a.report, p, D) for p in periods_for(a.report, D)]
        write_site({a.report: runs}, merge=True, source=D["_src"])
        print(f"{a.report}: website data for {len(runs)} periods ({', '.join(r['period'] for r in runs)}), from {D['_src'].name}")
        return
    period = a.period or default_period(a.report, D)
    r = run_report(a.report, period, D)
    print(f"{r['question']} · {r['business']} · {r['period_label']} ({r['period_status'].lower()})")
    for path, note in write_files(r, a.format.split(","), a.out):
        print(f"  {path}" + (f"  [{note}]" if note else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
