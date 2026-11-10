# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Triggers: start a playbook when a document is inserted, updated, submitted or cancelled.

Cost on every save in the system: one cached dictionary lookup. Only documents of a DocType that has an enabled
trigger go further. A trigger never breaks the user's save: any error is logged and the save continues.

Loop guard: changes made by a coworker never start triggers.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, getdate, now_datetime, nowdate

from neotec_ai.agents.automation import common

CACHE_KEY = "neotec_ai:trigger_index"
EVENTS = {"after_insert": "After Insert", "on_update": "On Update", "on_submit": "On Submit",
          "on_cancel": "On Cancel"}
SKIP = {"Version", "Comment", "Communication", "Error Log", "Notification Log", "Activity Log", "Access Log",
        "Scheduled Job Log", "Deleted Document", "Route History", "Email Queue", "Email Queue Recipient",
        "View Log", "Data Import", "Prepared Report", "Session Default", "DocShare", "User", "DocType",
        "Custom Field", "Property Setter", "Patch Log", "Unhandled Email", "Integration Request"}


def _cache():
    c = frappe.cache
    return c() if callable(c) else c


def clear_cache():
    _cache().delete_value(CACHE_KEY)


def _index() -> dict:
    def build():
        idx: dict[str, list] = {}
        for r in frappe.get_all("Coworker Trigger", filters={"enabled": 1},
                                fields=["name", "document_type", "event"]):
            idx.setdefault(r.document_type, []).append([r.name, r.event])
        return idx

    return _cache().get_value(CACHE_KEY, generator=build) or {}


def _quiet():
    f = frappe.flags
    return bool(f.in_install or f.in_migrate or f.in_patch or f.in_import or f.in_setup_wizard
                or f.in_uninstall or f.get("ntc_coworker"))


def on_event(doc, method=None):
    """doc_events hook for every DocType."""
    event = EVENTS.get(method)
    if not event or _quiet():
        return
    from neotec_ai.agents.takeover import legacy_installed

    if legacy_installed():
        return  # the old Coworker app is still installed and fires its own triggers
    dt = doc.doctype
    if dt in SKIP or dt.startswith("Coworker ") or dt == "AI Coworker":
        return
    try:
        rows = _index().get(dt)
        if not rows:
            return
        for name, ev in rows:
            if ev == event:
                _fire(name, doc)
    except Exception:  # noqa: BLE001 - never break the user's save
        frappe.log_error(title="Neotec AI trigger failed", reference_doctype=dt, reference_name=doc.name)


def evaluate(condition, doc) -> bool:
    if not (condition or "").strip():
        return True
    data = frappe._dict(doc.as_dict()) if hasattr(doc, "as_dict") else frappe._dict(doc)
    names = {"doc": data, "flt": flt, "cint": cint, "getdate": getdate, "nowdate": nowdate}
    return bool(frappe.safe_eval(condition, None, names))


def _run_as(t, doc):
    if t.run_as == "Fixed User":
        return t.fixed_user
    if t.run_as == "Last Modified By":
        return doc.modified_by or doc.owner
    return doc.owner


def _cooling(t, doc) -> bool:
    minutes = cint(t.cooldown_minutes)
    if minutes <= 0:
        return False
    since = add_to_date(now_datetime(), minutes=-minutes)
    return bool(frappe.db.exists("Coworker Run", {"trigger": t.name, "reference_doctype": doc.doctype,
                                                  "reference_name": doc.name, "creation": [">", since]}))


def _fire(name, doc, force=False):
    from neotec_ai.agents.automation import playbooks

    if not cint(frappe.get_cached_doc("Coworker Settings").enabled):
        return None
    t = frappe.get_cached_doc("Coworker Trigger", name)
    if not force:
        if not evaluate(t.condition, doc):
            return None
        if _cooling(t, doc):
            return None
    user = _run_as(t, doc)
    if not user or user == "Guest" or not frappe.db.get_value("User", user, "enabled"):
        return None
    parameter = common.render_parameter(t.parameter_template, {**doc.as_dict(no_child_table_fields=True),
                                                               "doctype": doc.doctype, "name": doc.name})
    run = playbooks.start_run(t.playbook, parameter, source="Trigger", run_as=user, trigger=t.name,
                              reference_doctype=doc.doctype, reference_name=doc.name)
    frappe.db.sql("""update `tabCoworker Trigger` set last_fired=%s, fire_count=ifnull(fire_count,0)+1
        where name=%s""", (now_datetime(), t.name))
    return run


# ---------------------------------------------------------------- controller

def validate_trigger(doc):
    dt = doc.document_type
    if dt in SKIP or dt.startswith("Coworker ") or dt == "AI Coworker":
        frappe.throw(_("Triggers cannot watch {0}.").format(dt))
    meta = frappe.get_meta(dt)
    if meta.istable:
        frappe.throw(_("{0} is a child table. Watch its parent document instead.").format(dt))
    if meta.issingle:
        frappe.throw(_("{0} is a settings page, not a document type.").format(dt))
    if doc.event in ("On Submit", "On Cancel") and not meta.is_submittable:
        frappe.throw(_("{0} cannot be submitted. Use After Insert or On Update.").format(dt))
    if (doc.condition or "").strip():
        try:
            compile(doc.condition, "<condition>", "eval")
        except SyntaxError as e:
            frappe.throw(_("The condition is not a valid Python expression: {0}").format(e.msg))
    if cint(doc.cooldown_minutes) < 0:
        doc.cooldown_minutes = 0
    if doc.event == "On Update" and cint(doc.cooldown_minutes) < 5:
        frappe.msgprint(_("On Update fires on every save. A cooldown of at least 5 minutes is recommended."),
                        indicator="orange", alert=True)


def test_trigger(trigger, name, start=0):
    if not set(frappe.get_roles()) & {"Coworker Admin", "System Manager"}:
        frappe.throw(_("Only a Coworker Admin can do this."), frappe.PermissionError)
    t = frappe.get_doc("Coworker Trigger", trigger)
    doc = frappe.get_doc(t.document_type, name)
    try:
        ok = evaluate(t.condition, doc)
    except Exception as e:  # noqa: BLE001
        return _("The condition raised an error: {0}").format(frappe.utils.escape_html(str(e)))
    parameter = common.render_parameter(t.parameter_template, {**doc.as_dict(no_child_table_fields=True),
                                                               "doctype": doc.doctype, "name": doc.name})
    lines = [_("Condition: {0}").format(_("matches") if ok else _("does not match")),
             _("Parameter: {0}").format(frappe.utils.escape_html(parameter) or "-"),
             _("Runs as: {0}").format(_run_as(t, doc))]
    if cint(start):
        run = _fire(t.name, doc, force=True)
        if run:
            lines.append(_("Started run {0}").format(f'<a href="/app/coworker-run/{run}">{run}</a>'))
    return "<br>".join(lines)
