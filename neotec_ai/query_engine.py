"""Governed data access for the AI.

The model never writes SQL. It returns a JSON query plan; every plan is checked against the
Data Dictionary (Neotec Data Source) and then executed with frappe.get_list, which applies the
current user's role permissions, user permissions and field-level (permlevel) restrictions.
"""

import json
import re
from decimal import Decimal

import frappe

AGG_FUNCS = {"sum", "count", "avg", "min", "max"}
DATE_FUNCS = {"year", "month", "quarter", "date"}
DATE_TYPES = {"Date", "Datetime"}
NUMERIC_TYPES = {"Int", "Float", "Currency", "Percent", "Duration", "Rating", "Check"}
CHART_NUMERIC_TYPES = {"Int", "Float", "Currency", "Percent", "Duration", "Rating"}

OPERATORS = {
    "=", "!=", ">", "<", ">=", "<=", "like", "not like", "in", "not in", "between", "is", "timespan",
}
TIMESPANS = {
    "today", "yesterday", "tomorrow", "this week", "last week", "next week",
    "this month", "last month", "next month", "this quarter", "last quarter", "next quarter",
    "this year", "last year", "next year", "last 6 months", "next 6 months",
}

IDENT = r"[a-z_][a-z0-9_]{0,63}"
RE_PLAIN = re.compile(rf"^({IDENT})$")
RE_AGG = re.compile(rf"^(sum|count|avg|min|max)\(\s*(distinct\s+)?({IDENT}|\*)\s*\)(?:\s+as\s+({IDENT}))?$")
RE_DATE = re.compile(rf"^(year|month|quarter|date)\(\s*({IDENT})\s*\)(?:\s+as\s+({IDENT}))?$")
RE_ORDER = re.compile(rf"^({IDENT})(?:\s+(asc|desc))?$")

MAX_QUERIES_PER_ROUND = 5
MAX_FILTERS = 15
MAX_IN_VALUES = 200


class PlanError(Exception):
    """A query plan the dictionary does not allow. The message is shown to the model so it can fix it."""


# --------------------------------------------------------------------------------------
# Catalog
# --------------------------------------------------------------------------------------

def get_catalog(check_permissions=True):
    """Enabled data sources keyed by DocType; by default only those the current user can read."""
    catalog = {}
    for name in frappe.get_all("Neotec Data Source", filters={"enabled": 1}, pluck="name"):
        src = frappe.get_cached_doc("Neotec Data Source", name)
        perm_doctype = src.parent_doctype if src.is_child_table else src.source_doctype
        if check_permissions and not frappe.has_permission(perm_doctype, "read"):
            continue
        fields = {
            row.fieldname: {
                "label": row.label,
                "fieldtype": row.fieldtype,
                "description": row.description or "",
            }
            for row in src.data_fields
            if row.enabled
        }
        if not fields:
            continue
        catalog[src.source_doctype] = {
            "doctype": src.source_doctype,
            "parent_doctype": src.parent_doctype if src.is_child_table else None,
            "submitted_only": bool(src.submitted_only),
            "description": src.description or "",
            "sample_questions": src.sample_questions or "",
            "fields": fields,
        }
    return catalog


def describe_catalog(catalog, joins=None):
    """Compact text description of the catalog for the system prompt.

    joins: optional {doctype: [ {doctype, via, kind}, ... ]} from bi.engine.join_options.
    """
    lines = []
    for dt, src in catalog.items():
        header = f"### {dt}"
        if src["parent_doctype"]:
            header += f" (line items of {src['parent_doctype']}; `parent` = {src['parent_doctype']} ID)"
        lines.append(header)
        lines.append(src["description"])
        if src["submitted_only"]:
            lines.append("(Only submitted records are visible.)")
        if src["sample_questions"]:
            lines.append(f"Answers questions like: {src['sample_questions']}")
        for fname, f in src["fields"].items():
            extra = f" - {f['description']}" if f["description"] else ""
            lines.append(f"- {fname} ({f['fieldtype']}, \"{f['label']}\"){extra}")
        for j in (joins or {}).get(dt, []):
            lines.append(f"  join -> {j['doctype']} via {j['via']} ({j['kind']})")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Plan validation (pure: no database access, unit-testable)
# --------------------------------------------------------------------------------------

def _alias_for(func, field):
    return f"{func}_{'all' if field == '*' else field}"


def validate_query(q, catalog, max_rows):
    """Turn one model-supplied query into safe get_list kwargs. Raises PlanError."""
    if not isinstance(q, dict):
        raise PlanError("Each query must be a JSON object.")

    doctype = q.get("doctype")
    if doctype not in catalog:
        raise PlanError(f"'{doctype}' is not an available data source. Use one listed in the dictionary.")
    src = catalog[doctype]
    allowed = src["fields"]

    def need_field(fname, ctx):
        if fname not in allowed:
            raise PlanError(f"{doctype}: field '{fname}' is not available ({ctx}). Allowed: {', '.join(allowed)}")
        return allowed[fname]

    # ---- fields ----
    raw_fields = q.get("fields") or []
    if isinstance(raw_fields, str):
        raw_fields = [raw_fields]
    if not isinstance(raw_fields, list) or not raw_fields:
        raise PlanError(f"{doctype}: 'fields' must be a non-empty list.")
    if len(raw_fields) > 25:
        raise PlanError(f"{doctype}: too many fields (max 25).")

    select, aliases, date_exprs, has_agg = [], set(), {}, False
    for raw in raw_fields:
        if not isinstance(raw, str):
            raise PlanError(f"{doctype}: field entries must be strings.")
        expr = " ".join(raw.strip().lower().split())

        m = RE_PLAIN.match(expr)
        if m:
            need_field(m.group(1), "fields")
            select.append(m.group(1))
            aliases.add(m.group(1))
            continue

        m = RE_AGG.match(expr)
        if m:
            func, distinct, fname, alias = m.group(1), m.group(2), m.group(3), m.group(4)
            if fname == "*":
                if func != "count" or distinct:
                    raise PlanError("Only count(*) is allowed with '*'.")
                fname = "name"  # counting rows reveals no field values
            else:
                f = need_field(fname, f"{func}()")
                if func in ("sum", "avg") and f["fieldtype"] not in NUMERIC_TYPES:
                    raise PlanError(f"{func}() needs a numeric field; '{fname}' is {f['fieldtype']}.")
            if distinct and func != "count":
                raise PlanError("DISTINCT is only allowed inside count().")
            alias = alias or _alias_for(func, m.group(3))
            select.append(f"{func}({'distinct ' if distinct else ''}{fname}) as {alias}")
            aliases.add(alias)
            has_agg = True
            continue

        m = RE_DATE.match(expr)
        if m:
            func, fname, alias = m.group(1), m.group(2), m.group(3)
            f = need_field(fname, f"{func}()")
            if f["fieldtype"] not in DATE_TYPES:
                raise PlanError(f"{func}() needs a Date/Datetime field; '{fname}' is {f['fieldtype']}.")
            alias = alias or f"{func}_{fname}"
            select.append(f"{func}({fname}) as {alias}")
            aliases.add(alias)
            date_exprs[alias] = f"{func}({fname})"
            continue

        raise PlanError(
            f"{doctype}: unsupported field expression '{raw}'. Use a field name, "
            "sum/count/avg/min/max(field) [as alias], or year/month/quarter/date(date_field) [as alias]."
        )

    # ---- filters ----
    filters = []
    raw_filters = q.get("filters") or []
    if isinstance(raw_filters, dict):
        raw_filters = [[k, "=", v] for k, v in raw_filters.items()]
    if not isinstance(raw_filters, list):
        raise PlanError(f"{doctype}: 'filters' must be a list of [field, operator, value].")
    if len(raw_filters) > MAX_FILTERS:
        raise PlanError(f"{doctype}: too many filters (max {MAX_FILTERS}).")

    for flt in raw_filters:
        if not isinstance(flt, (list, tuple)) or len(flt) != 3:
            raise PlanError(f"{doctype}: each filter must be [field, operator, value]; got {flt!r}.")
        fname, op, value = flt
        if not isinstance(fname, str) or not isinstance(op, str):
            raise PlanError(f"{doctype}: filter field and operator must be strings.")
        fname, op = fname.strip().lower(), " ".join(op.strip().lower().split())
        f = need_field(fname, "filters")
        if op not in OPERATORS:
            raise PlanError(f"Operator '{op}' is not allowed. Use one of: {', '.join(sorted(OPERATORS))}.")
        value = _check_value(op, value, f, fname)
        if op == "timespan":
            op = "Timespan"
        filters.append([doctype, fname, op, value])

    if src["submitted_only"]:
        filters.append([doctype, "docstatus", "=", 1])

    # ---- group by ----
    group_by = q.get("group_by") or []
    if isinstance(group_by, str):
        group_by = [g for g in group_by.split(",") if g.strip()]
    if not isinstance(group_by, list):
        raise PlanError(f"{doctype}: 'group_by' must be a list.")
    group_terms = []
    for g in group_by:
        g = " ".join(str(g).strip().lower().split())
        if g in date_exprs:
            group_terms.append(date_exprs[g])
        elif RE_DATE.match(g) and not RE_DATE.match(g).group(3):
            dm = RE_DATE.match(g)
            f = need_field(dm.group(2), "group_by")
            if f["fieldtype"] not in DATE_TYPES:
                raise PlanError(f"{dm.group(1)}() needs a Date/Datetime field.")
            group_terms.append(f"{dm.group(1)}({dm.group(2)})")
        elif RE_PLAIN.match(g):
            need_field(g, "group_by")
            group_terms.append(g)
        else:
            raise PlanError(f"{doctype}: cannot group by '{g}'. Use a field name or a date alias from 'fields'.")
    if len(group_terms) > 4:
        raise PlanError("Group by at most 4 terms.")

    # ---- order by ----
    order_by = q.get("order_by")
    order_term = None
    if order_by:
        parts = order_by if isinstance(order_by, list) else str(order_by).split(",")
        terms = []
        for part in parts:
            ob = " ".join(str(part).strip().lower().split())
            if not ob:
                continue
            m = RE_ORDER.match(ob)
            if not m or (m.group(1) not in aliases and m.group(1) not in allowed):
                raise PlanError(
                    f"{doctype}: order_by must be '<field or alias from fields> asc|desc' (comma-separated, max 3); got '{part}'."
                )
            terms.append(f"{m.group(1)} {m.group(2) or 'asc'}")
        if len(terms) > 3:
            raise PlanError("order_by accepts at most 3 terms.")
        order_term = ", ".join(terms) or None
    elif group_terms:
        reverse = {expr: alias for alias, expr in date_exprs.items()}
        order_term = ", ".join(f"{reverse.get(t, t)} asc" for t in group_terms)
    elif not has_agg:
        order_term = "modified desc"

    # ---- limit ----
    try:
        limit = int(q.get("limit") or max_rows)
    except (TypeError, ValueError):
        raise PlanError("limit must be an integer.")
    limit = max(1, min(limit, max_rows))

    kwargs = {
        "doctype": doctype,
        "fields": select,
        "filters": filters,
        "limit_page_length": limit,
    }
    if group_terms:
        kwargs["group_by"] = ", ".join(group_terms)
    if order_term:
        kwargs["order_by"] = order_term
    if src["parent_doctype"]:
        kwargs["parent_doctype"] = src["parent_doctype"]
    return kwargs


def output_columns(kwargs, catalog):
    """Describe the result columns of validated get_list kwargs: [{fieldname, label, fieldtype}]."""
    fields = catalog[kwargs["doctype"]]["fields"]
    cols = []
    for expr in kwargs["fields"]:
        if " as " in expr:
            body, alias = expr.rsplit(" as ", 1)
        else:
            body, alias = expr, expr
        m_agg = re.match(r"^(sum|count|avg|min|max)\((?:distinct )?([a-z0-9_]+)\)$", body)
        m_date = re.match(r"^(year|month|quarter|date)\(([a-z0-9_]+)\)$", body)
        if m_agg:
            func, fname = m_agg.groups()
            src = fields.get(fname, {})
            if func == "count":
                ftype = "Int"
            elif func == "avg":
                ftype = "Currency" if src.get("fieldtype") == "Currency" else "Float"
            else:
                ftype = src.get("fieldtype") or "Float"
            label = alias.replace("_", " ").title()
        elif m_date:
            func = m_date.group(1)
            ftype = "Date" if func == "date" else "Int"
            label = alias.replace("_", " ").title()
        else:
            f = fields.get(body, {})
            ftype = f.get("fieldtype") or "Data"
            label = f.get("label") or body.replace("_", " ").title()
        cols.append({"fieldname": alias, "label": label, "fieldtype": ftype})
    return cols


def _scalar_ok(v):
    return v is None or isinstance(v, (str, int, float, bool))


def _check_value(op, value, f, fname):
    if op in ("in", "not in"):
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        if not isinstance(value, list) or not value or len(value) > MAX_IN_VALUES:
            raise PlanError(f"'{op}' on {fname} needs a list of 1-{MAX_IN_VALUES} values.")
        if not all(_scalar_ok(v) for v in value):
            raise PlanError(f"'{op}' values must be plain values.")
        return value
    if op == "between":
        if not isinstance(value, list) or len(value) != 2 or not all(_scalar_ok(v) for v in value):
            raise PlanError(f"'between' on {fname} needs [from, to].")
        return value
    if op == "is":
        if value not in ("set", "not set"):
            raise PlanError("'is' only accepts 'set' or 'not set'.")
        return value
    if op == "timespan":
        if f["fieldtype"] not in DATE_TYPES or str(value).lower() not in TIMESPANS:
            raise PlanError(
                f"'timespan' needs a date field and one of: {', '.join(sorted(TIMESPANS))}."
            )
        return str(value).lower()
    if not _scalar_ok(value):
        raise PlanError(f"Filter value for {fname} must be a plain value.")
    if isinstance(value, str) and len(value) > 500:
        raise PlanError("Filter value too long.")
    return value


def parse_plan(text):
    """Extract the JSON action object from model output. Returns dict or None (= plain answer)."""
    if not text:
        return None
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.S)
    if fence:
        s = fence.group(1)
    elif not s.startswith("{"):
        start, end = s.find("{"), s.rfind("}")
        if start == -1 or end <= start or '"action"' not in s:
            return None
        s = s[start : end + 1]
    try:
        obj = json.loads(s)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) and obj.get("action") in ("query", "answer") else None


# --------------------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------------------

def run_queries(plan, catalog, max_rows, max_chars):
    """Validate and execute up to MAX_QUERIES_PER_ROUND queries.

    Returns (result_text_for_model, audit_entries).
    """
    queries = plan.get("queries") or []
    if not isinstance(queries, list) or not queries:
        return "ERROR: 'queries' must be a non-empty list.", []

    out, audit = [], []
    for i, q in enumerate(queries[:MAX_QUERIES_PER_ROUND], start=1):
        entry = {"query": q}
        try:
            kwargs = validate_query(q, catalog, max_rows)
            doctype = kwargs.pop("doctype")
            entry["executed"] = {"doctype": doctype, **kwargs}
            rows = frappe.get_list(doctype, **kwargs)  # permission-aware
            rows = [_clean_row(r) for r in rows]
            entry["row_count"] = len(rows)
            entry["rows"] = rows
            note = " (row limit reached; results may be incomplete)" if len(rows) >= kwargs["limit_page_length"] else ""
            out.append(f"Result {i} ({doctype}, {len(rows)} rows{note}):\n{json.dumps(rows, default=str)}")
        except PlanError as e:
            entry["error"] = str(e)
            out.append(f"Result {i}: INVALID QUERY - {e}")
        except frappe.PermissionError:
            frappe.clear_last_message()
            entry["error"] = "permission denied"
            out.append(f"Result {i}: PERMISSION DENIED - the user cannot read this data.")
        except Exception as e:
            frappe.clear_last_message()
            entry["error"] = str(e)[:300]
            out.append(f"Result {i}: QUERY FAILED - {str(e)[:300]}")
        audit.append(entry)

    if len(queries) > MAX_QUERIES_PER_ROUND:
        out.append(f"(Only the first {MAX_QUERIES_PER_ROUND} queries were run.)")

    text = "\n\n".join(out)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[TRUNCATED - narrow the query or aggregate instead]"
    return text, audit


def _clean_row(row):
    clean = {}
    for k, v in dict(row).items():
        if isinstance(v, Decimal):
            v = float(v)
        if isinstance(v, float):
            v = round(v, 4)
        clean[k] = v
    return clean
