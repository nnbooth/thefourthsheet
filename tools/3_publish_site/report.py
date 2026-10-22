#!/usr/bin/env python3
"""report.py — build a report from the data for a period, as Excel, PDF and PowerPoint (from scratch, no templates).

    python3 tools/3_publish_site/report.py job-margins --period 2026-06
    python3 tools/3_publish_site/report.py --list

See tools/3_publish_site/fourthsheet/cli.py for every option.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import sys
from pathlib import Path
import winutf8; winutf8.ensure()   # Windows: run in UTF-8 mode (the tools write characters like ¢ and ▲)


from fourthsheet.cli import main  # noqa: E402

main(sys.argv[1:])
