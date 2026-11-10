# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""BI tools: coworkers query the governed Data Dictionary the assistant and the BI Builder use, and can save
a result as a Neotec AI Report (re-runs live with each viewer's permissions, can be added to dashboards and
scheduled). Only DocTypes and fields enabled in the Data Dictionary are reachable; every query runs as the
user with their role, user-permission and field-level restrictions.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from neotec_ai.agents.engine.registry import tool
from neotec_ai.agents.tools._common import jarg


def _catalog():
    from neotec_ai.bi import engine

    return engine.user_catalog(engine.FrappeEnv())


@tool("list_data_sources", "List BI data sources",
      "List the business data sources (Data Dictionary) this user can query with query_data, each with a short "
      "description. Use before query_data when you are not sure which source holds the data.",
      {"search": {"type": "string", "description": "Optional words to filter by"}}, category="Data")
def list_data_sources(search=None):
    cat = _catalog()
    words = [w for w in (search or "").lower().split() if len(w) > 2]
    out = []
    for name, src in sorted(cat.items()):
        text = f"{name} {src.get('description') or ''}".lower()
        if words and not any(w in text for w in words):
            continue
        out.append({"source": name, "description": (src.get("description") or "")[:160]})
    return {"sources": out[:80], "total": len(out)}


@tool("describe_data_source", "Describe a BI data source",
      "Fields (with their business meaning), joins and the exact query format for one or more Data Dictionary "
      "sources. Always call this before query_data.",
      {"sources": {"type": "string", "description": "Source name, or several separated by commas"},
       "__required__": ["sources"]}, category="Data")
def describe_data_source(sources):
    from neotec_ai.bi import prompt as bi_prompt
    from neotec_ai.query_engine import describe_catalog

    names = [s.strip() for s in jarg(sources, []) if s.strip()] if not isinstance(sources, list) else sources
    cat = _catalog()
    known = {n: cat[n] for n in names[:6] if n in cat}
    missing = [n for n in names if n not in cat]
    return {"sources": describe_catalog(known)[:9000] if known else "",
            "not_available": missing, "query_format": bi_prompt.QUERY_FORMAT}


@tool("query_data", "Query business data (BI)",
      "Run one query over the Data Dictionary: columns, sums/counts/averages, date parts, joins, filters, "
      "sorting and a row limit. Use describe_data_source first for fields and the format. Results follow the "
      "user's permissions.",
      {"query": {"type": "string", "description": "The query as a JSON object (format from describe_data_source)"},
       "__required__": ["query"]}, category="Data")
def query_data(query):
    from neotec_ai.bi import engine

    q = jarg(query, {})
    if not isinstance(q, dict):
        frappe.throw(_("query must be a JSON object."))
    max_rows = min(engine._max_rows(), 200)
    try:
        res = engine.run(q, catalog=engine.get_full_catalog(), max_rows=max_rows)
    except engine.AccessError as e:
        raise frappe.PermissionError(str(e)) from e
    cols = [c["fieldname"] for c in res["columns"]]
    return {"source": res["source"], "columns": [{"field": c["fieldname"], "label": c.get("label")} for c in res["columns"]],
            "rows": [dict(zip(cols, r)) for r in res["rows"]], "row_count": res["row_count"],
            "truncated": bool(res.get("truncated"))}


@tool("save_bi_report", "Save as a BI report",
      "Save a query as a Neotec AI Report the user can reopen, export, add to a dashboard or schedule by e-mail. "
      "It keeps the query, not the data, so it always shows current figures.",
      {"title": {"type": "string"}, "query": {"type": "string", "description": "The query JSON used in query_data"},
       "viz": {"type": "string", "description": "Optional visualization JSON, e.g. {\"type\": \"bar\"}"},
       "description": {"type": "string"}, "__required__": ["title", "query"]},
      category="Data", is_write=True, risk="Low")
def save_bi_report(title, query, viz=None, description=None):
    from neotec_ai import reports

    definition = {"title": title, "query": jarg(query, {}), "viz": jarg(viz, {}) if viz else None}
    out = reports.save_report(definition=json.dumps(definition, default=str), title=title,
                              description=description or "", prompt="Saved by a coworker")
    return {"report": out["name"], "title": out["title"], "url": f"/app/neotec-bi?report={out['name']}"}
