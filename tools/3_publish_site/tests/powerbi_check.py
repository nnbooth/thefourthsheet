#!/usr/bin/env python3
"""
powerbi_check.py — checks the Power BI project in powerbi/ (written by tools/3_publish_site/powerbi_statements.py)
without Power BI, so a broken file is caught before anyone opens it:

  1. Every report file (.pbip, .pbir, report.json, pages, visuals, .platform) is valid against the JSON schema it names:
     Microsoft's published schemas, downloaded once from github.com/microsoft/json-schemas and kept in
     ~/.cache/fourthsheet/json-schemas. Skipped, with a note, if jsonschema isn't installed or there's no internet.
  2. Every field a visual uses is a column or measure of that table in the model, and every page's filter values exist
     (statements, Period view items).
  3. Every 'Table'[column] and [measure] the DAX names exists; every relationship joins columns that exist; every table
     has a partition (or is the calculation group); indentation is tabs only.

  python3 tools/3_publish_site/tests/powerbi_check.py

What it can't check: that DAX evaluates (that needs Power BI's engine). The numbers the DAX must reproduce are
checked in stage 1 (statement_lines.py), with the same rules the [Amount] measure follows.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import json
import re
import ssl
import urllib.request
from pathlib import Path

ROOT = _T.parent / "powerbi"
CACHE = Path.home() / ".cache" / "fourthsheet" / "json-schemas"
CANONICAL = "https://developer.microsoft.com/json-schemas/"
MIRROR = "https://raw.githubusercontent.com/microsoft/json-schemas/main/"


def fetch(url):
    """A schema, from the cache or GitHub (the canonical host redirects there; this skips the hop)."""
    rel = url.split(CANONICAL, 1)[1].replace("schema.embedded.json", "schema-embedded.json")
    f = CACHE / rel
    if not f.exists():
        import net
        try:
            body = net.urlopen(MIRROR + rel).read()
        except Exception:                                  # a proxy with its own certificates (SSL_CERT_FILE)
            body = urllib.request.urlopen(MIRROR + rel, timeout=15, context=ssl.create_default_context()).read()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body)
    return json.loads(f.read_text(encoding="utf-8"))


def model():
    """{table: {"columns": set, "measures": set, "items": [calculation items]}} from the TMDL."""
    out = {}
    for f in sorted(ROOT.glob("*.SemanticModel/definition/tables/*.tmdl")):
        text = f.read_text(encoding="utf-8")
        name = re.search(r"^table (.+)$", text, re.M).group(1).strip("'")
        out[name] = {"columns": {c.strip("'") for c in re.findall(r"^\tcolumn (.+)$", text, re.M)},
                     "measures": {m.strip("'") for m in re.findall(r"^\tmeasure (.+?) =", text, re.M)},
                     "items": [i.strip("'") for i in re.findall(r"^\t\tcalculationItem (.+?) =", text, re.M)],
                     "text": text, "file": f.name}
    return out


def fields(o, found):
    """Every (kind, entity, property) a visual's JSON refers to."""
    if isinstance(o, dict):
        for kind in ("Column", "Measure"):
            if kind in o and "SourceRef" in o[kind].get("Expression", {}) and "Entity" in o[kind]["Expression"]["SourceRef"]:
                found.append((kind, o[kind]["Expression"]["SourceRef"]["Entity"], o[kind]["Property"]))
        for v in o.values():
            fields(v, found)
    elif isinstance(o, list):
        for v in o:
            fields(v, found)
    return found


def check_schemas(problems):
    try:
        import jsonschema
        from referencing import Registry, Resource
    except ImportError:
        return "skipped (pip install jsonschema)"
    registry = Registry(retrieve=lambda uri: Resource.from_contents(fetch(uri)))
    n = 0
    files = [f for f in ROOT.rglob("*") if f.is_file() and (f.suffix in (".json", ".pbir", ".pbism", ".pbip") or f.name == ".platform")]
    for f in sorted(files):
        doc = json.loads(f.read_text(encoding="utf-8"))
        if "$schema" not in doc:
            if "RegisteredResources" not in f.parts:
                problems.append(f"{f.relative_to(ROOT)}: no $schema")
            continue
        try:
            schema = fetch(doc["$schema"])
        except Exception as e:
            return f"skipped (couldn't download the schemas: {e})"
        v = jsonschema.Draft7Validator(schema, registry=registry) if "draft-07" in schema.get("$schema", "") else \
            jsonschema.validators.validator_for(schema)(schema, registry=registry)
        for err in v.iter_errors(doc):
            problems.append(f"{f.relative_to(ROOT)}: {'/'.join(map(str, err.absolute_path))}: {err.message[:200]}")
        n += 1
    return f"{n} files valid against their schemas"


def main():
    problems = []
    if not ROOT.exists():
        raise SystemExit("No powerbi/ folder: run python3 tools/3_publish_site/powerbi_statements.py")
    m = model()
    # 2. the report's fields and filter values
    for f in sorted(ROOT.glob("*.Report/definition/pages/*/visuals/*/visual.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        for kind, entity, prop in fields(doc, []):
            what = "columns" if kind == "Column" else "measures"
            if entity not in m or prop not in m[entity][what]:
                problems.append(f"{f.relative_to(ROOT)}: {kind.lower()} {entity}[{prop}] isn't in the model")
        for flt in doc.get("filterConfig", {}).get("filters", []):
            col = flt["field"]["Column"]
            if col["Expression"]["SourceRef"]["Entity"] == "Period view":
                vals = [v[0]["Literal"]["Value"].strip("'") for v in flt["filter"]["Where"][0]["Condition"]["In"]["Values"]]
                missing = set(vals) - set(m["Period view"]["items"])
                if missing:
                    problems.append(f"{f.relative_to(ROOT)}: no Period view item {sorted(missing)}")
    # 3. the DAX and the TMDL
    all_measures = {x for t in m.values() for x in t["measures"]}
    for name, t in m.items():
        body = t["text"]
        if "\n\tpartition " not in body and "\tcalculationGroup" not in body:
            problems.append(f"{t['file']}: no partition")
        for i, line in enumerate(body.split("\n"), 1):
            if re.match(r"^ +\S", line):
                problems.append(f"{t['file']}:{i}: indented with spaces, not tabs")
        dax = "\n".join(re.findall(r"^\t(?:measure|\tcalculationItem) .*?=\n((?:\t{3,}.*\n|\n)+)", body, re.M))
        for quoted, plain, colname in re.findall(r"(?:'([^']+)'|\b([A-Za-z_]+))\[([^\]]+)\]", dax):
            tbl = quoted or plain
            if tbl not in m or (colname not in m[tbl]["columns"] and colname not in m[tbl]["measures"]):
                problems.append(f"{t['file']}: DAX refers to {tbl}[{colname}], which isn't in the model")
        for ref in re.findall(r"(?<![\w'\]])\[([^\]]+)\]", dax):
            if ref not in all_measures:
                problems.append(f"{t['file']}: DAX refers to the measure [{ref}], which isn't in the model")
    rel = next(ROOT.glob("*.SemanticModel/definition/relationships.tmdl")).read_text(encoding="utf-8")
    for side, quoted, plain, c in re.findall(r"\t(fromColumn|toColumn): (?:'([^']+)'|(\w+))\.(\w+)", rel):
        tbl = quoted or plain
        if tbl not in m or c not in m[tbl]["columns"]:
            problems.append(f"relationships.tmdl: {side} {tbl}.{c} isn't in the model")
    # 1. the JSON schemas
    note = check_schemas(problems)
    if problems:
        print("Power BI project check FAILED:\n  " + "\n  ".join(problems[:40]))
        sys.exit(1)
    print(f"Power BI project check passed: {len(m)} tables, fields and DAX references all in the model; schemas: {note}")


if __name__ == "__main__":
    main()
