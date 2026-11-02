"""AI-built reports: validation, live execution, export and saving.

A report spec is plain JSON:
    {"title": str, "description": str,
     "query": <same query format the AI uses for data lookups>,
     "chart": {"type": "bar|line|pie|donut|percentage", "x": "col" | ["col1", "col2"], "y": ["num_col", ...]} | null}

Specs are re-validated against the Data Dictionary and re-run as the *current* user every time a
report is shown, exported or opened from a saved copy, so data is always live and permission-checked.
"""

import csv
import io
import json
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import cint

from neotec_ai import query_engine
from neotec_ai.query_engine import CHART_NUMERIC_TYPES, PlanError

CHART_TYPES = {"bar", "line", "pie", "donut", "percentage"}
SINGLE_SERIES = {"pie", "donut", "percentage"}
MAX_REPORTS_PER_ANSWER = 3


def max_report_rows():
    return max(10, min(cint(frappe.db.get_single_value("Neotec Settings", "max_report_rows")) or 500, 5000))


# --------------------------------------------------------------------------------------
# Validation (pure helpers)
# --------------------------------------------------------------------------------------

def normalise_spec(spec):
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except ValueError:
            raise PlanError("Report spec is not valid JSON.")
    if not isinstance(spec, dict) or not isinstance(spec.get("query"), dict):
        raise PlanError("A report needs a 'query' object.")
    title = str(spec.get("title") or "AI Report").strip()[:140]
    return {
        "title": title,
        "description": str(spec.get("description") or "").strip()[:1000],
        "query": spec["query"],
        "chart": spec.get("chart") or None,
    }


def validate_chart(chart, columns):
    """Return a clean chart config or None. Raises PlanError for unusable configs."""
    if not chart:
        return None
    if not isinstance(chart, dict):
        raise PlanError("chart must be an object with type, x and y.")
    ctype = str(chart.get("type") or "bar").lower()
    if ctype not in CHART_TYPES:
        raise PlanError(f"Chart type must be one of: {', '.join(sorted(CHART_TYPES))}.")

    names = {c["fieldname"]: c for c in columns}
    x = chart.get("x")
    xs = x if isinstance(x, list) else [x]
    xs = [str(v).lower() for v in xs if v]
    if not xs or len(xs) > 2 or any(v not in names for v in xs):
        raise PlanError(f"chart.x must be one or two result columns: {', '.join(names)}.")

    y = chart.get("y")
    ys = y if isinstance(y, list) else [y]
    ys = [str(v).lower() for v in ys if v]
    if not ys:  # pick a measure: prefer amounts over counts / date parts
        numeric = [c for c, meta in names.items() if meta["fieldtype"] in CHART_NUMERIC_TYPES and c not in xs]
        amounts = [c for c in numeric if names[c]["fieldtype"] in ("Currency", "Float", "Percent")]
        ys = (amounts or numeric[-1:])[:1]
    bad = [v for v in ys if v not in names or names[v]["fieldtype"] not in CHART_NUMERIC_TYPES]
    if not ys or bad:
        raise PlanError(f"chart.y must be numeric result columns; problem with: {', '.join(bad) or 'none given'}.")
    if ctype in SINGLE_SERIES:
        ys = ys[:1]
    return {"type": ctype, "x": xs, "y": ys[:6]}


# --------------------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------------------

def build_report(spec, catalog=None):
    """Validate and run a spec as the current user. Returns a dict ready for the UI."""
    spec = normalise_spec(spec)
    catalog = catalog if catalog is not None else query_engine.get_catalog()
    limit = max_report_rows()

    kwargs = query_engine.validate_query(spec["query"], catalog, limit)
    columns = query_engine.output_columns(kwargs, catalog)
    chart = validate_chart(spec["chart"], columns)

    doctype = kwargs.pop("doctype")
    rows = frappe.get_list(doctype, **kwargs)
    data = [[_cell(r.get(c["fieldname"])) for c in columns] for r in rows]

    spec["chart"] = chart
    return {
        "title": spec["title"],
        "description": spec["description"],
        "doctype": doctype,
        "columns": columns,
        "rows": data,
        "chart": chart,
        "truncated": len(rows) >= kwargs["limit_page_length"],
        "spec": spec,
    }


def build_reports_from_answer(specs, catalog):
    """Used by chat: returns (reports, errors)."""
    reports, errors = [], []
    if not isinstance(specs, list):
        specs = [specs]
    for i, spec in enumerate(specs[:MAX_REPORTS_PER_ANSWER], start=1):
        try:
            reports.append(build_report(spec, catalog))
        except PlanError as e:
            errors.append(f"Report {i}: {e}")
        except frappe.PermissionError:
            frappe.clear_last_message()
            errors.append(f"Report {i}: permission denied")
        except Exception as e:
            frappe.clear_last_message()
            errors.append(f"Report {i}: {str(e)[:300]}")
    return reports, errors


def _cell(v):
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float):
        return round(v, 4)
    if v is None or isinstance(v, (int, str, bool)):
        return v
    return str(v)


# --------------------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------------------

@frappe.whitelist()
def run_report(name=None, spec=None):
    """Run a saved report (by name) or an unsaved spec, live, as the current user."""
    _check_access()
    if name:
        doc = frappe.get_doc("Neotec AI Report", name)
        doc.check_permission("read")
        spec = doc.get_spec()
    try:
        return {"ok": True, "report": build_report(spec)}
    except PlanError as e:
        return {"ok": False, "message": str(e)}


@frappe.whitelist(methods=["POST"])
def save_report(spec, title=None, prompt=None):
    _check_access()
    spec = normalise_spec(spec)
    if title:
        spec["title"] = title.strip()[:140]
    build_report(spec)  # validates as this user; raises if invalid

    chart = spec.get("chart") or {}
    doc = frappe.get_doc(
        {
            "doctype": "Neotec AI Report",
            "title": spec["title"],
            "description": spec["description"],
            "source_prompt": (prompt or "")[:2000],
            "query_spec": json.dumps(spec["query"], indent=1),
            "chart_type": chart.get("type") or "",
            "chart_x": ", ".join(chart.get("x") or []),
            "chart_y": ", ".join(chart.get("y") or []),
        }
    )
    doc.insert()
    return {"name": doc.name, "title": doc.title}


@frappe.whitelist(methods=["POST", "GET"])
def export_report(name=None, spec=None, fmt="xlsx"):
    """Re-run the report live and download it as Excel or CSV."""
    _check_access()
    if name:
        doc = frappe.get_doc("Neotec AI Report", name)
        doc.check_permission("read")
        spec = doc.get_spec()
    try:
        report = build_report(spec)
    except PlanError as e:
        frappe.throw(str(e))

    header = [c["label"] for c in report["columns"]]
    table = [header] + report["rows"]
    filename = frappe.scrub(report["title"])[:60] or "ai_report"

    if fmt == "csv":
        buf = io.StringIO()
        csv.writer(buf).writerows(table)
        frappe.response["filename"] = f"{filename}.csv"
        frappe.response["filecontent"] = buf.getvalue().encode("utf-8-sig")
    else:
        from frappe.utils.xlsxutils import make_xlsx

        xlsx = make_xlsx(table, report["title"][:31] or "Report")
        frappe.response["filename"] = f"{filename}.xlsx"
        frappe.response["filecontent"] = xlsx.getvalue()
    frappe.response["type"] = "binary"


def _check_access():
    from neotec_ai.api import _check_access as check

    check()
