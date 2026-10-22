#!/usr/bin/env python3
"""
data_integrity.py — does all the data fit together, and do its identifiers look real? Reads every CSV the database
load reads (OneDrive Data/, via tools/2_load_azure/database/schema.py). Run from the repo root:

    python3 -I tools/2_load_azure/tests/data_integrity.py .

  1. Every declared reference (REFERENCES in the schema files) points at a row that exists.
  2. Every undeclared one does too: a column named like another table's key (customer_id, matter_id, fee_earner_id ...)
     must only hold values that table has.
  3. No identifier is numbered 1, 2, 3 ... from 1: real systems issue numbers over years, so customer, matter and
     transaction numbers don't start at one. Short code lists (statuses, reasons, practice areas: under 20 values) and
     plain counters (line numbers, month numbers) are allowed to.

Prints PASS or FAIL for each and exits 1 if anything fails.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

from database import load, schema  # noqa: E402

COUNTERS = {"line_no", "fy_month_no", "month_key"}        # counters, not identifiers
CODE_LIST_MAX = 20                                        # a lookup this short may be numbered 1..n

ts = schema.tables()
data = {n: ([c for c, _ in t.columns], load.read_files(t)[1]) for n, t in ts.items()}
sch = lambda n: n.split(".")[0] if "." in n else "dbo"
fails = []


def report(name, problems):
    print(("PASS " if not problems else "FAIL ") + name + ("" if not problems else ":\n  " + "\n  ".join(problems[:15])))
    if problems:
        fails.append(name)


# 1. declared references
bad, n = [], 0
declared = set()
for name, t in ts.items():
    cols, rows = data[name]
    for m in re.finditer(r"^\s*\[?(\w+)\]?\s+[^\n]*?REFERENCES\s+(?:(\w+)\.)?(\w+)\((\w+)\)", t.ddl, re.M):
        c, ps, pt, pc = m.groups()
        declared.add((name, c))
        parent = f"{ps}.{pt}" if ps and ps != "dbo" else (f"{sch(name)}.{pt}" if sch(name) != "dbo" else pt)
        if parent not in data:
            bad.append(f"{name}.{c}: no table {parent}")
            continue
        n += 1
        have = {r[data[parent][0].index(pc)] for r in data[parent][1]}
        i = cols.index(c)
        miss = {r[i] for r in rows if r[i] not in (None, "") and r[i] not in have}
        if miss:
            bad.append(f"{name}.{c} -> {parent}.{pc}: {len(miss)} value(s) missing, e.g. {sorted(map(str, miss))[:3]}")
report(f"1. {n} declared references all resolve", bad)

# 2. undeclared references, by column name
keys = {}
for name, (cols, rows) in data.items():
    if name.split(".")[-1].startswith("dim_") and cols[0].endswith("_id"):
        keys.setdefault((sch(name), cols[0]), name)
bad, n = [], 0
for name, (cols, rows) in data.items():
    for i, c in enumerate(cols):
        p = keys.get((sch(name), c))
        if not p or p == name or (name, c) in declared:
            continue
        n += 1
        have = {r[0] for r in data[p][1]}
        miss = {r[i] for r in rows if r[i] not in (None, "") and r[i] not in have}
        if miss:
            bad.append(f"{name}.{c} -> {p}: {len(miss)} value(s) missing, e.g. {sorted(map(str, miss))[:3]}")
report(f"2. {n} undeclared references (same column name as a key) all resolve", bad)

# 3. identifiers that start from 1
bad = []
for name, (cols, rows) in data.items():
    for i, c in enumerate(cols):
        if c in COUNTERS or not re.search(r"(_id|_no|number|_key|_code)$", c) or c.endswith("date_key"):
            continue
        nums = set()
        for r in rows:
            m = re.search(r"(\d+)$", str(r[i])) if r[i] not in (None, "") else None
            if m:
                nums.add(int(m.group(1)))
        if len(nums) > CODE_LIST_MAX and min(nums) <= 1:
            bad.append(f"{name}.{c}: {len(nums):,} values, the lowest is {min(nums)}")
report("3. no identifier is numbered from 1 (code lists of up to 20 values excepted)", bad)

print("PROBLEMS:", fails)
sys.exit(1 if fails else 0)
