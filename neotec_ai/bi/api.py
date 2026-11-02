"""Endpoints for the BI Builder and Dashboards."""

import json
import time

import frappe
from frappe import _
from frappe.utils import cint, formatdate, nowdate

from neotec_ai import llm, reports
from neotec_ai.bi import engine, export
from neotec_ai.bi import prompt as bi_prompt
from neotec_ai.bi import viz as vizlib
from neotec_ai.query_engine import PlanError, describe_catalog

WIDTHS = ("3", "4", "6", "8", "12")
HEIGHTS = ("Small", "Medium", "Large")
DATE_FIELD_PREFERENCE = ("posting_date", "transaction_date", "date", "attendance_date", "opening_date", "creation")


def _check_access():
    from neotec_ai.api import _check_access as check

    check()


def _not_permitted(msg):
    frappe.throw(msg, frappe.PermissionError, title=_("Not Permitted"))


def _load(value, default=None):
    if isinstance(value, str):
        try:
            return json.loads(value) if value else default
        except ValueError:
            frappe.throw(_("Invalid JSON input."))
    return value if value is not None else default


# --------------------------------------------------------------------------------------
# Builder
# --------------------------------------------------------------------------------------

@frappe.whitelist()
def get_builder_meta():
    _check_access()
    env = engine.FrappeEnv()
    catalog = engine.user_catalog(env)
    sources = []
    for dt, src in sorted(catalog.items()):
        fields = [
            {"fieldname": f, "label": m["label"], "fieldtype": m["fieldtype"], "description": m["description"]}
            for f, m in src["fields"].items()
        ]
        if "name" not in src["fields"]:
            fields.insert(0, {"fieldname": "name", "label": "ID", "fieldtype": "Data", "description": ""})
        sources.append({
            "doctype": dt,
            "description": src["description"],
            "parent": src.get("parent_doctype"),
            "fields": fields,
            "joins": engine.join_options(dt, catalog, env),
        })
    return {
        "sources": sources,
        "aggs": engine.AGGS,
        "date_parts": engine.DATE_PARTS,
        "ops": engine.OPS,
        "timespans": engine.TIMESPANS,
        "viz_types": vizlib.VIZ_TYPES,
        "can_save": bool(frappe.has_permission("Neotec AI Report", "create")),
        "can_create_dashboard": bool(frappe.has_permission("Neotec Dashboard", "create")),
        "dashboards": _editable_dashboards(),
        "hidden_sources": len(engine.get_full_catalog()) - len(catalog),
    }


def _editable_dashboards():
    out = []
    for d in frappe.get_list("Neotec Dashboard", fields=["name", "title"], order_by="modified desc", limit=100):
        if frappe.has_permission("Neotec Dashboard", "write", doc=d.name):
            out.append(d)
    return out


@frappe.whitelist(methods=["POST"])
def run(definition, extra_filters=None):
    _check_access()
    return reports.safe_run(_load(definition), extra_filters=_load(extra_filters, []))


@frappe.whitelist()
def get_report(name):
    _check_access()
    doc = frappe.get_doc("Neotec AI Report", name)
    if not doc.has_permission("read"):
        _not_permitted(_("This report has not been shared with you."))
    return {
        "name": doc.name,
        "title": doc.title,
        "description": doc.description,
        "definition": doc.get_definition(),
        "can_write": bool(doc.has_permission("write")),
        "owner": doc.owner,
    }


@frappe.whitelist(methods=["POST"])
def ai_build(prompt, definition=None):
    """Create or modify a report definition from a plain-language request."""
    from neotec_ai.api import _check_rate_limit, _write_log

    _check_access()
    start = time.time()
    settings = frappe.get_cached_doc("Neotec Settings")
    if not settings.enable_ai:
        return {"ok": False, "message": _("The AI assistant is disabled.")}
    prompt = (prompt or "").strip()[:4000]
    if not prompt:
        return {"ok": False, "message": _("Describe the report you want.")}
    _check_rate_limit(settings)

    env = engine.FrappeEnv()
    catalog = engine.user_catalog(env)
    if not catalog:
        return {"ok": False, "permission": True, "message": _("You don't have access to any data sources yet. Ask your administrator.")}
    joins = {dt: engine.join_options(dt, catalog, env) for dt in catalog}
    current = _load(definition)

    system = "\n\n".join(filter(None, [
        "You are a BI report designer inside an ERP (Frappe/ERPNext). Turn the user's request into a report "
        "definition. If a current report is given, modify it as asked and keep everything else.",
        f"Today is {formatdate(nowdate(), 'yyyy-mm-dd')}.",
        ("## Business context\n" + settings.business_context.strip()) if settings.business_context else "",
        bi_prompt.QUERY_FORMAT,
        bi_prompt.VIZ_FORMAT,
        "## Data dictionary\n" + describe_catalog(catalog, joins),
        'Reply with ONLY JSON: {"title": "...", "description": "...", "query": {...}, "viz": {...}, '
        '"explanation": "<one or two sentences on what the report shows and any assumptions>"}',
    ]))
    messages = [{"role": "user", "content": json.dumps({"request": prompt, "current_report": current}, default=str)}]
    api_key = settings.get_password("api_key", raise_exception=False)

    tokens, error, out = 0, None, None
    try:
        for _attempt in range(3):
            text, t = llm.complete(settings, api_key, system, messages)
            tokens += t or 0
            spec = _extract_json(text)
            if not spec:
                messages += [{"role": "assistant", "content": text}, {"role": "user", "content": "Reply with the JSON object only."}]
                continue
            try:
                report = reports.run_definition(spec)
                out = {"ok": True, "report": report, "explanation": str(spec.get("explanation") or "")[:1000]}
                break
            except engine.AccessError as e:
                out = {"ok": False, "permission": True, "message": str(e)}
                break
            except PlanError as e:
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"That definition is invalid: {e}\nFix it and reply with the complete JSON."},
                ]
        if out is None:
            out = {"ok": False, "message": _("The AI could not build a valid report for this request. Try rephrasing it or build it manually.")}
    except llm.LLMError as e:
        error = str(e)
        out = {"ok": False, "message": _("The AI service could not answer right now.") +
               (f" {error}" if "System Manager" in frappe.get_roles() else "")}

    _write_log(settings, f"[BI Builder] {prompt}", (out or {}).get("explanation") or (out or {}).get("message"),
               error, tokens, round((time.time() - start) * 1000, 2), 0,
               [{"report": (out.get("report") or {}).get("title"), "definition": (out.get("report") or {}).get("definition")}] if out.get("ok") else [],
               None, None)
    return out


def _extract_json(text):
    if not text:
        return None
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e <= s:
        return None
    try:
        obj = json.loads(text[s : e + 1])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) and obj.get("query") else None


# --------------------------------------------------------------------------------------
# Dashboards
# --------------------------------------------------------------------------------------

@frappe.whitelist()
def get_dashboards():
    _check_access()
    rows = frappe.get_list(
        "Neotec Dashboard", fields=["name", "title", "description", "owner", "modified"], order_by="modified desc", limit=200
    )
    for r in rows:
        r["item_count"] = frappe.db.count("Neotec Dashboard Item", {"parent": r.name, "parenttype": "Neotec Dashboard"})
    return {"dashboards": rows, "can_create": bool(frappe.has_permission("Neotec Dashboard", "create"))}


@frappe.whitelist(methods=["POST"])
def create_dashboard(title, description=None):
    _check_access()
    if not frappe.has_permission("Neotec Dashboard", "create"):
        _not_permitted(_("You don't have permission to create dashboards."))
    doc = frappe.get_doc({"doctype": "Neotec Dashboard", "title": title.strip()[:140], "description": description})
    doc.insert()
    return {"name": doc.name}


def _dashboard(name, ptype="read"):
    _check_access()
    if not frappe.db.exists("Neotec Dashboard", name):
        frappe.throw(_("Dashboard {0} not found.").format(name), frappe.DoesNotExistError)
    doc = frappe.get_doc("Neotec Dashboard", name)
    if not doc.has_permission(ptype):
        _not_permitted(
            _("This dashboard has not been shared with you.") if ptype == "read"
            else _("You can view this dashboard but not change it. Ask its owner for edit access.")
        )
    return doc


@frappe.whitelist()
def get_dashboard(name):
    doc = _dashboard(name)
    items = []
    for row in doc.items:
        title = row.title
        if row.item_type == "Report" and row.report and not title:
            title = frappe.db.get_value("Neotec AI Report", row.report, "title")
        items.append({
            "name": row.name, "item_type": row.item_type, "report": row.report, "title": title,
            "width": row.width or "6", "height": row.height or "Medium", "content": row.content,
        })
    companies = []
    if doc.enable_company_filter and frappe.db.exists("DocType", "Company"):
        companies = frappe.get_list("Company", pluck="name", limit=100)
    return {
        "name": doc.name, "title": doc.title, "description": doc.description,
        "default_timespan": doc.default_timespan, "enable_company_filter": doc.enable_company_filter,
        "companies": companies, "can_write": bool(doc.has_permission("write")), "items": items,
        "timespans": engine.TIMESPANS,
    }


def _dashboard_filters(definition, row, filters):
    """Translate dashboard filter values into engine extra_filters for one report."""
    filters = _load(filters, {}) or {}
    if not isinstance(filters, dict):
        filters = {}
    q = engine.normalize_query(definition["query"])
    out = []
    date_field = row.date_field or auto_date_field(q)
    if date_field:
        if filters.get("timespan"):
            out.append({"field": date_field, "op": "timespan", "value": filters["timespan"], "replace": True})
        elif filters.get("from_date") and filters.get("to_date"):
            out.append({"field": date_field, "op": "between", "value": [filters["from_date"], filters["to_date"]], "replace": True})
    if filters.get("company"):
        catalog = engine.get_full_catalog()
        tables = [q["source"]] + [j.get("doctype") for j in q.get("joins") or []]
        for dt in tables:
            if "company" in (catalog.get(dt) or {}).get("fields", {}):
                out.append({"field": f"{dt}.company", "op": "=", "value": filters["company"], "replace": True})
                break
    return out


def auto_date_field(q):
    for f in q.get("filters") or []:
        if isinstance(f, dict) and f.get("op") in ("timespan", "between") and f.get("field"):
            return f["field"]
    catalog = engine.get_full_catalog()
    src = catalog.get(q.get("source")) or {}
    for name in DATE_FIELD_PREFERENCE:
        if name in src.get("fields", {}) and src["fields"][name]["fieldtype"] in ("Date", "Datetime"):
            return f"{q['source']}.{name}"
    return None


@frappe.whitelist(methods=["POST"])
def run_dashboard_item(dashboard, item, filters=None):
    doc = _dashboard(dashboard)
    row = next((r for r in doc.items if r.name == item), None)
    if not row:
        return {"ok": False, "message": _("This item was removed from the dashboard.")}
    if row.item_type == "Text":
        return {"ok": True, "text": row.content or ""}
    if not row.report or not frappe.db.exists("Neotec AI Report", row.report):
        return {"ok": False, "message": _("The report for this item no longer exists.")}
    # Dashboard access is enough to see the item; the data itself is still filtered by the viewer's permissions.
    definition = frappe.get_doc("Neotec AI Report", row.report).get_definition()
    if row.title:
        definition["title"] = row.title
    out = reports.safe_run(definition, extra_filters=_dashboard_filters(definition, row, filters))
    if out.get("ok"):
        if frappe.has_permission("Neotec AI Report", "read", doc=row.report):
            out["report"]["name"] = row.report
        else:  # viewer sees the data (with their own permissions) but not the report definition
            out["report"].pop("definition", None)
    return out


@frappe.whitelist(methods=["POST"])
def save_dashboard_layout(name, items):
    doc = _dashboard(name, "write")
    items = _load(items, [])
    by_name = {r.name: r for r in doc.items}
    ordered = []
    for it in items:
        row = by_name.pop(it.get("name"), None)
        if not row:
            continue
        if str(it.get("width")) in WIDTHS:
            row.width = str(it["width"])
        if it.get("height") in HEIGHTS:
            row.height = it["height"]
        if "title" in it:
            row.title = (it.get("title") or "")[:140]
        ordered.append(row)
    ordered += list(by_name.values())
    for i, row in enumerate(ordered, start=1):
        row.idx = i
    doc.items = ordered
    doc.save()
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def add_dashboard_item(dashboard, report=None, width="6", item_type="Report", content=None, title=None, height="Medium"):
    doc = _dashboard(dashboard, "write")
    if item_type == "Report":
        if not report or not frappe.db.exists("Neotec AI Report", report):
            frappe.throw(_("Choose a saved report."))
        if not frappe.has_permission("Neotec AI Report", "read", doc=report):
            _not_permitted(_("You can only add reports you own or that are shared with you."))
    row = doc.append("items", {
        "item_type": item_type if item_type in ("Report", "Text") else "Report",
        "report": report if item_type == "Report" else None,
        "content": content if item_type == "Text" else None,
        "title": (title or "")[:140] or None,
        "width": str(width) if str(width) in WIDTHS else "6",
        "height": height if height in HEIGHTS else "Medium",
    })
    doc.save()
    return {"name": row.name}


@frappe.whitelist(methods=["POST"])
def remove_dashboard_item(dashboard, item):
    doc = _dashboard(dashboard, "write")
    doc.items = [r for r in doc.items if r.name != item]
    doc.save()
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def ai_add_to_dashboard(dashboard, prompt, width="6"):
    _dashboard(dashboard, "write")
    out = ai_build(prompt)
    if not out.get("ok"):
        return out
    saved = reports.save_report(definition=out["report"]["definition"], prompt=prompt)
    add_dashboard_item(dashboard, report=saved["name"], width=width)
    return {"ok": True, "report": saved, "explanation": out.get("explanation")}


@frappe.whitelist(methods=["POST", "GET"])
def export_dashboard(name, fmt="pdf", filters=None):
    doc = _dashboard(name)
    reps = collect_dashboard(doc, filters)
    filename = frappe.scrub(doc.title)[:60] or "dashboard"
    if fmt == "xlsx":
        export.send_file(f"{filename}.xlsx", export.to_xlsx([r for r in reps if not r.get("error")]))
    else:
        export.send_file(f"{filename}.pdf", export.to_pdf(doc.title, reps, doc.description))


def collect_dashboard(doc, filters=None):
    reps = []
    for row in doc.items:
        if row.item_type != "Report" or not row.report or not frappe.db.exists("Neotec AI Report", row.report):
            continue
        definition = frappe.get_doc("Neotec AI Report", row.report).get_definition()
        if row.title:
            definition["title"] = row.title
        out = reports.safe_run(definition, extra_filters=_dashboard_filters(definition, row, filters))
        if out.get("ok"):
            reps.append(out["report"])
        else:
            reps.append({"title": definition["title"], "error": out.get("message"), "columns": [], "rows": []})
    return reps
