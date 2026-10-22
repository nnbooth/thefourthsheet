#!/usr/bin/env python3
"""
build_site.py - STAGE 3 of 3: everything that goes onto the live website, built from the stage-1 data.

Run after 1_build_data/sample_data.py (and after 2_load_azure/database/load.py if you want the reports to read Azure).
In order:
  1. publish_dashboard  the home-page dashboard: data/dashboard.json + sample-statements Excel/PDF/PowerPoint
  2. deliveries_site    the deliveries map: data/deliveries.json + Excel/PDF/PowerPoint
  3. build_all          the 14 report pages for every period: web data, Excel, PDF, PowerPoint
  4. powerbi_notes      the Power BI build notes (written to OneDrive, Data documentation/Power BI)
  5. sync_media         media/ (Excel, PDF, images) kept identical with OneDrive
The CI workflow then checks the downloads (tests/exports_match.py) and publishes (publish_site.py).
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import winutf8; winutf8.ensure()   # Windows: run in UTF-8 mode


def main():
    import deliveries_site
    import powerbi_notes
    import publish_dashboard
    import sync_media
    from fourthsheet.build import build_all
    publish_dashboard.publish()
    deliveries_site.publish()
    built = build_all()
    powerbi_notes.write(built)
    sync_media.sync()


if __name__ == "__main__":
    main()
