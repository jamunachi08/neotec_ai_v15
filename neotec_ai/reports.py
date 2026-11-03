"""Report definitions: run, save and export (shared by chat, BI builder, dashboards and schedules).

A report definition is either a data query or an ERPNext report:
    {"title": str, "description": str, "query": <bi.engine query>, "viz": <bi.viz spec>}
    {"title": str, "description": str, "erp_report": {"report": "<Report name>", "filters": {...}}, "viz": ...}
Legacy v2.1 definitions ({"query": {doctype, fields...}, "chart": {...}}) are converted automatically.

Definitions are re-validated and re-run as the *current* user every time, so data is live and
permission-checked.
"""

import json

import frappe
from frappe import _

from neotec_ai.bi import engine, export
from neotec_ai.bi import viz as vizlib
from neotec_ai.query_engine import PlanError

MAX_REPORTS_PER_ANSWER = 3


# --------------------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------------------

def normalise_definition(d):
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except ValueError:
            raise PlanError("Report definition is not valid JSON.")
    if not isinstance(d, dict):
        raise PlanError("A report definition must be an object.")
    base = {
        "title": str(d.get("title") or "Untitled Report").strip()[:140],
        "description": str(d.get("description") or "").strip()[:1000],
        "viz": d.get("viz") or vizlib.from_legacy_chart(d.get("chart")),
    }
    erp = d.get("erp_report")
    if isinstance(erp, str):
        erp = {"report": erp}
    if isinstance(erp, dict):
        if not erp.get("report"):
            raise PlanError("An ERPNext report needs a 'report' name.")
        filters = erp.get("filters") or {}
        if not isinstance(filters, dict):
            raise PlanError("ERPNext report 'filters' must be an object.")
        return {**base, "erp_report": {"report": str(erp["report"])[:140], "filters": filters}}
    if not isinstance(d.get("query"), (dict, str)):
        raise PlanError("A report needs a 'query' or an 'erp_report'.")
    return {**base, "query": engine.normalize_query(d["query"])}


def run_definition(d, extra_filters=None, catalog=None, env=None):
    """Run a definition. Raises PlanError (invalid) or engine.AccessError (no permission)."""
    d = normalise_definition(d)
    if "erp_report" in d:
        from neotec_ai import erp_reports

        extra = next((f for f in (extra_filters or []) if isinstance(f, dict) and f.get("kind") == "erp"), None)
        result = erp_reports.run_for_definition(d["erp_report"], extra)
    else:
        result = engine.run(d["query"], catalog=catalog, env=env, extra_filters=extra_filters)
        for col, rc in zip(d["query"]["columns"], result["columns"]):  # record resolved aliases
            if isinstance(col, dict):
                col["alias"] = rc["fieldname"]
    viz = vizlib.validate(d["viz"], result["columns"])
    if not d["viz"]:
        viz = vizlib.suggest(result["columns"], result["row_count"])
    d["viz"] = viz
    report = {
        "title": d["title"],
        "description": d["description"],
        "doctype": result["source"],
        "source_type": "ERPNext Report" if "erp_report" in d else "Data Query",
        "summary": result.get("summary") or [],
        "filters_used": result.get("filters_used"),
        "columns": result["columns"],
        "rows": result["rows"],
        "row_count": result["row_count"],
        "truncated": result["truncated"],
        "viz": viz,
        "pivot": engine.pivot(result, viz["pivot"]) if viz["type"] == "pivot" else None,
        "definition": d,
    }
    return report


def safe_run(d, extra_filters=None):
    """Run and convert errors into a message dict for the UI."""
    try:
        return {"ok": True, "report": run_definition(d, extra_filters=extra_filters)}
    except engine.AccessError as e:
        return {"ok": False, "permission": True, "message": str(e)}
    except PlanError as e:
        return {"ok": False, "message": str(e)}
    except frappe.PermissionError:
        frappe.clear_last_message()
        return {"ok": False, "permission": True, "message": _("You don't have permission to view this data.")}
    except frappe.ValidationError as e:
        frappe.clear_last_message()
        from frappe.utils import strip_html

        return {"ok": False, "message": strip_html(str(e)) or _("The report could not run with these settings.")}
    except Exception as e:
        frappe.clear_last_message()
        text = str(e).lower()
        if "max_statement_time" in text or "interrupted" in text or "timeout" in text:
            return {"ok": False, "message": _("This report took too long. Narrow the period or filters and try again.")}
        frappe.log_error(title="Neotec AI: report run failed")
        return {"ok": False, "message": _("The report could not run. The error has been logged for your administrator.")}


def build_reports_from_answer(specs, catalog=None):
    """Used by chat: returns (reports, errors)."""
    reports, errors = [], []
    if not isinstance(specs, list):
        specs = [specs]
    for i, spec in enumerate(specs[:MAX_REPORTS_PER_ANSWER], start=1):
        try:
            reports.append(run_definition(spec))
        except engine.AccessError as e:
            errors.append(f"Report {i}: {e}")
        except PlanError as e:
            errors.append(f"Report {i}: {e}")
        except Exception as e:
            frappe.clear_last_message()
            errors.append(f"Report {i}: {str(e)[:300]}")
    return reports, errors


# --------------------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------------------

@frappe.whitelist()
def run_report(name=None, definition=None, spec=None, extra_filters=None):
    """Run a saved report (by name) or an unsaved definition, live, as the current user."""
    _check_access()
    if name:
        doc = frappe.get_doc("Neotec AI Report", name)
        if not doc.has_permission("read"):
            return {"ok": False, "permission": True, "message": _("This report has not been shared with you.")}
        definition = doc.get_definition()
    definition = definition or spec
    extra_filters = _json_list(extra_filters)
    out = safe_run(definition, extra_filters=extra_filters)
    if out.get("ok") and name:
        out["report"]["name"] = name
    return out


@frappe.whitelist(methods=["POST"])
def save_report(definition=None, title=None, prompt=None, name=None, spec=None, description=None):
    """Create a new saved report, or update `name` if the user may edit it."""
    _check_access()
    d = normalise_definition(definition or spec)
    if title:
        d["title"] = title.strip()[:140]
    if description is not None:
        d["description"] = description.strip()[:1000]

    if name:
        doc = frappe.get_doc("Neotec AI Report", name)
        if not doc.has_permission("write"):
            frappe.throw(_("You can't change this report because it belongs to someone else. Use 'Save As' to keep your own copy."),
                         title=_("Not Permitted"))
    else:
        if not frappe.has_permission("Neotec AI Report", "create"):
            frappe.throw(_("You don't have permission to save reports. Ask your administrator for the Neotec AI User role."),
                         title=_("Not Permitted"))
        doc = frappe.new_doc("Neotec AI Report")
        doc.source_prompt = (prompt or "")[:2000]

    doc.title = d["title"]
    doc.description = d["description"]
    doc.query_spec = json.dumps({"erp_report": d["erp_report"]} if "erp_report" in d else d["query"], indent=1, default=str)
    doc.viz_spec = json.dumps(d["viz"], indent=1) if d["viz"] else None
    doc.save()
    return {"name": doc.name, "title": doc.title}


@frappe.whitelist(methods=["POST", "GET"])
def export_report(name=None, definition=None, spec=None, fmt="xlsx", extra_filters=None):
    """Re-run live and download as Excel, CSV or PDF."""
    _check_access()
    if name:
        doc = frappe.get_doc("Neotec AI Report", name)
        if not doc.has_permission("read"):
            frappe.throw(_("This report has not been shared with you."), frappe.PermissionError)
        definition = doc.get_definition()
    extra_filters = _json_list(extra_filters)
    try:
        report = run_definition(definition or spec, extra_filters=extra_filters)
    except (PlanError, engine.AccessError) as e:
        frappe.throw(str(e), title=_("Cannot Export"))

    filename = frappe.scrub(report["title"])[:60] or "report"
    if fmt == "csv":
        export.send_file(f"{filename}.csv", export.to_csv(report))
    elif fmt == "pdf":
        export.send_file(f"{filename}.pdf", export.to_pdf(report["title"], [report]))
    else:
        export.send_file(f"{filename}.xlsx", export.to_xlsx([report]))


def _json_list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value or "[]")
        except ValueError:
            frappe.throw(_("Invalid filter data."))
    return value if isinstance(value, list) else []


def _check_access():
    from neotec_ai.api import _check_access as check

    check()
