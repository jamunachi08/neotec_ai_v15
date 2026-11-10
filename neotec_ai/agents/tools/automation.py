# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Automation tools.

* signals_check / signals_record: let a playbook remember what it already reported, so a daily run does not
  repeat yesterday's findings. Granted automatically to playbook runs that have a repeat window.
* list_playbooks / run_playbook / get_run: let a chat coworker or an external MCP client start a playbook
  and read its result. A run can never start another run.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

from neotec_ai.agents.automation import common
from neotec_ai.agents.engine.registry import tool
from neotec_ai.agents.tools._common import jarg

S = {"type": "string"}


def _current_run():
    name = frappe.flags.get("ntc_run")
    if not name:
        frappe.throw(_("This tool is only available inside a playbook run."))
    return frappe.db.get_value("Coworker Run", name, ["name", "playbook"], as_dict=True)


@tool("signals_check", "Check what was already reported",
      "Inside a playbook run: pass the keys of the findings you are about to report. Returns which were already "
      "reported within the playbook's repeat window, so you can leave them out.",
      {"keys": {"type": "string", "description": "JSON list or comma separated keys, e.g. [\"overdue:CUST-0012\"]"},
       "__required__": ["keys"]}, category="Automation")
def signals_check(keys):
    run = _current_run()
    days = cint(frappe.db.get_value("Coworker Playbook", run.playbook, "dedupe_days")) or 3
    wanted = [common.normalise_key(k) for k in (jarg(keys, []) or []) if common.normalise_key(k)][:200]
    since = add_to_date(now_datetime(), days=-days)
    seen = set(frappe.get_all("Coworker Signal", filters={"playbook": run.playbook, "signal_key": ["in", wanted or [""]],
                                                          "last_seen": [">=", since]}, pluck="signal_key"))
    return {"window_days": days, "already_reported": [k for k in wanted if k in seen],
            "new": [k for k in wanted if k not in seen]}


@tool("signals_record", "Record reported findings",
      "Inside a playbook run, after writing the report: record the findings you reported so later runs skip them.",
      {"items": {"type": "string",
                 "description": "JSON list of objects: [{\"key\": \"overdue:CUST-0012\", \"summary\": \"SAR 84,000 over 90 days\"}]"},
       "__required__": ["items"]}, category="Automation")
def signals_record(items):
    run = _current_run()
    rows = jarg(items, []) or []
    if isinstance(rows, dict):
        rows = [rows]
    now = now_datetime()
    saved = 0
    for row in rows[:200]:
        if isinstance(row, str):
            row = {"key": row}
        key = common.normalise_key((row or {}).get("key"))
        if not key:
            continue
        summary = str(row.get("summary") or "")[:500]
        name = frappe.db.get_value("Coworker Signal", {"playbook": run.playbook, "signal_key": key}, "name")
        if name:
            frappe.db.sql("""update `tabCoworker Signal` set last_seen=%s, summary=%s, run=%s,
                times_seen=ifnull(times_seen,0)+1 where name=%s""", (now, summary, run.name, name))
        else:
            frappe.get_doc({"doctype": "Coworker Signal", "playbook": run.playbook, "signal_key": key,
                            "summary": summary, "first_seen": now, "last_seen": now, "times_seen": 1,
                            "run": run.name}).insert(ignore_permissions=True)
        saved += 1
    return {"recorded": saved}


@tool("list_playbooks", "List playbooks",
      "Lists the playbooks this user can run, with what each does and the parameter it takes.",
      {"search": {"type": "string", "description": "Optional word to filter by name or category."}},
      category="Automation")
def list_playbooks(search=None):
    from neotec_ai.agents.automation.playbooks import _can_use_playbook, playbook_available

    out = []
    filters = {"enabled": 1}
    or_filters = None
    if search:
        or_filters = [["playbook_name", "like", f"%{search}%"], ["category", "like", f"%{search}%"],
                      ["description", "like", f"%{search}%"]]
    for name in frappe.get_all("Coworker Playbook", filters=filters, or_filters=or_filters, pluck="name",
                               order_by="category asc, playbook_name asc", limit_page_length=100):
        pb = frappe.get_cached_doc("Coworker Playbook", name)
        if not playbook_available(pb) or not _can_use_playbook(pb):
            continue
        out.append({"playbook": pb.name, "category": pb.category, "mode": pb.mode, "description": pb.description,
                    "parameter": pb.parameter_label or None, "default_parameter": pb.default_parameter or None})
    return {"playbooks": out}


@tool("run_playbook", "Run a playbook",
      "Starts a playbook in the background as this user and returns the run ID. Use get_run later for the result. "
      "Results are also delivered to the playbook's channels.",
      {"playbook": S, "parameter": S,
       "dry_run": {"type": "boolean", "description": "True = change nothing, describe what would be done."},
       "__required__": ["playbook"]}, category="Automation", risk="Medium")
def run_playbook(playbook, parameter=None, dry_run=False):
    from neotec_ai.agents.automation.playbooks import _can_use_playbook, start_run

    if frappe.flags.get("ntc_run"):
        frappe.throw(_("A playbook run cannot start another playbook."))
    if not frappe.db.exists("Coworker Playbook", playbook):
        frappe.throw(_("There is no playbook called {0}. Use list_playbooks.").format(playbook))
    pb = frappe.get_doc("Coworker Playbook", playbook)
    if not _can_use_playbook(pb):
        frappe.throw(_("You do not have access to the coworker this playbook uses."), frappe.PermissionError)
    source = "MCP" if frappe.flags.get("ntc_mcp_call") else "Manual"
    run = start_run(pb.name, parameter, source=source, run_as=frappe.session.user, dry_run=1 if dry_run else 0)
    return {"run": run, "status": "Queued",
            "message": "Started. The result usually arrives within a few minutes; check it with get_run."}


@tool("get_run", "Get a playbook result",
      "Returns the status, severity and result of a playbook run.",
      {"run": S, "__required__": ["run"]}, category="Automation")
def get_run(run):
    doc = frappe.get_doc("Coworker Run", run)
    if doc.run_as != frappe.session.user and not set(frappe.get_roles()) & {"Coworker Admin", "System Manager"}:
        frappe.throw(_("This run belongs to someone else."), frappe.PermissionError)
    return {"run": doc.name, "playbook": doc.playbook, "status": doc.status, "severity": doc.severity,
            "parameter": doc.parameter, "started": str(doc.started_on or ""), "ended": str(doc.ended_on or ""),
            "output": (doc.output or "")[:8000], "error": doc.error}
