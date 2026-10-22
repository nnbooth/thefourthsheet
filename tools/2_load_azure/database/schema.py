"""
schema.py — the tables, read from the generated schema.sql (OneDrive, Data documentation/).

For each table: its CREATE TABLE statement, its columns and types, the CSV file(s) it loads from, and the
tables it references (so dimensions load before the facts that point at them).
"""

import re
from pathlib import Path

from . import config


def schema_file():
    return config.onedrive_project() / "Data documentation" / "schema.sql"


def data_root():
    return config.onedrive_project() / "Data"


class Table:
    """A table in the database. key = 'name' for the website's tables (schema dbo), 'schema.name' for the datasets."""

    def __init__(self, qualname, ddl, comment):
        self.schema_name, self.name = qualname.split(".") if "." in qualname else ("dbo", qualname)
        self.key = qualname
        self.qual = f"[{self.schema_name}].[{self.name}]"
        self.stage = f"stage.[{self.schema_name}__{self.name}]"
        self.ddl = ddl.strip()
        body = ddl[ddl.index("(") + 1:ddl.rindex(")")]
        self.columns = []
        for part in re.split(r",\s*\n", body):
            m = re.match(r"\s*([a-z_][a-z0-9_]*)\s+([A-Z]+(?:\([0-9, ]+\))?)", part)
            if m and m.group(1) not in ("primary", "foreign", "constraint", "unique"):
                self.columns.append((m.group(1), m.group(2)))
        self.refs = sorted({(f"{s}.{t}" if s and s != "dbo" else t) for s, t in re.findall(r"REFERENCES\s+(?:([a-z_]+)\.)?([a-z_]+)", ddl)} - {qualname})
        path = re.search(r"\[Data/([^\]]+?)(?: \(one file per organisation[^\]]*\))?\]", comment)
        self.pattern = path.group(1) if path else None

    def files(self):
        if not self.pattern:
            return []
        if "<organisation>" in self.pattern:
            return sorted(data_root().glob(self.pattern.replace("<organisation>", "*")))
        f = data_root() / self.pattern
        return [f] if f.exists() else []

    def ddl_stage(self):
        """The CREATE TABLE for its staging copy, with keys and references dropped."""
        cols = ",\n".join(f"    [{c}] {t}" for c, t in self.columns)
        return f"CREATE TABLE {self.stage} (\n{cols}\n);"

    def ddl_live(self, tables=None):
        """The CREATE TABLE for the live table. With tables (schema.tables()), a column that references another table
        takes that column's type (schema.sql has org_id VARCHAR(10) pointing at dim_org's VARCHAR(12): SQL Server
        won't link columns of different lengths). The schema file itself is left as it is."""
        ddl = self.ddl
        if tables:
            ddl = re.sub(r"(\n\s*[a-z_]+\s+)([A-Z]+(?:\([0-9, ]+\))?)([^,\n]*?REFERENCES\s+((?:[a-z_]+\.)?[a-z_]+)\(([a-z_]+)\))",
                         lambda m: m.group(1) + ((dict(tables[m.group(4)].columns).get(m.group(5)) if m.group(4) in tables else None) or m.group(2)) + m.group(3), ddl)
        if self.schema_name != "dbo":
            return ddl
        return re.sub(r"REFERENCES ([a-z_]+)\(", r"REFERENCES dbo.\1(", re.sub(r"^CREATE TABLE ([a-z_]+)", r"CREATE TABLE dbo.\1", ddl))


def schema_files():
    """schema.sql (the website's tables) and schema-<dataset>.sql (Retail, Health, Legal: tools/1_build_data/datasets.py)."""
    return [schema_file()] + sorted(schema_file().parent.glob("schema-*.sql"))


def tables():
    out = {}
    for f in schema_files():
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"((?:--[^\n]*\n)*)(CREATE TABLE ((?:[a-z_]+\.)?[a-z_]+) \((?:.|\n)*?\n\);)", text):
            out[m.group(3)] = Table(m.group(3), m.group(2), m.group(1))
    return out


def load_order(ts):
    """Referenced tables first (a dimension before the facts that point at it)."""
    done, order = set(), []

    def visit(n, path=()):
        if n in done or n not in ts:
            return
        if n in path:
            raise SystemExit(f"Circular references in the schema: {' -> '.join(path + (n,))}")
        for r in ts[n].refs:
            visit(r, path + (n,))
        done.add(n)
        order.append(n)
    for n in sorted(ts):
        visit(n)
    return order
