#!/usr/bin/env python3
"""
period_lock.py — the period-lock register: which months have been locked (closed), by whom and when.

A month is locked by a person, deliberately, once its books are final (standard month-end practice): nothing locks
on a date by itself. One row per organisation and month; reopening a month (for a late adjustment) blanks its lock
and says why, and locking it again fills the lock back in.

    Data/Common/period_lock.csv (loaded into the database as period_lock, like every other table)
      org_id     trades / services / nfp          } the key
      month_key  YYYY-MM                          }
      locked_at  YYYY-MM-DD HH:MM (Brisbane), blank while it's open
      locked_by  who locked it
      note       why (a reopened month says why it was reopened)

A month is locked as at a moment when locked_at is on or before it. data_status.py reads this for every Locked /
Provisional / Incomplete label; tools/lock_period.py changes it. The data build (tools/1_build_data/sample_data.py)
fills in the sample history's closes (Oct 2024 to Sep 2026, each on the 2nd working day of the next month, as a
bookkeeper would have done them) but never changes or removes a row someone entered.
"""
import csv
import os
from datetime import datetime
from pathlib import Path

ORGS = ("trades", "services", "nfp")
COLUMNS = ["org_id", "month_key", "locked_at", "locked_by", "note"]
HISTORY_BY = "Bookkeeper (sample history)"


def path():
    """Data/Common/period_lock.csv in the OneDrive Data folder (or FOURTH_SHEET_DATA)."""
    if os.getenv("FOURTH_SHEET_DATA"):
        root = Path(os.getenv("FOURTH_SHEET_DATA")).expanduser()
    else:
        from sync_media import onedrive_root
        root = onedrive_root() / "Data"
    return root / "Common" / "period_lock.csv"


def read():
    """The register as {(org_id, month_key): row}, each row with `when` (locked_at as a datetime, or None).
    Stops with a plain message if there is no register yet."""
    p = path()
    if not p.exists():
        raise SystemExit(f"No period-lock register at {p}. Run python3 tools/1_build_data/sample_data.py to start it "
                         "(it fills in the sample history's closes), then lock months with tools/lock_period.py.")
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["when"] = datetime.strptime(r["locked_at"], "%Y-%m-%d %H:%M") if r["locked_at"] else None
    return {(r["org_id"], r["month_key"]): r for r in rows}


def write(reg):
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows([[reg[k].get(c) or "" for c in COLUMNS] for k in sorted(reg, key=lambda k: (k[1], k[0]))])


def locked(reg, org, month, as_at):
    """The row if the organisation's month is locked as at the moment, else None."""
    r = reg.get((org, month))
    return r if r and r["when"] and r["when"] <= as_at else None


def seed_history(months, lock_day):
    """Make sure the sample history's closes are in the register: for each organisation and month in `months` with no
    row, one locked on lock_day(month) at 9am by the bookkeeper. Rows already there (anyone's) are kept as they are, so
    a month someone reopened stays reopened. Returns how many rows were added."""
    p = path()
    reg = read() if p.exists() else {}
    added = {(org, m): {"org_id": org, "month_key": m, "locked_at": f"{lock_day(m).isoformat()} 09:00",
                        "locked_by": HISTORY_BY, "note": "Month-end close"}
             for m in months for org in ORGS if (org, m) not in reg}
    if added or not p.exists():
        write({**reg, **added})
    return len(added)
