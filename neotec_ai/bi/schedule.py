"""Scheduled e-mail of reports and dashboards.

Each schedule runs *as its owner*: recipients receive exactly the data the owner is allowed to see.
"""

import calendar
import datetime

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from neotec_ai import reports
from neotec_ai.bi import export

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def compute_next_run(doc, after=None):
    after = get_datetime(after or now_datetime())
    hour = max(0, min(int(doc.send_hour or 0), 23))
    candidate = after.replace(hour=hour, minute=0, second=0, microsecond=0)

    if doc.frequency == "Daily":
        if candidate <= after:
            candidate += datetime.timedelta(days=1)
        return candidate

    if doc.frequency == "Weekly":
        target = WEEKDAYS.index(doc.weekday or "Monday")
        days = (target - candidate.weekday()) % 7
        candidate += datetime.timedelta(days=days)
        if candidate <= after:
            candidate += datetime.timedelta(days=7)
        return candidate

    # Monthly
    day = max(1, min(int(doc.day_of_month or 1), 31))
    year, month = candidate.year, candidate.month
    for _i in range(3):
        last = calendar.monthrange(year, month)[1]
        c = candidate.replace(year=year, month=month, day=min(day, last))
        if c > after:
            return c
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return candidate + datetime.timedelta(days=31)


def run_due():
    """Hourly scheduler job."""
    due = frappe.get_all(
        "Neotec Report Schedule",
        filters={"enabled": 1, "next_run": ("<=", now_datetime())},
        pluck="name",
    )
    for name in due:
        try:
            send_schedule(name)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"Neotec AI: scheduled report {name} failed")
            frappe.db.set_value("Neotec Report Schedule", name, {
                "last_error": frappe.get_traceback()[-1000:],
                "next_run": compute_next_run(frappe.get_doc("Neotec Report Schedule", name)),
            })
        frappe.db.commit()


def check_sendable(doc):
    """Re-checked at every send: the owner must still be allowed, recipients must still be allowed."""
    owner = frappe.db.get_value("User", doc.owner, ["enabled"], as_dict=True)
    if not owner or not owner.enabled:
        raise frappe.ValidationError(_("The schedule owner {0} is disabled.").format(doc.owner))
    roles = set(frappe.get_roles(doc.owner))
    if doc.owner != "Administrator" and not roles & {"Neotec AI User", "System Manager"}:
        raise frappe.ValidationError(_("The schedule owner {0} no longer has access to Neotec AI.").format(doc.owner))
    validate_recipients(recipient_list(doc.recipients))


def validate_recipients(emails):
    from frappe.utils import validate_email_address

    if not emails:
        frappe.throw(_("Add at least one recipient."))
    if len(emails) > 50:
        frappe.throw(_("At most 50 recipients."))
    allow_external = frappe.db.get_single_value("Neotec Settings", "allow_external_recipients")
    for email in emails:
        if not validate_email_address(email):
            frappe.throw(_("{0} is not a valid e-mail address.").format(email))
        if not allow_external and not frappe.db.exists(
            "User", {"email": email, "enabled": 1, "user_type": "System User"}
        ):
            frappe.throw(
                _("{0} is not a system user. Only system users can receive scheduled reports "
                  "(an administrator can allow external recipients in Neotec Settings).").format(email),
                title=_("Recipient Not Allowed"),
            )


def send_schedule(name):
    doc = frappe.get_doc("Neotec Report Schedule", name)
    check_sendable(doc)
    previous_user = frappe.session.user
    frappe.set_user(doc.owner)
    try:
        title, reps, subtitle = _collect(doc)
    finally:
        frappe.set_user(previous_user)

    stamp = now_datetime().strftime("%Y-%m-%d")
    base = f"{frappe.scrub(title)[:50] or 'report'}_{stamp}"
    attachments = []
    fmt = doc.attachment_format or "Excel"
    data_reps = [r for r in reps if not r.get("error")]
    if fmt in ("Excel", "Excel + PDF"):
        attachments.append({"fname": f"{base}.xlsx", "fcontent": export.to_xlsx(data_reps)})
    if fmt in ("PDF", "Excel + PDF"):
        attachments.append({"fname": f"{base}.pdf", "fcontent": export.to_pdf(title, reps, subtitle)})
    if fmt == "CSV" and data_reps:
        attachments.append({"fname": f"{base}.csv", "fcontent": export.to_csv(data_reps[0])})

    intro = frappe.utils.escape_html(doc.message or "") .replace("\n", "<br>")
    body = (
        f"<div style='font-family:Arial,sans-serif;font-size:13px'>"
        f"{'<p>' + intro + '</p>' if intro else ''}"
        f"<style>{export.CSS}</style>"
        + "".join(export.report_html(r, max_rows=25, charts=False) for r in reps)
        + f"<p style='color:#888;font-size:11px'>{_('Scheduled by {0} via Neotec AI. Data reflects {0}’s access permissions.').format(frappe.utils.get_fullname(doc.owner))}</p></div>"
    )
    frappe.sendmail(
        recipients=recipient_list(doc.recipients),
        subject=doc.subject or f"{title} - {stamp}",
        message=body,
        attachments=attachments,
        reference_doctype=doc.doctype,
        reference_name=doc.name,
        now=False,
    )
    doc.db_set({"last_sent_on": now_datetime(), "last_error": None, "next_run": compute_next_run(doc)}, update_modified=False)


def _collect(doc):
    if doc.reference_type == "Neotec Dashboard":
        from neotec_ai.bi.api import collect_dashboard

        dash = frappe.get_doc("Neotec Dashboard", doc.reference_name)
        filters = {"timespan": doc.timespan_override} if doc.timespan_override else {"timespan": dash.default_timespan} if dash.default_timespan else None
        return dash.title, collect_dashboard(dash, filters), dash.description
    rep = frappe.get_doc("Neotec AI Report", doc.reference_name)
    definition = rep.get_definition()
    out = reports.safe_run(definition)
    if out.get("ok"):
        return rep.title, [out["report"]], rep.description
    return rep.title, [{"title": rep.title, "error": out.get("message"), "columns": [], "rows": []}], rep.description


def recipient_list(text):
    parts = [p.strip() for p in (text or "").replace(";", ",").replace("\n", ",").split(",")]
    return [p for p in parts if p]


@frappe.whitelist(methods=["POST"])
def send_now(name):
    doc = frappe.get_doc("Neotec Report Schedule", name)
    if not doc.has_permission("write"):
        frappe.throw(_("You can only send schedules you own."), frappe.PermissionError, title=_("Not Permitted"))
    check_sendable(doc)
    frappe.enqueue("neotec_ai.bi.schedule.send_schedule", name=name, queue="short", enqueue_after_commit=True)
    return {"ok": True, "recipients": recipient_list(doc.recipients)}
