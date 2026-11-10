# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Helpers shared by tools. Every data helper respects the calling user's permissions."""

from __future__ import annotations

import json
import re

import frappe
from frappe import _

NO_VALUE_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading",
                  "Image", "Password"}
STANDARD_FIELDS = ["name", "owner", "creation", "modified", "modified_by", "docstatus"]
BLOCKED_DOCTYPES = {"OAuth Bearer Token", "OAuth Authorization Code", "Session Default Settings",
                    "Coworker Provider", "Coworker MCP Server", "User Social Login"}
_ORDER = re.compile(r"^`?([a-z_][a-z0-9_]*)`?(\s+(asc|desc))?$", re.I)


def jarg(value, default=None):
    """Tool arguments may arrive as JSON strings (portable across providers) or as objects."""
    if value is None or value == "":
        return default
    if isinstance(value, str):
        s = value.strip()
        if s[:1] in "[{":
            try:
                return json.loads(s)
            except ValueError:
                frappe.throw(_("Could not read JSON: {0}").format(s[:200]))
        if default is not None and isinstance(default, list):
            return [p.strip() for p in s.split(",") if p.strip()]
        return s
    return value


def ensure_doctype(doctype: str, ptype: str = "read"):
    if not doctype or not isinstance(doctype, str):
        frappe.throw(_("A DocType name is required."))
    if not frappe.db.exists("DocType", doctype):
        frappe.throw(_("There is no DocType called {0}. Use describe_doctype or global_search to find the right one.").format(doctype))
    if doctype in BLOCKED_DOCTYPES:
        raise frappe.PermissionError(_("{0} is not available to coworkers.").format(doctype))
    if not frappe.has_permission(doctype, ptype):
        raise frappe.PermissionError(_("You do not have {0} access to {1}.").format(ptype, doctype))
    return frappe.get_meta(doctype)


def readable_fieldnames(meta) -> set[str]:
    names = None
    try:
        names = set(meta.get_permitted_fieldnames(user=frappe.session.user, permission_type="read"))
    except Exception:  # noqa: BLE001 - older signature
        try:
            names = set(meta.get_permitted_fieldnames())
        except Exception:  # noqa: BLE001
            names = None
    if names is None:
        names = {df.fieldname for df in meta.fields if (df.permlevel or 0) == 0}
    blocked = {df.fieldname for df in meta.fields if df.fieldtype in NO_VALUE_TYPES}
    return (names - blocked) | set(STANDARD_FIELDS)


def parse_filters(filters):
    filters = jarg(filters, {})
    if filters in (None, "", {}):
        return {}
    if isinstance(filters, dict):
        return filters
    if isinstance(filters, list):
        return [f for f in filters if isinstance(f, (list, tuple))]
    frappe.throw(_("Filters must be an object like {\"status\": \"Unpaid\"} or a list like [[\"grand_total\", \">\", 1000]]."))


def filter_fields(filters) -> set[str]:
    if isinstance(filters, dict):
        return set(filters)
    out = set()
    for f in filters or []:
        if len(f) == 3 and isinstance(f[0], str):
            out.add(f[0])
    return out


def check_fields(meta, fields, allowed=None):
    allowed = allowed or readable_fieldnames(meta)
    bad = [f for f in fields if f not in allowed]
    if bad:
        frappe.throw(_("Unknown or not permitted fields on {0}: {1}. Use describe_doctype.").format(
            meta.name, ", ".join(bad[:8])))


def safe_order(order_by, meta, allowed=None):
    if not order_by:
        return None
    m = _ORDER.match(str(order_by).strip())
    if not m:
        frappe.throw(_("order_by must look like 'fieldname desc'."))
    check_fields(meta, [m.group(1)], allowed)
    return f"{m.group(1)} {(m.group(3) or 'asc').lower()}"


def default_fields(meta) -> list[str]:
    fields = ["name"]
    if meta.title_field and meta.title_field != "name":
        fields.append(meta.title_field)
    for df in meta.fields:
        if df.in_list_view and df.fieldtype not in NO_VALUE_TYPES and df.fieldtype not in ("Table", "Table MultiSelect"):
            fields.append(df.fieldname)
    if meta.is_submittable:
        fields.append("docstatus")
    fields.append("modified")
    seen = []
    for f in fields:
        if f not in seen:
            seen.append(f)
    return seen[:12]


def permitted_companies() -> list[str]:
    return frappe.get_list("Company", pluck="name", limit_page_length=500)


def company_filter(company=None) -> list[str]:
    companies = permitted_companies()
    if company:
        if company not in companies:
            raise frappe.PermissionError(_("You do not have access to company {0}.").format(company))
        return [company]
    return companies


def plain(value):
    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def compact_row(row: dict) -> dict:
    return {k: plain(v) for k, v in row.items() if v is not None and v != ""}
