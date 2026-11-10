"""Neotec BI query engine.

One structured, JSON query format is used by the visual builder, the AI, saved reports,
dashboards and scheduled e-mails:

    {
      "source": "Sales Invoice",
      "joins":   [{"doctype": "Sales Invoice Item", "from": "Sales Invoice", "via": "items", "type": "inner"},
                  {"doctype": "Item", "from": "Sales Invoice Item", "via": "item_code"}],
      "columns": [{"field": "Item.item_group", "label": "Item Group"},
                  {"field": "Sales Invoice.posting_date", "date_part": "year_month", "alias": "month"},
                  {"field": "Sales Invoice Item.base_net_amount", "agg": "sum", "alias": "revenue"},
                  {"formula": "revenue / 1000", "alias": "revenue_k", "label": "Revenue (K)"}],
      "filters": [{"field": "Sales Invoice.posting_date", "op": "timespan", "value": "this year"}],
      "having":  [{"column": "revenue", "op": ">", "value": 1000}],
      "order_by": [{"column": "revenue", "dir": "desc"}],
      "limit": 100
    }

Security model
- Only DocTypes and fields registered (and enabled) in the Data Dictionary can be used.
- Every non-child table needs the user's role *read* permission; otherwise an AccessError with a
  friendly message is raised.
- Frappe's own match conditions (User Permissions, "only if creator", permission query hooks,
  shares) are added for every table. Child tables are always tied to their parent, whose
  conditions apply.
- Field-level (permlevel) restrictions are respected.
- The SQL is assembled only from validated identifiers; every user value is a bound parameter.
"""

import ast
import datetime
import re

import frappe
from frappe.utils import cint

from neotec_ai.query_engine import PlanError as QueryError


class AccessError(Exception):
    """The user lacks permission for some data. The message is safe to show to the user."""


AGGS = ("sum", "count", "count_distinct", "avg", "min", "max")
DATE_PARTS = ("year", "quarter", "month", "week", "day", "year_quarter", "year_month", "year_week")
OPS = ("=", "!=", ">", "<", ">=", "<=", "like", "not like", "in", "not in", "between", "is", "timespan")
TIMESPANS = (
    "today", "yesterday", "tomorrow", "this week", "last week", "next week",
    "this month", "last month", "next month", "this quarter", "last quarter", "next quarter",
    "this year", "last year", "next year", "last 7 days", "last 30 days", "last 90 days",
    "last 6 months", "last 12 months", "year to date", "month to date",
)
NUMERIC = {"Int", "Float", "Currency", "Percent", "Duration", "Rating", "Check"}
DATE_TYPES = {"Date", "Datetime"}
STANDARD_FIELDS = {
    "name": ("ID", "Data"),
    "creation": ("Created On", "Datetime"),
    "modified": ("Last Modified", "Datetime"),
    "owner": ("Created By", "Link"),
    "docstatus": ("Document Status", "Int"),
    "parent": ("Parent Document ID", "Data"),
}

RE_ALIAS = re.compile(r"^[a-z_][a-z0-9_]{0,63}$")
RE_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,139}$")
RE_DOCTYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _\-]{0,139}$")

MAX_JOINS = 6
MAX_COLUMNS = 30
MAX_FILTERS = 30
MAX_IN_VALUES = 500
QUERY_TIMEOUT_SECONDS = 60


# --------------------------------------------------------------------------------------
# Environment (meta + permissions). Swappable for tests.
# --------------------------------------------------------------------------------------

class FrappeEnv:
    def __init__(self, user=None):
        self.user = user or frappe.session.user

    def meta(self, doctype):
        return frappe.get_meta(doctype)

    def can_read(self, doctype):
        from frappe.permissions import get_role_permissions

        perms = get_role_permissions(frappe.get_meta(doctype), user=self.user)
        return bool(perms.get("read"))

    def match_conditions(self, doctype):
        from frappe.desk.reportview import build_match_conditions

        return build_match_conditions(doctype, user=self.user) or ""

    def permitted_fields(self, doctype, parenttype=None):
        meta = frappe.get_meta(doctype)
        try:
            return set(meta.get_permitted_fieldnames(parenttype=parenttype, user=self.user))
        except Exception:
            return {df.fieldname for df in meta.fields if not (df.permlevel or 0)}


# --------------------------------------------------------------------------------------
# Join graph
# --------------------------------------------------------------------------------------

def join_options(doctype, catalog, env):
    """Joins available *from* doctype to other Data Dictionary DocTypes."""
    meta = env.meta(doctype)
    src = catalog.get(doctype) or {}
    enabled = src.get("fields", {})
    try:
        permitted = env.permitted_fields(doctype, src.get("parent_doctype") if meta.istable else None)
    except Exception:
        permitted = set()
    opts = []
    for df in meta.fields:
        if df.fieldname not in permitted:
            continue  # the join key itself must be visible to the user
        if df.fieldtype == "Link" and df.options in catalog and df.options != doctype:
            if df.fieldname not in enabled or env.meta(df.options).istable:
                continue  # link must be an enabled dictionary field; never link-join a child table
            opts.append({"doctype": df.options, "via": df.fieldname, "kind": "link", "label": df.label or df.fieldname})
        elif df.fieldtype in ("Table", "Table MultiSelect") and df.options in catalog:
            opts.append({"doctype": df.options, "via": df.fieldname, "kind": "child", "label": df.label or df.fieldname})
    if meta.istable:
        parent = (catalog.get(doctype) or {}).get("parent_doctype")
        if parent and parent in catalog:
            opts.append({"doctype": parent, "via": "parent", "kind": "parent", "label": parent})
    return opts


def _resolve_join(j, tables, catalog, env):
    target, frm, via = j.get("doctype"), j.get("from"), j.get("via")
    if target not in catalog:
        raise QueryError(f"Cannot join '{target}': it is not in the Data Dictionary.")
    if target in tables:
        raise QueryError(f"'{target}' is already part of the query; each DocType can be used once.")
    if frm not in tables:
        raise QueryError(f"Join to '{target}' comes from '{frm}', which is not in the query yet.")
    options = [o for o in join_options(frm, catalog, env) if o["doctype"] == target]
    if not options:
        raise QueryError(f"There is no relationship from '{frm}' to '{target}'.")
    if via:
        options = [o for o in options if o["via"] == via]
        if not options:
            raise QueryError(f"'{frm}' has no field '{via}' linking to '{target}'.")
    elif len(options) > 1:
        raise QueryError(
            f"'{frm}' links to '{target}' in several ways ({', '.join(o['via'] for o in options)}); set 'via'."
        )
    return options[0]


# --------------------------------------------------------------------------------------
# Spec normalisation (also converts the v2.x string format)
# --------------------------------------------------------------------------------------

_LEG_AGG = re.compile(r"^(sum|count|avg|min|max)\(\s*(distinct\s+)?([a-z0-9_]+|\*)\s*\)(?:\s+as\s+([a-z0-9_]+))?$")
_LEG_DATE = re.compile(r"^(year|month|quarter|date)\(\s*([a-z0-9_]+)\s*\)(?:\s+as\s+([a-z0-9_]+))?$")


def normalize_query(q):
    if isinstance(q, str):
        import json

        try:
            q = json.loads(q)
        except ValueError:
            raise QueryError("Query is not valid JSON.")
    if not isinstance(q, dict):
        raise QueryError("Query must be an object.")
    if "source" not in q and "doctype" in q:
        return _from_legacy(q)
    return {
        "source": q.get("source"),
        "joins": q.get("joins") or [],
        "columns": q.get("columns") or [],
        "filters": q.get("filters") or [],
        "having": q.get("having") or [],
        "order_by": q.get("order_by") or [],
        "limit": q.get("limit"),
    }


def _from_legacy(q):
    """Convert the v2.x format ({doctype, fields: ["sum(x) as y"], filters: [[f, op, v]], ...})."""
    dt = q.get("doctype")
    cols, aliases = [], set()
    fields = q.get("fields") or []
    if isinstance(fields, str):
        fields = [fields]
    for raw in fields:
        expr = " ".join(str(raw).strip().lower().split())
        m = _LEG_AGG.match(expr)
        if m:
            func, distinct, fname, alias = m.groups()
            agg = "count_distinct" if distinct else func
            col = {"field": "*" if fname == "*" else f"{dt}.{fname}", "agg": agg}
            if alias:
                col["alias"] = alias
        else:
            m = _LEG_DATE.match(expr)
            if m:
                part, fname, alias = m.groups()
                col = {"field": f"{dt}.{fname}", "date_part": "day" if part == "date" else part}
                if alias:
                    col["alias"] = alias
            else:
                col = {"field": f"{dt}.{expr}", "alias": expr}
        cols.append(col)
        if col.get("alias"):
            aliases.add(col["alias"])

    filters = q.get("filters") or []
    if isinstance(filters, dict):
        filters = [[k, "=", v] for k, v in filters.items()]
    new_filters = []
    for f in filters:
        if isinstance(f, (list, tuple)) and len(f) == 3:
            new_filters.append({"field": f"{dt}.{str(f[0]).strip().lower()}", "op": f[1], "value": f[2]})
        else:
            new_filters.append(f)

    order = []
    ob = q.get("order_by")
    for part in (ob if isinstance(ob, list) else str(ob or "").split(",")):
        bits = str(part).strip().lower().split()
        if bits and bits[0] in aliases:
            order.append({"column": bits[0], "dir": bits[1] if len(bits) > 1 else "asc"})

    return {"source": dt, "joins": [], "columns": cols, "filters": new_filters, "having": [], "order_by": order, "limit": q.get("limit")}


# --------------------------------------------------------------------------------------
# Compilation
# --------------------------------------------------------------------------------------

class Compiled:
    def __init__(self):
        self.sql = ""
        self.values = {}
        self.columns = []  # [{fieldname, label, fieldtype, kind: sql|formula}]
        self.sql_columns = []
        self.formulas = []  # [(alias, compiled_ast)]
        self.tables = []
        self.limit = 0
        self.source = None


def compile_query(q, catalog, env, max_rows, extra_filters=None):
    """Validate a query spec and build parameterised SQL. Raises QueryError / AccessError."""
    q = normalize_query(q)
    out = Compiled()
    values = {"_nq": 1}  # never empty: keeps %-escaping consistent for the DB driver
    pcount = [0]

    def param(v):
        pcount[0] += 1
        key = f"p{pcount[0]}"
        values[key] = v
        return f"%({key})s"

    # ---------------- tables & joins ----------------
    base = q["source"]
    if not base or base not in catalog:
        raise QueryError(f"'{base}' is not an available data source.")
    out.source = base
    tables = {base: {"kind": "base", "parent": catalog[base].get("parent_doctype"), "tied": False}}
    joins_sql = []

    raw_joins = q["joins"]
    if not isinstance(raw_joins, list) or len(raw_joins) > MAX_JOINS:
        raise QueryError(f"'joins' must be a list of at most {MAX_JOINS} joins.")
    for j in raw_joins:
        if not isinstance(j, dict):
            raise QueryError("Each join must be an object.")
        j = dict(j)
        j.setdefault("from", base)
        opt = _resolve_join(j, tables, catalog, env)
        target, frm = j["doctype"], j["from"]
        jtype = str(j.get("type") or ("left" if opt["kind"] == "link" else "inner")).lower()
        if jtype not in ("left", "inner"):
            raise QueryError("Join type must be 'left' or 'inner'.")
        if opt["kind"] != "link":
            jtype = "inner"  # parent/child joins carry permissions; they are always inner joins
        if opt["kind"] == "link":
            on = f"`tab{target}`.`name` = `tab{frm}`.`{opt['via']}`"
            tables[target] = {"kind": "link", "parent": None, "tied": False}
        elif opt["kind"] == "child":
            on = (
                f"`tab{target}`.`parent` = `tab{frm}`.`name` AND `tab{target}`.`parenttype` = {param(frm)}"
                f" AND `tab{target}`.`parentfield` = {param(opt['via'])}"
            )
            tables[target] = {"kind": "child", "parent": frm, "tied": True}
        else:  # parent
            on = f"`tab{target}`.`name` = `tab{frm}`.`parent` AND `tab{frm}`.`parenttype` = {param(target)}"
            tables[target] = {"kind": "parent", "parent": None, "tied": False}
            tables[frm]["parent"] = target
            tables[frm]["tied"] = True
        joins_sql.append([jtype.upper(), target, on])

    # Child tables are always tied to a parent so the parent's permissions apply.
    for dt, info in list(tables.items()):
        if not env.meta(dt).istable or info.get("tied"):
            continue
        parent = info.get("parent")
        if not parent:
            raise QueryError(f"'{dt}' is a child table; set its Parent DocType in the Data Dictionary.")
        if parent in tables:
            raise QueryError(f"Join '{dt}' to '{parent}' through 'parent' so each line stays with its own document.")
        if parent not in tables:
            tables[parent] = {"kind": "hidden_parent", "parent": None, "tied": False}
            info["tied"] = True
            joins_sql.append(
                ["INNER", parent, f"`tab{parent}`.`name` = `tab{dt}`.`parent` AND `tab{dt}`.`parenttype` = {param(parent)}"]
            )
    out.tables = list(tables)

    # ---------------- permission conditions per table ----------------
    where = []
    join_extra = {}
    for dt, info in tables.items():
        meta = env.meta(dt)
        conds = []
        if not meta.istable:
            if not env.can_read(dt):
                raise AccessError(
                    f"You don't have permission to read {dt}. Ask your administrator for access to {dt} data."
                )
            mc = env.match_conditions(dt)
            if mc:
                conds.append(f"({mc})")
        src = catalog.get(dt)
        if src and src.get("submitted_only") and (meta.is_submittable or meta.istable):
            conds.append(f"`tab{dt}`.`docstatus` = 1")
        elif meta.is_submittable or meta.istable:
            conds.append(f"`tab{dt}`.`docstatus` < 2")
        if dt == base:
            where.extend(conds)
        else:
            join_extra[dt] = conds

    from_sql = f"`tab{base}`"
    for jtype, target, on in joins_sql:
        extra = join_extra.get(target) or []
        from_sql += f" {jtype} JOIN `tab{target}` ON {on}" + "".join(f" AND {c}" for c in extra)

    # ---------------- field resolution ----------------
    permitted_cache = {}

    def resolve(ref, ctx):
        """'DocType.field' (or 'field' on the source) -> (sql, doctype, fieldname, field_meta)."""
        if not isinstance(ref, str) or not ref.strip():
            raise QueryError(f"{ctx}: a field is required.")
        ref = ref.strip()
        dt, _, fname = ref.rpartition(".")
        dt = dt or base
        if dt not in tables or tables[dt]["kind"] == "hidden_parent":
            raise QueryError(f"{ctx}: '{dt}' is not part of the query. Add a join first.")
        if not RE_FIELD.match(fname):
            raise QueryError(f"{ctx}: invalid field name '{fname}'.")
        allowed = catalog[dt]["fields"]
        if fname not in allowed and fname != "name":
            raise QueryError(f"{ctx}: '{dt}.{fname}' is not available in the Data Dictionary.")
        if fname not in STANDARD_FIELDS:
            key = dt
            if key not in permitted_cache:
                permitted_cache[key] = env.permitted_fields(dt, tables[dt].get("parent") if env.meta(dt).istable else None)
            if fname not in permitted_cache[key]:
                raise AccessError(f"You don't have permission to see the field '{allowed[fname]['label']}' of {dt}.")
        fmeta = allowed.get(fname) or {"label": STANDARD_FIELDS["name"][0], "fieldtype": "Data"}
        return f"`tab{dt}`.`{fname}`", dt, fname, fmeta

    # ---------------- columns ----------------
    cols = q["columns"]
    if not isinstance(cols, list) or not cols:
        raise QueryError("Add at least one column.")
    if len(cols) > MAX_COLUMNS:
        raise QueryError(f"At most {MAX_COLUMNS} columns.")

    aliases, select, group_exprs, has_agg = {}, [], [], False
    date_group = False
    agg_aliases, group_aliases = [], []
    for i, c in enumerate(cols, start=1):
        if not isinstance(c, dict):
            raise QueryError(f"Column {i} must be an object.")
        if c.get("formula"):
            alias = _alias(c.get("alias") or f"formula_{i}", aliases)
            tree = _compile_formula(c["formula"], set(aliases))
            label = str(c.get("label") or alias.replace("_", " ").title())[:140]
            aliases[alias] = {"fieldname": alias, "label": label, "fieldtype": "Float", "kind": "formula"}
            out.formulas.append((alias, tree))
            continue

        agg = (c.get("agg") or "").lower() or None
        part = (c.get("date_part") or "").lower() or None
        if agg and agg not in AGGS:
            raise QueryError(f"Column {i}: aggregate must be one of {', '.join(AGGS)}.")
        if part and part not in DATE_PARTS:
            raise QueryError(f"Column {i}: date part must be one of {', '.join(DATE_PARTS)}.")

        if c.get("field") == "*":
            if agg != "count":
                raise QueryError(f"Column {i}: '*' is only allowed with count.")
            expr, fname, fmeta = "COUNT(*)", "rows", {"label": "Count", "fieldtype": "Int"}
            dt = base
        else:
            expr, dt, fname, fmeta = resolve(c.get("field"), f"Column {i}")
            ftype = fmeta["fieldtype"]
            if part:
                if ftype not in DATE_TYPES:
                    raise QueryError(f"Column {i}: date part needs a Date/Datetime field; '{fname}' is {ftype}.")
                expr = _date_expr(expr, part)
            if agg in ("sum", "avg") and ftype not in NUMERIC:
                raise QueryError(f"Column {i}: {agg} needs a numeric field; '{fname}' is {ftype}.")
            if agg:
                expr = {
                    "sum": f"SUM({expr})", "avg": f"AVG({expr})", "min": f"MIN({expr})", "max": f"MAX({expr})",
                    "count": f"COUNT({expr})", "count_distinct": f"COUNT(DISTINCT {expr})",
                }[agg]

        default_alias = "_".join(x for x in (agg, part, fname) if x)
        alias = _alias(c.get("alias") or default_alias, aliases)
        if agg in ("count", "count_distinct"):
            out_type = "Int"
        elif agg == "avg":
            out_type = "Currency" if fmeta["fieldtype"] == "Currency" else "Float"
        elif part:
            out_type = "Date" if part == "day" else ("Int" if part in ("year", "quarter", "month", "week") else "Data")
        else:
            out_type = fmeta["fieldtype"]
        label = c.get("label") or _default_label(fmeta["label"], agg, part)
        if len(tables) > 1 and not c.get("label") and dt != base and not agg:
            label = f"{label} ({dt})"
        aliases[alias] = {"fieldname": alias, "label": str(label)[:140], "fieldtype": out_type, "kind": "sql"}
        select.append(f"{expr} AS `{alias}`")
        out.sql_columns.append(alias)
        if agg:
            has_agg = True
            agg_aliases.append(alias)
        else:
            group_exprs.append(expr)
            group_aliases.append(alias)
            date_group = date_group or bool(part)

    out.columns = list(aliases.values())
    if not select:
        raise QueryError("Add at least one data column (formulas need other columns).")

    # ---------------- filters ----------------
    if not isinstance(q["filters"], list):
        raise QueryError("'filters' must be a list.")
    filters = list(q["filters"])
    extra_filters = [f for f in (extra_filters or []) if isinstance(f, dict)]
    if extra_filters:
        replaced = {f.get("field") for f in extra_filters if f.get("replace")}
        filters = [f for f in filters if not (isinstance(f, dict) and f.get("field") in replaced)]
    if len(filters) + len(extra_filters) > MAX_FILTERS:
        raise QueryError(f"At most {MAX_FILTERS} filters.")
    for i, f in enumerate(filters, start=1):
        where.append(_filter_sql(f, resolve, param, f"Filter {i}"))
    for f in extra_filters:  # dashboard filters: skipped when the field is not in this query
        try:
            where.append(_filter_sql(f, resolve, param, "Dashboard filter"))
        except (QueryError, AccessError):
            continue

    # ---------------- group / having / order / limit ----------------
    sql = "SELECT " + ", ".join(select) + " FROM " + from_sql
    if where:
        sql += " WHERE " + " AND ".join(where)
    if has_agg and group_exprs:
        sql += " GROUP BY " + ", ".join(group_exprs)

    having = q["having"]
    if having:
        if not has_agg:
            raise QueryError("Summary filters (having) need at least one aggregated column.")
        parts = []
        if not isinstance(having, list):
            raise QueryError("'having' must be a list.")
        for i, h in enumerate(having, start=1):
            if not isinstance(h, dict):
                raise QueryError(f"Summary filter {i} must be an object.")
            col = h.get("column")
            if col not in aliases or aliases[col]["kind"] != "sql":
                raise QueryError(f"Summary filter {i}: '{col}' is not a column of this query.")
            op = str(h.get("op") or "=").lower()
            if op not in ("=", "!=", ">", "<", ">=", "<=", "between"):
                raise QueryError(f"Summary filter {i}: operator '{op}' is not allowed.")
            v = h.get("value")
            if op == "between":
                if not (isinstance(v, list) and len(v) == 2):
                    raise QueryError(f"Summary filter {i}: between needs [from, to].")
                parts.append(f"`{col}` BETWEEN {param(_num(v[0]))} AND {param(_num(v[1]))}")
            else:
                parts.append(f"`{col}` {op} {param(_num(v))}")
        sql += " HAVING " + " AND ".join(parts)

    order = q["order_by"]
    if isinstance(order, (str, dict)):
        order = [order]
    terms = []
    for o in order or []:
        if isinstance(o, str):
            bits = o.strip().split()
            o = {"column": bits[0] if bits else "", "dir": bits[1] if len(bits) > 1 else "asc"}
        if not isinstance(o, dict):
            raise QueryError("Each sort entry must be an object with column and dir.")
        col, direction = o.get("column"), str(o.get("dir") or "asc").lower()
        if col not in aliases:
            raise QueryError(f"Sort column '{col}' is not a column of this query.")
        if aliases[col]["kind"] != "sql":
            raise QueryError(f"Cannot sort by calculated column '{col}'.")
        if direction not in ("asc", "desc"):
            raise QueryError("Sort direction must be asc or desc.")
        terms.append(f"`{col}` {direction}")
    if len(terms) > 4:
        raise QueryError("Sort by at most 4 columns.")
    if not terms:
        if has_agg and date_group:
            terms = [f"`{a}` asc" for a in group_aliases[:4]]
        elif has_agg and group_aliases:
            terms = [f"`{agg_aliases[0]}` desc"]
        elif not has_agg:
            terms = [f"`tab{base}`.`modified` desc"]
    if terms:
        sql += " ORDER BY " + ", ".join(terms)

    try:
        limit = int(q.get("limit") or max_rows)
    except (TypeError, ValueError):
        raise QueryError("Limit must be a number.")
    out.limit = max(1, min(limit, max_rows))
    sql += f" LIMIT {out.limit}"

    out.sql = sql
    out.values = values
    return out


def _alias(alias, existing):
    alias = re.sub(r"[^a-z0-9_]", "_", str(alias).strip().lower())[:60] or "col"
    if alias[0].isdigit():
        alias = f"c_{alias}"
    if not RE_ALIAS.match(alias):
        raise QueryError(f"Invalid column alias '{alias}'.")
    base, n = alias, 2
    while alias in existing:
        alias = f"{base}_{n}"
        n += 1
    return alias


def _default_label(label, agg, part):
    label = label or ""
    if part:
        label = f"{label} ({part.replace('_', ' ').title()})"
    if agg:
        name = "Distinct Count" if agg == "count_distinct" else agg.title()
        label = f"{name} of {label}".strip()
    return label


def _date_expr(expr, part):
    return {
        "year": f"YEAR({expr})",
        "quarter": f"QUARTER({expr})",
        "month": f"MONTH({expr})",
        "week": f"WEEK({expr}, 3)",
        "day": f"DATE({expr})",
        "year_quarter": f"CONCAT(YEAR({expr}), '-Q', QUARTER({expr}))",
        "year_month": f"CONCAT(YEAR({expr}), '-', LPAD(MONTH({expr}), 2, '0'))",
        "year_week": f"CONCAT(LEFT(YEARWEEK({expr}, 3), 4), '-W', LPAD(WEEK({expr}, 3), 2, '0'))",
    }[part]


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise QueryError("Summary filter values must be numbers.")
    try:
        return float(v)
    except ValueError:
        raise QueryError(f"'{v}' is not a number.")


def _scalar(v, ctx):
    if v is None or isinstance(v, (str, int, float, bool)):
        if isinstance(v, str) and len(v) > 500:
            raise QueryError(f"{ctx}: value too long.")
        return v
    raise QueryError(f"{ctx}: values must be plain text or numbers.")


def _filter_sql(f, resolve, param, ctx):
    if isinstance(f, (list, tuple)) and len(f) == 3:
        f = {"field": f[0], "op": f[1], "value": f[2]}
    if not isinstance(f, dict):
        raise QueryError(f"{ctx}: must be an object with field, op and value.")
    expr, dt, fname, fmeta = resolve(f.get("field"), ctx)
    op = " ".join(str(f.get("op") or "=").lower().split())
    v = f.get("value")
    if op not in OPS:
        raise QueryError(f"{ctx}: operator '{op}' is not allowed. Use one of: {', '.join(OPS)}.")

    if op in ("in", "not in"):
        if isinstance(v, str):
            v = [x.strip() for x in v.split(",") if x.strip()]
        if not isinstance(v, list) or not v or len(v) > MAX_IN_VALUES:
            raise QueryError(f"{ctx}: '{op}' needs a list of 1-{MAX_IN_VALUES} values.")
        placeholders = ", ".join(param(_scalar(x, ctx)) for x in v)
        return f"{expr} {op.upper()} ({placeholders})"
    if op == "between":
        if not (isinstance(v, list) and len(v) == 2):
            raise QueryError(f"{ctx}: 'between' needs [from, to].")
        if fmeta["fieldtype"] == "Datetime":
            return f"{expr} >= {param(_scalar(v[0], ctx))} AND {expr} < DATE_ADD({param(_scalar(v[1], ctx))}, INTERVAL 1 DAY)"
        return f"{expr} BETWEEN {param(_scalar(v[0], ctx))} AND {param(_scalar(v[1], ctx))}"
    if op == "is":
        if v == "set":
            return f"({expr} IS NOT NULL AND {expr} != '')"
        if v == "not set":
            return f"({expr} IS NULL OR {expr} = '')"
        raise QueryError(f"{ctx}: 'is' accepts 'set' or 'not set'.")
    if op == "timespan":
        if fmeta["fieldtype"] not in DATE_TYPES:
            raise QueryError(f"{ctx}: timespan needs a Date/Datetime field.")
        rng = timespan_range(str(v or "").lower())
        if not rng:
            raise QueryError(f"{ctx}: timespan must be one of: {', '.join(TIMESPANS)}.")
        start, end = rng
        return f"{expr} >= {param(str(start))} AND {expr} < {param(str(end + datetime.timedelta(days=1)))}"
    if op in ("like", "not like"):
        v = str(_scalar(v, ctx) or "")
        if "%" not in v and "_" not in v:
            v = f"%{v}%"
        return f"{expr} {op.upper()} {param(v)}"
    return f"{expr} {op} {param(_scalar(v, ctx))}"


def timespan_range(span, today=None):
    """(start_date, end_date) inclusive for a named period. Weeks start on Monday."""
    t = today or datetime.date.today()

    def month_start(d):
        return d.replace(day=1)

    def add_months(d, n):
        m = d.month - 1 + n
        y = d.year + m // 12
        m = m % 12 + 1
        return datetime.date(y, m, 1)

    def month_end(d):
        return add_months(d, 1) - datetime.timedelta(days=1)

    def quarter_start(d):
        return datetime.date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)

    week_start = t - datetime.timedelta(days=t.weekday())
    q0 = quarter_start(t)
    table = {
        "today": (t, t),
        "yesterday": (t - datetime.timedelta(days=1),) * 2,
        "tomorrow": (t + datetime.timedelta(days=1),) * 2,
        "this week": (week_start, week_start + datetime.timedelta(days=6)),
        "last week": (week_start - datetime.timedelta(days=7), week_start - datetime.timedelta(days=1)),
        "next week": (week_start + datetime.timedelta(days=7), week_start + datetime.timedelta(days=13)),
        "this month": (month_start(t), month_end(t)),
        "last month": (add_months(t, -1), month_start(t) - datetime.timedelta(days=1)),
        "next month": (add_months(t, 1), month_end(add_months(t, 1))),
        "this quarter": (q0, add_months(q0, 3) - datetime.timedelta(days=1)),
        "last quarter": (add_months(q0, -3), q0 - datetime.timedelta(days=1)),
        "next quarter": (add_months(q0, 3), add_months(q0, 6) - datetime.timedelta(days=1)),
        "this year": (datetime.date(t.year, 1, 1), datetime.date(t.year, 12, 31)),
        "last year": (datetime.date(t.year - 1, 1, 1), datetime.date(t.year - 1, 12, 31)),
        "next year": (datetime.date(t.year + 1, 1, 1), datetime.date(t.year + 1, 12, 31)),
        "last 7 days": (t - datetime.timedelta(days=6), t),
        "last 30 days": (t - datetime.timedelta(days=29), t),
        "last 90 days": (t - datetime.timedelta(days=89), t),
        "last 6 months": (add_months(t, -6), t),
        "last 12 months": (add_months(t, -12), t),
        "year to date": (datetime.date(t.year, 1, 1), t),
        "month to date": (month_start(t), t),
    }
    return table.get(span)


# --------------------------------------------------------------------------------------
# Formulas (calculated columns, evaluated in Python after the query)
# --------------------------------------------------------------------------------------

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Call,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.USub, ast.UAdd,
)
_FUNCS = {"round": round, "abs": abs, "min": min, "max": max}


def _compile_formula(text, known):
    text = str(text).strip()
    if len(text) > 300:
        raise QueryError("Formula is too long.")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        raise QueryError(f"Formula '{text}' is not valid. Use column names, numbers and + - * / ( ).")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise QueryError(f"Formula '{text}': only arithmetic, round(), abs(), min(), max() are allowed.")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in _FUNCS):
            raise QueryError(f"Formula '{text}': only round(), abs(), min(), max() are allowed.")
        if isinstance(node, ast.Name) and node.id not in _FUNCS and node.id not in known:
            raise QueryError(f"Formula '{text}': unknown column '{node.id}'. Use aliases of earlier columns.")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise QueryError(f"Formula '{text}': only numbers are allowed as constants.")
            if abs(node.value) > 1e15:
                raise QueryError(f"Formula '{text}': numbers must be below 10^15.")
    return compile(tree, "<formula>", "eval")


def _eval_formula(code, row):
    # Only numbers reach the formula; text/dates become None, so no string repetition or big-int maths.
    env = {k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None) for k, v in row.items()}
    try:
        result = eval(code, {"__builtins__": {}}, {**_FUNCS, **env})  # noqa: S307 - AST validated above
    except (ZeroDivisionError, TypeError, ValueError, OverflowError, MemoryError):
        return None
    return round(result, 6) if isinstance(result, float) else result


# --------------------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------------------

def run(q, catalog=None, env=None, max_rows=None, extra_filters=None):
    """Compile and execute. Returns {columns, rows, truncated, row_count, source, tables}."""
    from decimal import Decimal

    env = env or FrappeEnv()
    catalog = catalog if catalog is not None else get_full_catalog()
    max_rows = max_rows or _max_rows()
    c = compile_query(q, catalog, env, max_rows, extra_filters=extra_filters)

    sql = c.sql
    if frappe.db.db_type == "mariadb":
        sql = f"SET STATEMENT max_statement_time={QUERY_TIMEOUT_SECONDS} FOR {sql}"
    raw = frappe.db.sql(sql, c.values, as_list=True)

    rows = []
    for r in raw:
        rec = {}
        for alias, v in zip(c.sql_columns, r):
            if isinstance(v, Decimal):
                v = float(v)
            elif isinstance(v, (datetime.date, datetime.datetime, datetime.timedelta)):
                v = str(v)
            rec[alias] = v
        for alias, code in c.formulas:
            rec[alias] = _eval_formula(code, rec)
        rows.append([rec.get(col["fieldname"]) for col in c.columns])

    return {
        "columns": [{k: col[k] for k in ("fieldname", "label", "fieldtype")} for col in c.columns],
        "rows": rows,
        "row_count": len(rows),
        "truncated": len(rows) >= c.limit,
        "source": c.source,
        "tables": c.tables,
    }


def get_full_catalog():
    from neotec_ai.query_engine import get_catalog

    return get_catalog(check_permissions=False)


def user_catalog(env=None):
    """Catalog entries the current user can read (used for the AI prompt and the builder)."""
    env = env or FrappeEnv()
    full = get_full_catalog()
    out = {}
    for dt, src in full.items():
        perm_dt = src.get("parent_doctype") or dt
        try:
            if env.can_read(perm_dt):
                out[dt] = src
        except Exception:
            continue
    return out


def _max_rows():
    return max(10, min(cint(frappe.db.get_single_value("Neotec Settings", "max_report_rows")) or 500, 5000))


# --------------------------------------------------------------------------------------
# Pivot (applied to query results)
# --------------------------------------------------------------------------------------

def pivot(result, cfg, max_columns=60):
    cols = {c["fieldname"]: i for i, c in enumerate(result["columns"])}
    labels = {c["fieldname"]: c["label"] for c in result["columns"]}
    rows_by = cfg.get("rows") or []
    col_by = cfg.get("columns")
    val = cfg.get("values")
    agg = (cfg.get("agg") or "sum").lower()
    if not rows_by or any(r not in cols for r in rows_by) or col_by not in cols or val not in cols:
        raise QueryError("Pivot needs row column(s), a column field and a value column from the results.")
    if agg not in ("sum", "count", "avg", "min", "max"):
        raise QueryError("Pivot aggregate must be sum, count, avg, min or max.")

    col_values, buckets, order = [], {}, []
    for r in result["rows"]:
        rk = tuple(r[cols[x]] for x in rows_by)
        ck = r[cols[col_by]]
        ck = "" if ck is None else str(ck)
        if ck not in col_values:
            col_values.append(ck)
            if len(col_values) > max_columns:
                raise QueryError(f"Pivot would create more than {max_columns} columns; filter the data first.")
        if rk not in buckets:
            buckets[rk] = {}
            order.append(rk)
        buckets[rk].setdefault(ck, []).append(r[cols[val]])

    col_values.sort()

    def reduce(vals):
        nums = [float(v) for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if agg == "count":
            return len(vals)
        if not nums:
            return None
        return {"sum": sum(nums), "avg": sum(nums) / len(nums), "min": min(nums), "max": max(nums)}[agg]

    out_cols = [{"fieldname": f"r_{i}", "label": labels[x], "fieldtype": "Data"} for i, x in enumerate(rows_by)]
    out_cols += [{"fieldname": f"c_{i}", "label": v or "(blank)", "fieldtype": "Float"} for i, v in enumerate(col_values)]
    with_total = agg in ("sum", "count")
    if with_total:
        out_cols.append({"fieldname": "total", "label": "Total", "fieldtype": "Float"})

    out_rows = []
    for rk in order:
        cells = [reduce(buckets[rk][cv]) if cv in buckets[rk] else None for cv in col_values]
        row = list(rk) + cells
        if with_total:
            row.append(sum(x for x in cells if x is not None))
        out_rows.append(row)
    if with_total and out_rows:
        n = len(rows_by)
        totals = ["Total"] + [""] * (n - 1)
        for j in range(len(col_values) + 1):
            totals.append(sum((r[n + j] or 0) for r in out_rows))
        out_rows.append(totals)
    return {"columns": out_cols, "rows": out_rows}
