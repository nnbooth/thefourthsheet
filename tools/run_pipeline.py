#!/usr/bin/env python3
"""
run_pipeline.py - run the stages in order.   python3 tools/run_pipeline.py [--azure] [--skip-site]

  stage 1  1_build_data/sample_data.py       make the raw data (CSVs in OneDrive)
  stage 2  2_load_azure/database/load.py     load the CSVs into Azure SQL          (only with --azure: needs your sign-in)
  stage 3  3_publish_site/build_site.py      build the website files from the data  (skip with --skip-site)
"""
import argparse
import subprocess
import sys
from pathlib import Path

T = Path(__file__).resolve().parent
STEPS = [("1_build_data/sample_data.py", "Stage 1: build the raw data"),
         ("2_load_azure/database/load.py", "Stage 2: load into Azure"),
         ("3_publish_site/build_site.py", "Stage 3: build the website files")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--azure", action="store_true", help="also run stage 2 (loads the Azure database)")
    ap.add_argument("--skip-site", action="store_true", help="stop after stage 1 (and 2)")
    a = ap.parse_args()
    for i, (script, label) in enumerate(STEPS):
        if (i == 1 and not a.azure) or (i == 2 and a.skip_site):
            print(f"-- skipped: {label}")
            continue
        print(f"== {label}  ({script})")
        r = subprocess.run([sys.executable, str(T / script)])
        if r.returncode:
            sys.exit(f"{label} failed (exit {r.returncode}); later stages not run.")
    print("== all requested stages finished")


if __name__ == "__main__":
    main()
