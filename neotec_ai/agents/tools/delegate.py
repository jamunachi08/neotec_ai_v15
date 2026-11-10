# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Delegation: a coworker hands a self-contained sub-task to another coworker.

The other coworker works in its own conversation (linked as "Delegated From"), with its own tools and grants,
as the same user and under the same policy. It cannot ask questions, cannot wait for approvals (it reports the
change instead) and cannot delegate again, so chains always end. Only its final answer comes back.
"""

from __future__ import annotations

import frappe
from frappe import _

from neotec_ai.agents.engine.registry import tool

MAX_ANSWER = 6000


@tool("delegate_task", "Delegate to another coworker",
      "Hand a self-contained sub-task to another coworker who is better suited (for example the Finance Analyst "
      "for figures, Procurement Checker for supplier questions). Give the full context in the task; it cannot "
      "see this conversation or ask questions. Returns its final answer.",
      {"coworker": {"type": "string", "description": "Exact coworker name"},
       "task": {"type": "string", "description": "What to do and what to return"},
       "__required__": ["coworker", "task"]}, category="Automation")
def delegate_task(coworker, task):
    from neotec_ai.agents.engine import runner

    parent = frappe.flags.get("ntc_conversation")
    depth = int(frappe.flags.get("ntc_depth") or 0)
    if depth >= 1:
        frappe.throw(_("A delegated coworker cannot delegate again."))
    if not frappe.db.exists("AI Coworker", coworker):
        names = frappe.get_all("AI Coworker", filters={"enabled": 1, "chat_visible": 1}, pluck="name")
        frappe.throw(_("There is no coworker called {0}. Available: {1}").format(coworker, ", ".join(names)))
    if coworker == frappe.flags.get("ntc_coworker"):
        frappe.throw(_("Delegate to a different coworker."))
    target = frappe.get_doc("AI Coworker", coworker)
    if not target.enabled:
        frappe.throw(_("The coworker {0} is disabled.").format(coworker))
    if not runner.can_use(target, frappe.session.user):
        raise frappe.PermissionError(_("This user may not use the coworker {0}.").format(coworker))

    mode = frappe.db.get_value("Coworker Conversation", parent, "permission_mode") if parent else None
    saved = {k: frappe.flags.get(k) for k in ("ntc_conversation", "ntc_depth", "ntc_coworker", "ntc_run",
                                              "ntc_external")}
    try:
        child = frappe.get_doc({
            "doctype": "Coworker Conversation", "coworker": coworker, "user": frappe.session.user,
            "title": f"Delegated: {task[:60]}", "channel": "Delegated", "status": "Idle",
            "parent_conversation": parent, "delegation_depth": depth + 1, "permission_mode": mode or "Standard",
        }).insert(ignore_permissions=True)
        runner.add_message(child.name, "user",
                           f"{task}\n\n(Delegated by the coworker {saved.get('ntc_coworker') or ''}. Work only from "
                           "this task. You cannot ask questions or wait for approvals: if a change needs approval, "
                           "describe it instead. Finish with a complete, self-contained answer.)", status="ok")
        frappe.db.commit()
        answer = runner.run_once(child.name)
        return {"coworker": coworker, "conversation": child.name, "answer": (answer or "")[:MAX_ANSWER]}
    except Exception as e:  # noqa: BLE001 - never raise after the child committed (the tool savepoint is gone)
        frappe.db.rollback()
        return {"coworker": coworker, "error": str(e)[:500] or e.__class__.__name__}
    finally:
        for k, v in saved.items():
            frappe.flags[k] = v
