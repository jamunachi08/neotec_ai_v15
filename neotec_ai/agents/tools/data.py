# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Generic, permission-respecting read tools over any DocType and report."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, strip_html

from neotec_ai.agents.engine.registry import tool
from neotec_ai.agents.tools._common import (
    NO_VALUE_TYPES, check_fields, compact_row, default_fields, ensure_doctype, filter_fields, jarg,
    parse_filters, readable_fieldnames, safe_order,
)

S = {"type": "string"}
I = {"type": "integer"}
FILTERS = {"type": "string", "description": 'JSON. Object {"status":"Overdue"} or list [["grand_total",">",1000],["posting_date","between",["2026-01-01","2026-03-31"]]].'}


@tool("describe_doctype", "Describe a DocType",
      "List the fields of an ERPNext DocType (fieldname, label, type, options) that the user can read. "
      "Call this before filtering or aggregating on a DocType you have not used yet.",
      {"doctype": S, "__required__": ["doctype"]})
def describe_doctype(doctype):
    meta = ensure_doctype(doctype)
    allowed = readable_fieldnames(meta)
    fields = []
    for df in meta.fields:
        if df.fieldname not in allowed or df.fieldtype in NO_VALUE_TYPES:
            continue
        row = {"fieldname": df.fieldname, "label": df.label, "type": df.fieldtype}
        if df.options and df.fieldtype in ("Link", "Select", "Table", "Dynamic Link", "Table MultiSelect"):
            row["options"] = df.options[:200]
        if df.reqd:
            row["required"] = 1
        fields.append(row)
    return {"doctype": doctype, "module": meta.module, "is_submittable": cint(meta.is_submittable),
            "is_child_table": cint(meta.istable), "title_field": meta.title_field or "name",
            "fields": fields[:120]}


@tool("search_documents", "Search documents",
      "Find records of one DocType with filters. Returns at most `limit` rows (max 100). "
      "Respects the user's permissions. Use fields to choose columns.",
      {"doctype": S, "filters": FILTERS,
       "fields": {"type": "string", "description": "Comma separated fieldnames. Optional."},
       "search_text": {"type": "string", "description": "Matches name or title. Optional."},
       "order_by": {"type": "string", "description": "e.g. 'posting_date desc'"},
       "limit": I, "__required__": ["doctype"]})
def search_documents(doctype, filters=None, fields=None, search_text=None, order_by=None, limit=20):
    meta = ensure_doctype(doctype)
    allowed = readable_fieldnames(meta)
    fields = jarg(fields, []) or default_fields(meta)
    if isinstance(fields, str):
        fields = [f.strip() for f in fields.split(",") if f.strip()]
    check_fields(meta, fields, allowed)
    filters = parse_filters(filters)
    check_fields(meta, sorted(filter_fields(filters)), allowed)
    or_filters = None
    if search_text:
        like = f"%{search_text}%"
        or_filters = [[doctype, "name", "like", like]]
        if meta.title_field and meta.title_field in allowed:
            or_filters.append([doctype, meta.title_field, "like", like])
    limit = max(1, min(cint(limit) or 20, 100))
    rows = frappe.get_list(doctype, filters=filters, or_filters=or_filters, fields=fields,
                           order_by=safe_order(order_by, meta, allowed) or "modified desc",
                           limit_page_length=limit)
    return {"doctype": doctype, "rows": [compact_row(r) for r in rows], "count": len(rows),
            "more_available": len(rows) == limit}


@tool("get_document", "Open a document",
      "Read one document with its child tables (max 50 rows each). Respects field-level permissions.",
      {"doctype": S, "name": S, "__required__": ["doctype", "name"]})
def get_document(doctype, name):
    meta = ensure_doctype(doctype)
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    try:
        doc.apply_fieldlevel_read_permissions()
    except Exception:  # noqa: BLE001 - older versions
        pass
    out = {"doctype": doctype, "name": doc.name}
    if meta.is_submittable:
        out["docstatus"] = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(doc.docstatus)
    for df in meta.fields:
        if df.fieldtype in NO_VALUE_TYPES:
            continue
        val = doc.get(df.fieldname)
        if val in (None, "", []):
            continue
        if df.fieldtype in ("Table", "Table MultiSelect"):
            child_meta = frappe.get_meta(df.options)
            rows = []
            for r in val[:50]:
                row = {}
                for cdf in child_meta.fields:
                    if cdf.fieldtype in NO_VALUE_TYPES or cdf.fieldtype in ("Table",):
                        continue
                    v = r.get(cdf.fieldname)
                    if v not in (None, ""):
                        row[cdf.fieldname] = strip_html(str(v))[:300] if cdf.fieldtype in ("Text Editor", "HTML Editor") else v
                rows.append(row)
            out[df.fieldname] = {"rows": rows, "total_rows": len(val)}
        elif df.fieldtype in ("Text Editor", "HTML Editor", "Long Text", "Code"):
            out[df.fieldname] = strip_html(str(val))[:2000]
        else:
            out[df.fieldname] = val if isinstance(val, (int, float, str)) else str(val)
    return out


@tool("count_documents", "Count documents",
      "Count records of a DocType that match filters, respecting permissions.",
      {"doctype": S, "filters": FILTERS, "__required__": ["doctype"]})
def count_documents(doctype, filters=None):
    ensure_doctype(doctype)
    from frappe.client import get_count

    return {"doctype": doctype, "count": get_count(doctype, filters=parse_filters(filters) or None)}


def _bucket(value, bucket):
    d = getdate(value) if value else None
    if not d:
        return "(blank)"
    if bucket == "month":
        return d.strftime("%Y-%m")
    if bucket == "quarter":
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    if bucket == "year":
        return str(d.year)
    if bucket == "day":
        return d.isoformat()
    return d.isoformat()


@tool("aggregate", "Group and total",
      "Group records of a DocType and compute sum/avg/count/min/max of a numeric field. "
      "For date fields set date_bucket to day, month, quarter or year. Good for charts.",
      {"doctype": S, "group_by": S,
       "value_field": {"type": "string", "description": "Numeric field. Omit for counts."},
       "function": {"type": "string", "enum": ["sum", "avg", "count", "min", "max"]},
       "filters": FILTERS,
       "date_bucket": {"type": "string", "enum": ["", "day", "month", "quarter", "year"]},
       "limit": I, "__required__": ["doctype", "group_by"]})
def aggregate(doctype, group_by, value_field=None, function="sum", filters=None, date_bucket=None, limit=20):
    meta = ensure_doctype(doctype)
    allowed = readable_fieldnames(meta)
    fields = [group_by] + ([value_field] if value_field else [])
    check_fields(meta, fields, allowed)
    function = (function or "sum").lower()
    if not value_field:
        function = "count"
    rows = frappe.get_list(doctype, filters=parse_filters(filters), fields=fields, limit_page_length=50000,
                           order_by="modified desc")
    groups = defaultdict(list)
    df = meta.get_field(group_by)
    is_date = bool(df and df.fieldtype in ("Date", "Datetime")) or group_by in ("creation", "modified")
    for r in rows:
        key = _bucket(r.get(group_by), date_bucket or "day") if is_date else (r.get(group_by) or "(blank)")
        groups[str(key)].append(flt(r.get(value_field)) if value_field else 1)

    def agg(vals):
        if function == "count":
            return len(vals)
        if function == "avg":
            return round(sum(vals) / len(vals), 2) if vals else 0
        if function == "min":
            return min(vals)
        if function == "max":
            return max(vals)
        return round(sum(vals), 2)

    result = [{"group": k, "value": agg(v), "records": len(v)} for k, v in groups.items()]
    if is_date:
        result.sort(key=lambda x: x["group"])
    else:
        result.sort(key=lambda x: x["value"], reverse=True)
    limit = max(1, min(cint(limit) or 20, 200))
    return {"doctype": doctype, "group_by": group_by, "function": function, "value_field": value_field,
            "groups": result[:limit], "total_groups": len(result), "records_scanned": len(rows),
            "truncated_scan": len(rows) >= 50000}


@tool("list_reports", "Find reports",
      "Find ERPNext reports by name or DocType (e.g. 'Accounts Receivable', 'General Ledger', 'Stock Balance').",
      {"query": S, "__required__": ["query"]})
def list_reports(query):
    like = f"%{query}%"
    rows = frappe.get_list("Report", filters={"disabled": 0},
                           or_filters=[["name", "like", like], ["ref_doctype", "like", like]],
                           fields=["name", "ref_doctype", "report_type", "module"], limit_page_length=25)
    return {"reports": rows}


@tool("run_report", "Run a report",
      "Run a Query or Script report (e.g. 'Accounts Receivable', 'Trial Balance', 'Stock Balance') with filters "
      "and return its columns and the first 100 rows. Check the report's filters with list_reports first if unsure.",
      {"report_name": S, "filters": {"type": "string", "description": 'JSON object of report filters, e.g. {"company":"X","report_date":"2026-10-28"}'},
       "__required__": ["report_name"]})
def run_report(report_name, filters=None):
    from frappe.desk.query_report import run

    filters = jarg(filters, {}) or {}
    if not isinstance(filters, dict):
        frappe.throw(_("Report filters must be a JSON object."))
    if "company" not in filters:
        company = frappe.defaults.get_user_default("Company")
        if company:
            filters["company"] = company
    data = run(report_name, filters=filters, ignore_prepared_report=False)
    if data.get("prepared_report"):
        return {"report": report_name, "note": "This report runs in the background. Ask the user to open it in ERPNext."}
    columns = []
    for c in data.get("columns") or []:
        if isinstance(c, dict):
            columns.append({"fieldname": c.get("fieldname"), "label": c.get("label")})
        else:
            parts = str(c).split(":")
            columns.append({"fieldname": frappe.scrub(parts[0]), "label": parts[0]})
    rows = []
    for r in (data.get("result") or [])[:100]:
        if isinstance(r, dict):
            rows.append({c["fieldname"]: r.get(c["fieldname"]) for c in columns if r.get(c["fieldname"]) not in (None, "")})
        elif isinstance(r, (list, tuple)):
            rows.append({columns[i]["fieldname"]: v for i, v in enumerate(r) if i < len(columns) and v not in (None, "")})
    return {"report": report_name, "filters": filters, "columns": columns, "rows": rows,
            "total_rows": len(data.get("result") or []), "truncated": len(data.get("result") or []) > 100}


@tool("global_search", "Search everything",
      "Full-text search across documents the user can read. Use when you do not know the DocType.",
      {"text": S, "limit": I, "__required__": ["text"]})
def global_search(text, limit=10):
    from frappe.utils.global_search import search

    from neotec_ai.agents.engine.gateway import sensitive_doctypes

    external = bool(frappe.flags.get("ntc_external"))
    hidden = sensitive_doctypes() if external else set()
    out = []
    for r in search(text, start=0, limit=min(cint(limit) or 10, 30) * 2):
        dt, dn = r.get("doctype"), r.get("name")
        if dt in hidden or not frappe.has_permission(dt, "read", dn):
            continue
        out.append({"doctype": dt, "name": dn, "match": strip_html(r.get("content") or "")[:240]})
        if len(out) >= (cint(limit) or 10):
            break
    return {"results": out}


@tool("current_user", "Who am I",
      "The current user's name, roles, default company, currency and today's date.", {})
def current_user():
    from frappe.utils import nowdate

    company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
    currency = frappe.db.get_value("Company", company, "default_currency") if company else None
    return {"user": frappe.session.user, "full_name": frappe.utils.get_fullname(frappe.session.user),
            "roles": [r for r in frappe.get_roles() if r not in ("All", "Guest")][:40],
            "company": company, "currency": currency, "today": nowdate()}
