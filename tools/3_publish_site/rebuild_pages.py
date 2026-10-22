#!/usr/bin/env python3
"""rebuild_pages.py — regenerate only the report pages, the SME/NFP report cards and "The numbers, explained" from
their templates (after editing sme.html, the page shell or the generators). Much quicker than sample_data.py, which
also rebuilds every data file and download.

    python3 tools/3_publish_site/rebuild_pages.py
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import sys
from pathlib import Path

import winutf8; winutf8.ensure()   # noqa: E402,E702  Windows: run in UTF-8 mode

import build_reports as br                                   # noqa: E402
from fourthsheet.build import load_data, periods_for, run_report, default_period, write_site   # noqa: E402
from fourthsheet.catalogue import REPORTS                     # noqa: E402


def main(data_too=True):
    D = load_data()
    runs = {slug: [run_report(slug, p, D) for p in periods_for(slug, D)] for slug in REPORTS}
    defaults = [next(r for r in rs if r["period"] == r["default_period"]) for rs in runs.values()]
    if data_too:
        write_site(runs)
    br.write_pages(defaults)
    br.write_cards(defaults)
    br.write_explainer()
    print(f"rebuilt {len(defaults)} report pages, the report cards and numbers-explained.html" + (" (and their data files)" if data_too else ""))


if __name__ == "__main__":
    main()
