# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""One way to send a result anywhere: the ERPNext bell, e-mail, Slack, Microsoft Teams, Google Chat, Telegram or a
generic webhook. Each channel has a minimum severity, so a channel for managers can receive only warnings.

Where a run's result goes:
  * a run started by a routine -> the routine's own delivery settings (bell / e-mail / webhook) and its channels
  * a chain step               -> the chain's channels (intermediate steps only if marked "deliver")
  * any other run              -> the playbook's channels
  * nothing configured         -> the bell of the user the run worked for
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, get_url, md_to_html, now_datetime, strip_html, validate_email_address

from neotec_ai.agents.automation import common

WEBHOOK_TYPES = ("Slack", "Microsoft Teams", "Google Chat", "Generic Webhook")


# ---------------------------------------------------------------- channel controller

def validate_channel(doc):
    if doc.channel_type in WEBHOOK_TYPES and not doc.webhook_url:
        frappe.throw(_("Enter the webhook URL."))
    if doc.channel_type == "Telegram" and not (doc.telegram_bot_token and doc.telegram_chat_id):
        frappe.throw(_("Enter the Telegram bot token and chat ID."))
    if doc.channel_type == "Email" and doc.email_recipients:
        for addr in _split(doc.email_recipients):
            validate_email_address(addr, throw=True)
    if doc.channel_type == "Bell":
        for user in _lines(doc.users):
            if not frappe.db.exists("User", user):
                frappe.throw(_("User {0} does not exist.").format(user))


def send_test(name):
    roles = set(frappe.get_roles())
    if not roles & {"Coworker Admin", "System Manager"}:
        frappe.throw(_("Only a Coworker Admin can do this."), frappe.PermissionError)
    notes = send([name], _("Test from Neotec AI"),
                 _("If you can read this, the channel {0} works.").format(name), "critical", frappe.session.user)
    return "; ".join(notes)


# ---------------------------------------------------------------- helpers

def _split(value):
    return [p.strip() for p in (value or "").replace(";", ",").replace("\n", ",").split(",") if p.strip()]


def _lines(value):
    return [p.strip() for p in (value or "").replace(",", "\n").splitlines() if p.strip()]


def _post(url, payload, headers=None):
    import requests

    resp = requests.post(url, json=payload, timeout=20, headers=headers or {})
    if resp.status_code >= 400:
        raise frappe.ValidationError(f"HTTP {resp.status_code}: {resp.text[:200]}")


def _bell(users, subject, body_html, reference):
    dt, dn = reference or (None, None)
    for user in users:
        if not user or user == "Guest" or not frappe.db.get_value("User", user, "enabled"):
            continue
        frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert",
                        "subject": strip_html(subject)[:140], "email_content": body_html,
                        "document_type": dt, "document_name": dn}).insert(ignore_permissions=True)


def _link(reference):
    if not reference or not reference[0]:
        return ""
    dt, dn = reference
    route = frappe.scrub(dt).replace("_", "-")
    return get_url(f"/app/{route}/{dn}" if dn else f"/app/{route}")


# ---------------------------------------------------------------- sending

def send_one(ch, subject, body, severity, run_as, reference=None):
    icon = common.SEVERITY_ICON.get(severity, "")
    link = _link(reference)
    if ch.channel_type == "Bell":
        _bell(_lines(ch.users) or [run_as], subject, md_to_html(body), reference)
    elif ch.channel_type == "Email":
        recipients = _split(ch.email_recipients) or [frappe.db.get_value("User", run_as, "email")]
        recipients = [r for r in recipients if r][:20]
        if recipients:
            html = md_to_html(body) + (f'<p><a href="{link}">{_("Open in ERPNext")}</a></p>' if link else "")
            frappe.sendmail(recipients=recipients, subject=f"[{severity.upper()}] {subject}", message=html,
                            reference_doctype=reference[0] if reference else None,
                            reference_name=reference[1] if reference else None)
    elif ch.channel_type in ("Slack", "Google Chat"):
        url = ch.get_password("webhook_url")
        text = f"{icon} *{subject}*\n{common.to_chat_markdown(body)}" + (f"\n<{link}|Open in ERPNext>" if link else "")
        _post(url, {"text": text[:39000]})
    elif ch.channel_type == "Microsoft Teams":
        url = ch.get_password("webhook_url")
        _post(url, common.teams_payload(f"{icon} {subject}", body + (f"\n\n{link}" if link else ""), severity))
    elif ch.channel_type == "Telegram":
        token = ch.get_password("telegram_bot_token")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        for part in common.chunk_text(f"{icon} {subject}\n\n{body}" + (f"\n\n{link}" if link else "")):
            _post(url, {"chat_id": ch.telegram_chat_id, "text": part, "disable_web_page_preview": True})
    elif ch.channel_type == "Generic Webhook":
        url = ch.get_password("webhook_url")
        _post(url, {"subject": subject, "body": body, "severity": severity, "link": link,
                    "reference_doctype": reference[0] if reference else None,
                    "reference_name": reference[1] if reference else None, "site": frappe.local.site})


def send(channel_names, subject, body, severity, run_as, reference=None) -> list[str]:
    notes = []
    for name in channel_names:
        if not frappe.db.exists("Coworker Channel", name):
            notes.append(f"{name}: missing")
            continue
        ch = frappe.get_doc("Coworker Channel", name)
        if not cint(ch.enabled):
            notes.append(f"{name}: disabled")
            continue
        if not common.passes_threshold(severity, ch.min_severity):
            notes.append(f"{name}: below {ch.min_severity}")
            continue
        try:
            send_one(ch, subject, body, severity, run_as, reference)
            frappe.db.set_value("Coworker Channel", name, {"last_delivery": now_datetime(), "last_error": None},
                                update_modified=False)
            notes.append(f"{name}: sent")
        except Exception as e:  # noqa: BLE001 - one bad channel must not stop the others
            frappe.db.set_value("Coworker Channel", name, "last_error", str(e)[:500], update_modified=False)
            notes.append(f"{name}: failed ({str(e)[:80]})")
    return notes


# ---------------------------------------------------------------- runs

def _routine_legacy(routine, subject, body, severity, reference):
    """The delivery fields a routine had before channels existed."""
    notes = []
    if cint(routine.deliver_notification):
        _bell([routine.run_as], subject, md_to_html(body), reference)
        notes.append("bell: sent")
    recipients = _split(routine.email_recipients)
    if recipients:
        frappe.sendmail(recipients=recipients[:20], subject=subject, message=md_to_html(body),
                        reference_doctype="Coworker Routine", reference_name=routine.name)
        notes.append("e-mail: queued")
    if routine.webhook_url:
        url = routine.get_password("webhook_url", raise_exception=False)
        if url:
            try:
                _post(url, {"text": f"*{subject}*\n{body}"[:12000]})
                notes.append("webhook: sent")
            except Exception as e:  # noqa: BLE001
                notes.append(f"webhook: failed ({str(e)[:80]})")
    return notes


def deliver_run(run, pb):
    from neotec_ai.agents.automation import chains

    status = run.status
    subject = pb.playbook_name + (f" — {run.parameter}" if run.parameter else "")
    reference = ("Coworker Run", run.name)
    severity = run.severity or pb.default_severity or "info"

    if status in ("Succeeded", "Budget Exceeded"):
        body = run.output or ""
        if status == "Budget Exceeded":
            body = _("The token budget ran out before the run finished. Partial result:") + "\n\n" + body
            severity = "warn"
    elif status == "Nothing to Report":
        if cint(pb.silent_when_empty):
            frappe.db.set_value("Coworker Run", run.name, "delivery_note", "silent: nothing new", update_modified=False)
            return
        body = _("Nothing new to report.")
    elif status in ("Failed", "Waiting Approval"):
        # Failures of automated runs are handled by the health check (issues), not broadcast on every run.
        if run.source == "Manual" or status == "Waiting Approval":
            msg = run.error or _("A person has to approve an action before this run can continue.")
            _bell([run.run_as], f"{subject}: {_(status)}", md_to_html(msg), reference)
            frappe.db.set_value("Coworker Run", run.name, "delivery_note", "bell to requester", update_modified=False)
        return
    else:
        return

    if run.chain and not chains.is_delivering_step(run):
        frappe.db.set_value("Coworker Run", run.name, "delivery_note", "intermediate chain step", update_modified=False)
        return

    notes = []
    if run.routine and frappe.db.exists("Coworker Routine", run.routine):
        routine = frappe.get_doc("Coworker Routine", run.routine)
        notes += _routine_legacy(routine, subject, body, severity, reference)
        notes += send([r.channel for r in routine.channels], subject, body, severity, run.run_as, reference)
    else:
        rows = []
        if run.chain and frappe.db.exists("Coworker Chain", run.chain):
            rows = [r.channel for r in frappe.get_doc("Coworker Chain", run.chain).channels]
        if not rows:
            rows = [r.channel for r in pb.channels]
        if rows:
            notes += send(rows, subject, body, severity, run.run_as, reference)
        else:
            _bell([run.run_as], subject, md_to_html(body), reference)
            notes.append("bell: sent")
    frappe.db.set_value("Coworker Run", run.name, {
        "delivered": 1 if any(n.endswith(("sent", "queued")) for n in notes) else 0,
        "delivery_note": "; ".join(notes)[:1000]}, update_modified=False)


def routine_channels(routine, subject, body):
    """Prompt routines (the 1.0 kind) can also use channels."""
    if routine.get("channels"):
        send([r.channel for r in routine.channels], subject, body, "info", routine.run_as,
             ("Coworker Routine", routine.name))
