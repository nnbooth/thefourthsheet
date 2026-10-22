"""
readable_json.py — JSON for the generated data/*.js files that a person can read.

Containers are indented; anything with nothing nested inside it (one map point, one KPI set, a list of numbers)
stays on one line, so a list of records reads like a table.
"""

import json


def dumps(o, indent="  ", level=0):
    flat = lambda v: json.dumps(v, ensure_ascii=False, separators=(", ", ": "))
    nested = lambda v: isinstance(v, (dict, list)) and any(isinstance(x, (dict, list)) and x for x in (v.values() if isinstance(v, dict) else v))
    if not nested(o):
        return flat(o)
    pad, inner = indent * level, indent * (level + 1)
    if isinstance(o, dict):
        items = [f"{inner}{json.dumps(k, ensure_ascii=False)}: {dumps(v, indent, level + 1)}" for k, v in o.items()]
        return "{\n" + ",\n".join(items) + f"\n{pad}}}"
    return "[\n" + ",\n".join(inner + dumps(v, indent, level + 1) for v in o) + f"\n{pad}]"
