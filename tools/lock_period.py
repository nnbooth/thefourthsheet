#!/usr/bin/env python3
"""
lock_period.py — lock (close) a month, or reopen one, in the period-lock register (tools/shared/period_lock.py).

    python3 tools/lock_period.py                               list the last few months and their status
    python3 tools/lock_period.py 2026-10 --by "Nathan Booth"   lock October 2026 for all three organisations
    python3 tools/lock_period.py 2026-10 --org trades --by ...  lock it for one organisation
    python3 tools/lock_period.py 2026-09 --reopen --by ... --note "late supplier credit"

Locking is the deliberate end of the month-end close: once a month is locked its numbers are final, reports default
to it, and it's labelled Locked everywhere. A month can only be locked once it's over (as at the run,
data_status.AS_AT). Reopening records why; lock it again when the adjustment is in.

Then rebuild, so the site and the downloads say so: python3 tools/run_pipeline.py (stages 1 and 3).
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import argparse
import csv
import re
from datetime import date

import winutf8; winutf8.ensure()   # Windows: run in UTF-8 mode
import data_status as ds
import period_lock as pl


def show(rows, n=6):
    months = sorted({r["month_key"] for r in rows}, reverse=True)[:n]
    nxt = date(ds.AS_AT.year, ds.AS_AT.month, 1).strftime("%Y-%m")
    for m in ([nxt] if nxt not in months else []) + months:
        bits = []
        for org in pl.ORGS:
            a = pl.state(rows, org, m, ds.AS_AT)
            bits.append(f"{org} {a['action'].lower()} {a['action_at'][:10]} ({a['action_by']})" if a else f"{org} not locked")
        print(f"  {m}  {ds.month_status(m)[0]:<11}  " + " · ".join(bits))


def main():
    ap = argparse.ArgumentParser(description="Lock or reopen a month in the period-lock register.")
    ap.add_argument("month", nargs="?", help="YYYY-MM")
    ap.add_argument("--org", choices=pl.ORGS, help="one organisation (default: all three)")
    ap.add_argument("--by", help="who is locking it (required to lock or reopen)")
    ap.add_argument("--reopen", action="store_true", help="reopen a locked month")
    ap.add_argument("--note", default="", help="why (a reopen should always say)")
    a = ap.parse_args()
    rows = pl.read()
    if not a.month:
        print(f"As at {ds.as_at_text()}:")
        show(rows)
        return
    if not re.fullmatch(r"\d{4}-\d{2}", a.month):
        raise SystemExit("Month as YYYY-MM, e.g. 2026-10")
    if not a.by:
        raise SystemExit("Say who is doing it: --by \"Your Name\"")
    if not a.reopen and ds.month_end(a.month) >= ds.AS_AT.date():
        raise SystemExit(f"{a.month} isn't over yet (as at {ds.as_at_text()}): a month can only be locked once it has ended.")
    if a.reopen and not a.note:
        raise SystemExit("Say why it's being reopened: --note \"...\"")
    action = "Reopened" if a.reopen else "Locked"
    stamp = ds.AS_AT.strftime("%Y-%m-%d %H:%M")
    changed = []
    for org in ([a.org] if a.org else pl.ORGS):
        cur = pl.state(rows, org, a.month, ds.AS_AT)
        if (cur and cur["action"] == action) or (a.reopen and not cur):
            print(f"  {org} {a.month}: already {'locked' if action == 'Locked' else 'open'}, nothing to do")
            continue
        changed.append({"org_id": org, "month_key": a.month, "action": action, "action_at": stamp, "action_by": a.by, "note": a.note})
    if changed:
        with open(pl.path(), newline="", encoding="utf-8") as f:
            raw = list(csv.DictReader(f))
        pl.write(raw + changed)
        print(f"{action} {a.month} for {', '.join(c['org_id'] for c in changed)} ({a.by}, {stamp}). "
              "Rebuild to update the site and downloads: python3 tools/run_pipeline.py")
    show(pl.read())


if __name__ == "__main__":
    main()
