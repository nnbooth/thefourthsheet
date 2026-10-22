#!/usr/bin/env python3
"""
period_lock.py — the period-lock register: which months have been locked (closed), by whom and when.

A month is locked by a person, deliberately, once its books are final (standard month-end practice): nothing locks
on a date by itself. Locking can be undone (a month reopened for a late adjustment) and locked again; the register
keeps every action, so the history of the close is never lost.

    Data/Common/period_lock.csv (loaded into the database as period_lock, like every other table)
      org_id     trades / services / nfp
      month_key  YYYY-MM
      action     Locked or Reopened
      action_at  YYYY-MM-DD HH:MM (Brisbane)
      action_by  who did it
      note       why (optional)

A month's state as at a moment is the last action on or before it. data_status.py reads this for every Locked /
Provisional / Incomplete label; tools/lock_period.py adds to it. The data build (tools/1_build_data/sample_data.py)
fills in the sample history's closes (Oct 2024 to Sep 2026, each on the 2nd working day of the next month, as a
bookkeeper would have done them) but never changes or removes a row someone entered.
"""
import csv
import os
from datetime import datetime
from pathlib import Path

ORGS = ("trades", "services", "nfp")
COLUMNS = ["org_id", "month_key", "action", "action_at", "action_by", "note"]
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
    """Every action in the register, oldest first. Stops with a plain message if there is no register yet."""
    p = path()
    if not p.exists():
        raise SystemExit(f"No period-lock register at {p}. Run python3 tools/1_build_data/sample_data.py to start it "
                         "(it fills in the sample history's closes), then lock months with tools/lock_period.py.")
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["when"] = datetime.strptime(r["action_at"], "%Y-%m-%d %H:%M")
    return sorted(rows, key=lambda r: (r["when"], r["org_id"], r["month_key"]))


def write(rows):
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["action_at"], r["org_id"], r["month_key"]))
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows([[r.get(c) or "" for c in COLUMNS] for r in rows])


def state(rows, org, month, as_at):
    """The last action on or before as_at for one organisation's month: the row, or None (never locked)."""
    last = None
    for r in rows:
        if r["org_id"] == org and r["month_key"] == month and r["when"] <= as_at:
            last = r
    return last


def seed_history(months, lock_day):
    """Make sure the sample history's closes are in the register: for each organisation and month in `months` with no
    action at all, a Locked row on lock_day(month) at 9am by the bookkeeper. Rows already there (anyone's) are kept as
    they are, so a month someone reopened stays reopened. Returns how many rows were added."""
    p = path()
    rows = []
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    have = {(r["org_id"], r["month_key"]) for r in rows}
    added = [{"org_id": org, "month_key": m, "action": "Locked", "action_at": f"{lock_day(m).isoformat()} 09:00",
              "action_by": HISTORY_BY, "note": "Month-end close"}
             for m in months for org in ORGS if (org, m) not in have]
    if added or not p.exists():
        write(rows + added)
    return len(added)
