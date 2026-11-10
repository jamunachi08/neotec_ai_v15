# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Routines: on a schedule, as the routine's owner, run one of
  * a prompt (an instruction to a coworker; the answer goes to the bell, e-mail, a webhook and channels),
  * a playbook (a reusable task with an output contract, see automation/playbooks.py), or
  * a chain (several playbooks in sequence, see automation/chains.py).

Safety: 15-minute floor, a per-user cap on enabled routines, read-and-notify only (policy pack), and
automatic disabling after repeated failures so a broken routine does not burn model spend.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, cint, get_datetime, now_datetime, strip_html

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def compute_next_run(doc, after=None):
    after = get_datetime(after or now_datetime())
    freq = doc.frequency
    if freq == "Every 15 Minutes":
        return add_to_date(after, minutes=15)
    if freq == "Hourly":
        return add_to_date(after, hours=1)
    if freq == "Cron":
        from croniter import croniter

        if not doc.cron_expression:
            frappe.throw(_("Enter a cron expression."))
        nxt = croniter(doc.cron_expression, after).get_next(type(after))
        if (nxt - after).total_seconds() < 15 * 60:
            nxt2 = croniter(doc.cron_expression, nxt).get_next(type(after))
            if (nxt2 - nxt).total_seconds() < 15 * 60:
                frappe.throw(_("Routines may run at most every 15 minutes."))
        return nxt
    t = str(doc.run_time or "07:00:00")
    hh, mm = (int(x) for x in t.split(":")[:2])
    candidate = get_datetime(after).replace(hour=hh, minute=mm, second=0, microsecond=0)
    if freq == "Daily":
        return candidate if candidate > after else add_days(candidate, 1)
    if freq == "Weekly":
        target = WEEKDAYS.index(doc.weekday or "Sunday")
        delta = (target - candidate.weekday()) % 7
        candidate = add_days(candidate, delta)
        return candidate if candidate > after else add_days(candidate, 7)
    if freq == "Monthly":
        day = min(max(cint(doc.day_of_month) or 1, 1), 28)
        candidate = candidate.replace(day=day)
        if candidate <= after:
            month = candidate.month % 12 + 1
            year = candidate.year + (1 if candidate.month == 12 else 0)
            candidate = candidate.replace(year=year, month=month)
        return candidate
    return add_days(after, 1)


def tick():
    """Every five minutes: queue routines that are due."""
    from neotec_ai.agents.takeover import legacy_installed

    if legacy_installed():
        return  # the old Coworker app still runs these until it is uninstalled
    s = frappe.get_cached_doc("Coworker Settings")
    if not s.enabled:
        return
    due = frappe.get_all("Coworker Routine", filters={"enabled": 1, "next_run": ["<=", now_datetime()]},
                         pluck="name", limit_page_length=50)
    for name in due:
        frappe.db.set_value("Coworker Routine", name, "next_run",
                            compute_next_run(frappe.get_doc("Coworker Routine", name)), update_modified=False)
        frappe.enqueue("neotec_ai.agents.routines.run_routine", queue="long", timeout=1500, routine=name,
                       enqueue_after_commit=True)
    frappe.db.commit()


def run_routine(routine: str, manual: bool = False):
    from neotec_ai.agents.engine import runner

    doc = frappe.get_doc("Coworker Routine", routine)
    frappe.set_user(doc.run_as)
    if (doc.get("target") or "Prompt") != "Prompt":
        return _run_automation(doc, manual)
    try:
        conv = doc.conversation if doc.conversation and frappe.db.exists("Coworker Conversation", doc.conversation) else None
        if not conv:
            conv = frappe.get_doc({"doctype": "Coworker Conversation", "coworker": doc.coworker, "user": doc.run_as,
                                   "title": f"Routine: {doc.routine_name}"[:80], "channel": "Routine",
                                   "routine": doc.name, "status": "Idle"}).insert(ignore_permissions=True).name
            frappe.db.set_value("Coworker Routine", doc.name, "conversation", conv, update_modified=False)
        stamp = now_datetime().strftime("%Y-%m-%d %H:%M")
        runner.add_message(conv, "user", f"[Scheduled run {stamp}] {doc.prompt}", status="ok")
        frappe.db.commit()
        answer = runner.run_once(conv)
        blocks = _latest_blocks(conv)
        deliver(doc, answer, blocks, conv)
        frappe.db.set_value("Coworker Routine", doc.name, {
            "last_run": now_datetime(), "last_status": "Succeeded", "consecutive_failures": 0,
            "last_result": (answer or "")[:5000]}, update_modified=False)
        frappe.db.commit()
    except Exception as e:  # noqa: BLE001
        frappe.db.rollback()
        _record_failure(doc, e)
        if manual:
            raise


def _run_automation(doc, manual=False):
    """Playbook and chain routines. The run record carries the result; delivery uses the routine's settings."""
    from neotec_ai.agents.automation import chains, playbooks

    try:
        if doc.target == "Playbook":
            run = playbooks.start_run(doc.playbook, doc.parameter, source="Routine", run_as=doc.run_as,
                                      routine=doc.name, enqueue=False)
            frappe.db.commit()
            playbooks.execute_run(run)
        else:
            run = chains.start(doc.chain, doc.parameter, source="Routine", run_as=doc.run_as, routine=doc.name,
                               inline=True)
        status, error = frappe.db.get_value("Coworker Run", run, ["status", "error"])
        if status in ("Failed", "Budget Exceeded"):
            raise RuntimeError(error or status)
        frappe.db.set_value("Coworker Routine", doc.name, {
            "last_run": now_datetime(), "last_status": "Succeeded", "consecutive_failures": 0,
            "last_run_record": run,
            "last_result": (frappe.db.get_value("Coworker Run", run, "output") or status)[:5000]},
            update_modified=False)
        frappe.db.commit()
    except Exception as e:  # noqa: BLE001
        frappe.db.rollback()
        _record_failure(doc, e)
        if manual:
            raise


def _record_failure(doc, e):
    failures = cint(frappe.db.get_value("Coworker Routine", doc.name, "consecutive_failures")) + 1
    limit = cint(frappe.get_cached_doc("Coworker Settings").max_routine_failures) or 5
    values = {"last_run": now_datetime(), "last_status": "Failed", "consecutive_failures": failures,
              "last_result": str(e)[:2000]}
    if failures >= limit:
        values["enabled"] = 0
        _bell(doc.run_as, _("Routine '{0}' was switched off after {1} failures in a row.").format(
            doc.routine_name, failures), str(e)[:500], doc.name)
    frappe.db.set_value("Coworker Routine", doc.name, values, update_modified=False)
    frappe.db.commit()


def _latest_blocks(conv):
    rows = frappe.get_all("Coworker Message", filters={"conversation": conv, "blocks": ["is", "set"]},
                          fields=["blocks", "creation"], order_by="seq desc", limit_page_length=1)
    if rows and rows[0].creation >= add_to_date(now_datetime(), minutes=-30):
        try:
            return json.loads(rows[0].blocks)
        except ValueError:
            return None
    return None


def _blocks_to_text(blocks) -> str:
    if not blocks:
        return ""
    lines = []
    for b in blocks.get("blocks") or []:
        if b["type"] == "kpis":
            lines += [f"{i['label']}: {i['value']}" for i in b["items"]]
        elif b["type"] == "table":
            lines.append(" | ".join(b["columns"]))
            lines += [" | ".join(r) for r in b["rows"][:25]]
        elif b["type"] in ("text", "callout"):
            lines.append(b["text"])
    return "\n".join(lines)


def _bell(user, subject, body, routine=None):
    frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert",
                    "subject": strip_html(subject)[:140], "email_content": body,
                    "document_type": "Coworker Routine" if routine else None,
                    "document_name": routine}).insert(ignore_permissions=True)


def deliver(doc, answer, blocks, conv):
    extra = _blocks_to_text(blocks)
    body = (answer or "").strip()
    if extra:
        body = f"{body}\n\n{extra}" if body else extra
    subject = f"{doc.routine_name}"
    if doc.deliver_notification:
        _bell(doc.run_as, subject, frappe.utils.md_to_html(body), doc.name)
    recipients = [r.strip() for r in (doc.email_recipients or "").replace(";", ",").split(",") if r.strip()]
    if recipients:
        frappe.sendmail(recipients=recipients[:20], subject=subject, message=frappe.utils.md_to_html(body),
                        reference_doctype="Coworker Routine", reference_name=doc.name)
    if doc.webhook_url:
        url = doc.get_password("webhook_url", raise_exception=False)
        if url:
            import requests

            payload = {"text": f"*{subject}*\n{body}"[:12000]}
            requests.post(url, json=payload, timeout=20)
    from neotec_ai.agents.automation import delivery

    delivery.routine_channels(doc, subject, body)


@frappe.whitelist()
def run_now(routine):
    doc = frappe.get_doc("Coworker Routine", routine)
    doc.check_permission("write")
    frappe.enqueue("neotec_ai.agents.routines.run_routine", queue="long", timeout=1500, routine=routine,
                   manual=False, enqueue_after_commit=True)
    return {"queued": True}


def validate_routine(doc):
    target = doc.get("target") or "Prompt"
    if target == "Playbook":
        if not doc.playbook:
            frappe.throw(_("Choose the playbook to run."))
        doc.coworker = frappe.db.get_value("Coworker Playbook", doc.playbook, "coworker")
    elif target == "Chain":
        if not doc.chain:
            frappe.throw(_("Choose the chain to run."))
        first = frappe.get_all("Coworker Chain Step", filters={"parent": doc.chain, "parenttype": "Coworker Chain"},
                               pluck="playbook", order_by="idx asc", limit_page_length=1)
        if first:
            doc.coworker = frappe.db.get_value("Coworker Playbook", first[0], "coworker")
    elif not (doc.prompt or "").strip():
        frappe.throw(_("Write the instruction for the coworker."))
    if doc.frequency == "Cron":
        compute_next_run(doc)
    s = frappe.get_cached_doc("Coworker Settings")
    if doc.enabled:
        cap = cint(s.max_routines_per_user) or 20
        others = frappe.db.count("Coworker Routine", {"run_as": doc.run_as, "enabled": 1, "name": ["!=", doc.name]})
        if others >= cap:
            frappe.throw(_("{0} already has {1} enabled routines, the maximum.").format(doc.run_as, cap))
    if doc.run_as != frappe.session.user and not set(frappe.get_roles()) & {"Coworker Admin", "System Manager"}:
        frappe.throw(_("You can only create routines that run as yourself."))
    if doc.is_new() or doc.has_value_changed("frequency") or doc.has_value_changed("run_time") \
            or doc.has_value_changed("weekday") or doc.has_value_changed("day_of_month") \
            or doc.has_value_changed("cron_expression") or not doc.next_run:
        doc.next_run = compute_next_run(doc)
