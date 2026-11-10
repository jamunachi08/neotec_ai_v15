# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Live Briefs: a note that keeps itself current.

A brief has an objective ("overdue receivables above 50,000 SAR, newest first") and a coworker. On its
schedule, or when a chosen document changes, the coworker re-reads the data and rewrites the brief, saying
what changed since last time. Briefs are read-only: the coworker can look, never change anything. They run as
the brief's owner, so they show only what that user may see.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

DT = "Neotec Live Brief"
EVENTS = {"after_insert": "After Insert", "on_update": "On Update", "on_submit": "On Submit", "on_cancel": "On Cancel"}
INDEX_KEY = "neotec_ai:brief_index"
CHANGES = "CHANGES:"


def compute_next_run(doc, after=None):
    if doc.frequency in ("On Document Event", "Manual"):
        return None
    from neotec_ai.agents.routines import compute_next_run as routine_next

    proxy = frappe._dict(frequency=doc.frequency, run_time=doc.run_time, weekday=doc.weekday,
                         cron_expression=doc.cron_expression, day_of_month=1)
    return routine_next(proxy, after)


def _cache():
    c = frappe.cache
    return c() if callable(c) and not hasattr(c, "get_value") else c


def clear_index(*_args, **_kw):
    try:
        _cache().delete_value(INDEX_KEY)
    except Exception:  # noqa: BLE001
        pass


def _index() -> dict:
    c = _cache()
    idx = c.get_value(INDEX_KEY)
    if idx is None:
        idx = {}
        if frappe.db.table_exists(DT):
            for r in frappe.get_all(DT, filters={"enabled": 1, "frequency": "On Document Event"},
                                    fields=["name", "trigger_doctype", "trigger_event"]):
                if r.trigger_doctype:
                    idx.setdefault(r.trigger_doctype, []).append([r.name, r.trigger_event])
        c.set_value(INDEX_KEY, idx, expires_in_sec=600)
    return idx


def on_event(doc, method=None):
    """doc_events hook: queue briefs that refresh when this DocType changes. Never blocks the save."""
    try:
        if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.get("ntc_coworker"):
            return
        event = EVENTS.get(method)
        if not event or doc.doctype == DT:
            return
        for name, ev in _index().get(doc.doctype, []):
            if ev != event:
                continue
            last, gap = frappe.db.get_value(DT, name, ["last_run_at", "min_minutes_between"]) or (None, 30)
            if last and get_datetime(last) > add_to_date(now_datetime(), minutes=-(cint(gap) or 30)):
                continue
            frappe.enqueue("neotec_ai.briefs.run_brief", queue="long", timeout=1500, brief=name,
                           enqueue_after_commit=True, job_id=f"ntc-brief::{name}", deduplicate=True)
    except Exception:  # noqa: BLE001
        frappe.log_error(title="Neotec AI: live brief trigger failed")


def tick():
    """Every five minutes: refresh briefs that are due."""
    if not frappe.db.table_exists(DT):
        return
    for name in frappe.get_all(DT, filters={"enabled": 1, "next_run": ["<=", now_datetime()],
                                            "frequency": ["not in", ["On Document Event", "Manual"]]},
                               pluck="name", limit_page_length=50):
        doc = frappe.get_doc(DT, name)
        frappe.db.set_value(DT, name, "next_run", compute_next_run(doc), update_modified=False)
        frappe.enqueue("neotec_ai.briefs.run_brief", queue="long", timeout=1500, brief=name,
                       enqueue_after_commit=True)
    frappe.db.commit()


def build_prompt(objective: str, body: str | None, now: str) -> str:
    previous = (body or "").strip()
    return (f"[Live brief refresh {now}]\nObjective of this brief:\n{objective.strip()}\n\n"
            + (f"The brief as it stands:\n<<<\n{previous[:12000]}\n>>>\n\n" if previous else
               "This is the first version of the brief.\n\n")
            + "Use your tools to read the current data and rewrite the whole brief in Markdown: short, factual, "
              "figures with currency, tables where useful. Change nothing in the system. Start your answer with "
              f"one line '{CHANGES} <what changed since the previous version, or 'first version'>' and then the "
              "brief itself.")


def split_answer(answer: str) -> tuple[str, str]:
    text = (answer or "").strip()
    if text.upper().startswith(CHANGES):
        first, _sep, rest = text.partition("\n")
        return first[len(CHANGES):].strip()[:500], rest.strip()
    return "", text


def run_brief(brief: str, manual: bool = False):
    from neotec_ai.agents.engine import runner

    doc = frappe.get_doc(DT, brief)
    user = doc.run_as or doc.owner
    frappe.set_user(user)
    frappe.db.set_value(DT, brief, {"last_status": "Running", "last_error": None}, update_modified=False)
    frappe.db.commit()
    try:
        conv = doc.conversation if doc.conversation and frappe.db.exists("Coworker Conversation", doc.conversation) else None
        if not conv:
            conv = frappe.get_doc({"doctype": "Coworker Conversation", "coworker": doc.coworker, "user": user,
                                   "title": f"Brief: {doc.brief_title}"[:80], "channel": "Brief", "status": "Idle",
                                   "permission_mode": "Read Only"}).insert(ignore_permissions=True).name
        frappe.db.set_value("Coworker Conversation", conv, "permission_mode", "Read Only", update_modified=False)
        runner.add_message(conv, "user", build_prompt(doc.objective, doc.body, now_datetime().strftime("%Y-%m-%d %H:%M")),
                           status="ok")
        frappe.db.commit()
        answer = runner.run_once(conv)
        summary, body = split_answer(answer)
        tokens = cint(frappe.db.get_value("Coworker Conversation", conv, "total_tokens"))
        frappe.db.set_value(DT, brief, {"body": body, "last_summary": summary, "last_run_at": now_datetime(),
                                        "last_status": "Succeeded", "conversation": conv, "total_tokens": tokens},
                            update_modified=False)
        frappe.db.commit()
        frappe.publish_realtime("neotec_ai_brief", {"brief": brief}, user=user)
    except Exception as e:  # noqa: BLE001
        frappe.db.rollback()
        frappe.db.set_value(DT, brief, {"last_status": "Failed", "last_error": str(e)[:1000],
                                        "last_run_at": now_datetime()}, update_modified=False)
        frappe.db.commit()
        if manual:
            raise


@frappe.whitelist(methods=["POST"])
def refresh_now(brief: str):
    doc = frappe.get_doc(DT, brief)
    doc.check_permission("write")
    frappe.enqueue("neotec_ai.briefs.run_brief", queue="long", timeout=1500, brief=brief, enqueue_after_commit=True)
    return {"queued": True}
