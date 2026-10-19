"""
load.py — load the CSVs (OneDrive Data/) into the cloud database, safely.

    python3 tools/database/load.py --check     stage and check everything, change nothing live
    python3 tools/database/load.py             load: stage, check, then replace the live tables
    python3 tools/database/load.py --tables dim_org,fact_gl_daily

How it stays safe:
  - Signed in with the SQL login; its password comes from FOURTH_SHEET_SQL_PASSWORD (environment or the
    git-ignored .env) or Azure Key Vault, and is never shown. Encrypted, certificate checked.
  - Each file's columns must match the table exactly, or nothing loads.
  - Every row goes into stage.<table> first. Row counts and a checksum (the sum of every number) are read
    back and compared with the files. Any difference stops the load.
  - Only then are the live tables replaced, all in ONE transaction: either every table changes or none does.
    A failure part-way leaves the live data exactly as it was.
  - Every run is logged in ops.load_run / ops.load_table: who, which machine, when, what, how many rows.
  - Values are always sent as parameters, never pasted into SQL, so nothing in a file can run as a command.
"""

import argparse
import csv
import platform
import sys
import time
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import winutf8; winutf8.ensure()   # noqa: E402  Windows: run in UTF-8 mode

from database import connect as dbc   # noqa: E402
from database import config, schema   # noqa: E402

BATCH = 1000


def convert(kind):
    k = kind.split("(")[0]
    if k in ("INT", "BIGINT", "SMALLINT", "TINYINT"):
        return lambda v: None if v == "" else int(Decimal(v))
    if k in ("DECIMAL", "NUMERIC"):
        # rounded to the column's decimal places, as the database stores it, so the checksums compare like for like
        scale = Decimal(1).scaleb(-int(kind.split(",")[1].rstrip(")"))) if "," in kind else Decimal(1)
        return lambda v: None if v == "" else Decimal(v).quantize(scale, ROUND_HALF_UP)
    if k in ("FLOAT", "REAL"):
        return lambda v: None if v == "" else Decimal(v)
    if k == "DATE":
        return lambda v: None if v == "" else date.fromisoformat(v)
    return lambda v: None if v == "" else v


def numeric(kind):
    return kind.split("(")[0] in ("INT", "BIGINT", "SMALLINT", "TINYINT", "DECIMAL", "NUMERIC", "FLOAT", "REAL")


def read_files(t):
    """All rows for a table from its file(s), converted to the column types. Checks the headers first."""
    want = [c for c, _ in t.columns]
    convs = [convert(k) for _, k in t.columns]
    rows, checksum = [], Decimal(0)
    nums = [i for i, (_, k) in enumerate(t.columns) if numeric(k)]
    files = t.files()
    if not files:
        raise SystemExit(f"{t.name}: no data file found ({t.pattern})")
    for f in files:
        with open(f, newline="", encoding="utf-8") as fh:
            r = csv.reader(fh)
            head = next(r)
            if head != want:
                raise SystemExit(f"{t.name}: the columns in {f} don't match the table.\n  file:  {head}\n  table: {want}\n"
                                 "Nothing was loaded. Rebuild schema.sql (python3 tools/sample_data.py) or fix the file.")
            for n, row in enumerate(r, 2):
                if len(row) != len(want):
                    raise SystemExit(f"{t.name}: {f.name} line {n} has {len(row)} values, expected {len(want)}. Nothing was loaded.")
                try:
                    vals = [c(v) for c, v in zip(convs, row)]
                except Exception as e:
                    raise SystemExit(f"{t.name}: {f.name} line {n}: {e}. Nothing was loaded.")
                checksum += sum((Decimal(vals[i]) for i in nums if vals[i] is not None), Decimal(0))
                rows.append(vals)
    return files, rows, checksum


def checksum_sql(t, where):
    """where: 'live' or 'stage'."""
    target = t.qual if where == "live" else t.stage
    nums = [c for c, k in t.columns if numeric(k)]
    if not nums:
        return f"SELECT COUNT(*), CAST(0 AS DECIMAL(38,6)) FROM {target}"
    s = " + ".join(f"CAST(ISNULL([{c}], 0) AS DECIMAL(38,6))" for c in nums)   # 6 places: the most any column has
    return f"SELECT COUNT(*), ISNULL(SUM({s}), 0) FROM {target}"


def existing_columns(cur, t):
    cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION", (t.schema_name, t.name))
    return [r[0] for r in cur.fetchall()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Load the CSVs into the cloud database (stage, check, then replace live in one transaction).")
    ap.add_argument("--check", action="store_true", help="stage and check only; change nothing live")
    ap.add_argument("--tables", help="comma-separated table names (default: all), e.g. dim_org,retail.fact_sales")
    ap.add_argument("--dataset", help="only one area: website (dbo), retail, health or legal")
    ap.add_argument("--rebuild", action="store_true", help="drop and recreate live tables whose columns have changed (their data is reloaded)")
    ap.add_argument("--interactive", action="store_true", help="sign in with your Microsoft account in the browser instead of the SQL login (only if the server has you as its Entra admin)")
    a = ap.parse_args(argv)

    ts = schema.tables()
    order = schema.load_order(ts)
    if a.tables:
        pick = set(a.tables.split(","))
        unknown = pick - set(ts)
        if unknown:
            raise SystemExit(f"Unknown table(s): {', '.join(sorted(unknown))}")
        order = [n for n in order if n in pick]
    if a.dataset:
        want = "dbo" if a.dataset == "website" else a.dataset
        order = [n for n in order if ts[n].schema_name == want]
        if not order:
            raise SystemExit(f"No tables for dataset {a.dataset!r}")

    print(f"Reading {len(order)} tables from {schema.data_root()} ...")
    data = {n: read_files(ts[n]) for n in order}
    print(f"  {sum(len(d[1]) for d in data.values()):,} rows, every file's columns match its table.")

    conn = dbc.connect(interactive=a.interactive)
    cur = conn.cursor()
    who, db, _ = dbc.whoami(conn)
    print(f"Connected to {config.server_host()} / {db} as {who} (encrypted).")
    cur.execute("SET XACT_ABORT ON")
    cur.execute("INSERT INTO ops.load_run (machine, source, status) OUTPUT INSERTED.load_id VALUES (?, ?, 'Running')",
                (platform.node(), f"CSV: {schema.data_root()}"))
    load_id = cur.fetchone()[0]
    conn.commit()
    t0 = time.time()
    try:
        # 1. live tables exist, with the right columns (each dataset in its own schema)
        for sch in sorted({ts[n].schema_name for n in order} - {"dbo"}):
            cur.execute(f"IF SCHEMA_ID('{sch}') IS NULL EXEC('CREATE SCHEMA [{sch}]')")
        for n in order:
            have = existing_columns(cur, ts[n])
            want = [c for c, _ in ts[n].columns]
            if not have:
                cur.execute(ts[n].ddl_live())
            elif have != want:
                if not a.rebuild:
                    raise SystemExit(f"{ts[n].qual} has different columns from its schema file.\n  database: {have}\n  schema:   {want}\n"
                                     "Re-run with --rebuild to recreate it (its data is reloaded from the files).")
                print(f"  rebuilding {ts[n].qual} (columns changed)")
        if a.rebuild:
            changed = [n for n in order if existing_columns(cur, ts[n]) not in ([], [c for c, _ in ts[n].columns])]
            for n in reversed(changed):
                cur.execute(f"DROP TABLE {ts[n].qual}")
            for n in changed:
                cur.execute(ts[n].ddl_live())
        conn.commit()

        # 2. stage every table and check it against the files
        report = []
        for n in order:
            t = ts[n]
            files, rows, csum = data[n]
            cur.execute(f"DROP TABLE IF EXISTS {t.stage}")
            cur.execute(t.ddl_stage())
            cols = ", ".join(f"[{c}]" for c, _ in t.columns)
            marks = ", ".join("?" for _ in t.columns)
            sql = f"INSERT INTO {t.stage} ({cols}) VALUES ({marks})"
            for i in range(0, len(rows), BATCH):
                cur.executemany(sql, rows[i:i + BATCH])
            conn.commit()
            cur.execute(checksum_sql(t, "stage"))
            got_n, got_sum = cur.fetchone()
            ok = got_n == len(rows) and Decimal(got_sum) == csum
            report.append((n, len(files), len(rows), got_n, csum, Decimal(got_sum)))
            print(f"  staged {n:44} {got_n:>7,} rows  {'ok' if ok else 'MISMATCH'}")
            if not ok:
                raise SystemExit(f"{n}: the database has {got_n} rows (checksum {got_sum}) but the files have {len(rows)} (checksum {csum}). Nothing live was changed.")

        if a.check:
            status, msg = "Checked", "Dry run: staged and checked; live tables not changed."
        else:
            # 3. replace the live tables, all in one transaction
            for n in reversed(order):
                cur.execute(f"DELETE FROM {ts[n].qual}")
            for n in order:
                cols = ", ".join(f"[{c}]" for c, _ in ts[n].columns)
                cur.execute(f"INSERT INTO {ts[n].qual} ({cols}) SELECT {cols} FROM {ts[n].stage}")
            for n, _, csv_rows, _, csum, _ in report:
                cur.execute(checksum_sql(ts[n], "live"))
                live_n, live_sum = cur.fetchone()
                if live_n != csv_rows or Decimal(live_sum) != csum:
                    raise SystemExit(f"{ts[n].qual} doesn't match after loading ({live_n} rows). Rolled back: nothing live was changed.")
            conn.commit()
            status, msg = "Loaded", f"{len(order)} tables replaced in one transaction."
        for n in order:
            cur.execute(f"DROP TABLE IF EXISTS {ts[n].stage}")
        for n, nf, csv_rows, got_n, csum, got_sum in report:
            cur.execute("INSERT INTO ops.load_table VALUES (?, ?, ?, ?, ?, ?, ?)", (load_id, n, nf, csv_rows, got_n, csum, got_sum))
        cur.execute("UPDATE ops.load_run SET finished_at = SYSUTCDATETIME(), status = ?, tables_loaded = ?, rows_loaded = ?, message = ? WHERE load_id = ?",
                    (status, len(order), sum(r[2] for r in report), msg, load_id))
        conn.commit()
        print(f"{status}: {msg} Load {load_id}, {time.time() - t0:.0f}s.")
    except BaseException as e:
        conn.rollback()
        cur.execute("UPDATE ops.load_run SET finished_at = SYSUTCDATETIME(), status = 'Failed', message = ? WHERE load_id = ?", (str(e)[:4000], load_id))
        conn.commit()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
