# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Tools that change data. All run as the user, with the user's permissions, after the gateway's decision.

Coworkers create and edit drafts; they never cancel or delete. Submitting exists as a tool so an
administrator can choose to allow it for specific cases, but the starter policy pack denies it.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, strip_html

from neotec_ai.agents.engine.registry import tool
from neotec_ai.agents.tools._common import ensure_doctype, jarg

S = {"type": "string"}
PROTECTED = {"name", "docstatus", "owner", "creation", "modified", "modified_by", "amended_from", "idx",
             "doctype", "parent", "parentfield", "parenttype"}
NEVER_CREATE = {"User", "Role", "DocType", "Custom Field", "Property Setter", "Server Script", "Client Script",
                "System Settings", "Has Role", "User Permission", "DocShare", "File",
                "Coworker Policy Rule", "Coworker Settings", "Coworker Provider", "AI Coworker",
                "Coworker Approval", "Coworker Action Log", "Coworker MCP Server", "Coworker Tool"}


def _values(values) -> dict:
    values = jarg(values, {}) or {}
    if not isinstance(values, dict):
        frappe.throw(_("values must be a JSON object of fieldname: value."))
    return {k: v for k, v in values.items() if k not in PROTECTED}


def _link(doc):
    return {"doctype": doc.doctype, "name": doc.name, "url": frappe.utils.get_url_to_form(doc.doctype, doc.name)}


@tool("create_draft_document", "Create a draft",
      "Create a new document as a DRAFT (never submitted), e.g. a Quotation, Sales Order, Material Request, "
      "ToDo or Lead. Child tables are lists of row objects, e.g. {\"items\":[{\"item_code\":\"X\",\"qty\":2}]}. "
      "Use describe_doctype first to get field names.",
      {"doctype": S, "values": {"type": "string", "description": "JSON object of field values"},
       "__required__": ["doctype", "values"]}, category="Actions", is_write=True, risk="Medium")
def create_draft_document(doctype, values):
    if doctype in NEVER_CREATE:
        raise frappe.PermissionError(_("Coworkers cannot create {0} records.").format(doctype))
    meta = ensure_doctype(doctype, "create")
    if meta.istable or meta.issingle:
        frappe.throw(_("{0} cannot be created on its own.").format(doctype))
    doc = frappe.get_doc({"doctype": doctype, **_values(values)})
    doc.docstatus = 0
    doc.insert()
    doc.add_comment("Info", _("Drafted by a Neotec coworker for {0}.").format(frappe.session.user))
    return {"created": True, **_link(doc), "status": "Draft"}


@tool("update_draft_document", "Edit a draft",
      "Change fields on a DRAFT document. Submitted or cancelled documents cannot be edited.",
      {"doctype": S, "name": S, "values": {"type": "string", "description": "JSON object of field values"},
       "__required__": ["doctype", "name", "values"]}, category="Actions", is_write=True, risk="Medium")
def update_draft_document(doctype, name, values):
    if doctype in NEVER_CREATE:
        raise frappe.PermissionError(_("Coworkers cannot change {0} records.").format(doctype))
    ensure_doctype(doctype, "write")
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("{0} {1} is not a draft, so it cannot be edited.").format(doctype, name))
    vals = _values(values)
    for key, val in vals.items():
        if isinstance(val, list) and doc.meta.get_field(key) and doc.meta.get_field(key).fieldtype == "Table":
            doc.set(key, [])
            for row in val:
                doc.append(key, row)
        else:
            doc.set(key, val)
    doc.save()
    return {"updated": True, **_link(doc), "fields": sorted(vals)}


@tool("add_comment", "Comment on a document",
      "Add a comment to a document's timeline.",
      {"doctype": S, "name": S, "text": S, "__required__": ["doctype", "name", "text"]},
      category="Actions", is_write=True, risk="Low")
def add_comment(doctype, name, text):
    ensure_doctype(doctype)
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    c = doc.add_comment("Comment", strip_html(text)[:4000], comment_email=frappe.session.user)
    return {"commented": True, **_link(doc), "comment": c.name}


@tool("create_todo", "Assign a follow-up",
      "Assign a document to a user as a ToDo with a description and optional due date.",
      {"doctype": S, "name": S, "assign_to": {"type": "string", "description": "User e-mail"},
       "description": S, "date": {"type": "string", "description": "YYYY-MM-DD"},
       "__required__": ["doctype", "name", "assign_to", "description"]},
      category="Actions", is_write=True, risk="Low")
def create_todo(doctype, name, assign_to, description, date=None):
    from frappe.desk.form.assign_to import add

    ensure_doctype(doctype)
    frappe.get_doc(doctype, name).check_permission("read")
    if not frappe.db.get_value("User", assign_to, "enabled"):
        frappe.throw(_("{0} is not an active user.").format(assign_to))
    add({"doctype": doctype, "name": name, "assign_to": [assign_to], "description": strip_html(description)[:2000],
         "date": str(getdate(date)) if date else None})
    return {"assigned": True, "to": assign_to, "doctype": doctype, "name": name}


@tool("notify_user", "Notify a user",
      "Send an in-app ERPNext notification to a user (bell icon). Optionally link a document.",
      {"user": S, "subject": S, "message": S, "doctype": S, "name": S, "__required__": ["user", "subject"]},
      category="Actions", is_write=True, risk="Low")
def notify_user(user, subject, message=None, doctype=None, name=None):
    if not frappe.db.get_value("User", user, "enabled"):
        frappe.throw(_("{0} is not an active user.").format(user))
    if doctype and name:
        frappe.get_doc(doctype, name).check_permission("read")
    frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert",
                    "subject": strip_html(subject)[:140], "email_content": strip_html(message or "")[:4000],
                    "document_type": doctype, "document_name": name,
                    "from_user": frappe.session.user}).insert(ignore_permissions=True)
    return {"notified": user}


@tool("send_email", "Send an e-mail",
      "Send an e-mail through ERPNext's outgoing account, optionally linked to a document (appears in its timeline).",
      {"recipients": {"type": "string", "description": "Comma separated e-mails"}, "subject": S,
       "message": {"type": "string", "description": "Plain text or simple HTML"},
       "reference_doctype": S, "reference_name": S, "__required__": ["recipients", "subject", "message"]},
      category="Actions", is_write=True, risk="High")
def send_email(recipients, subject, message, reference_doctype=None, reference_name=None):
    recips = [r.strip() for r in str(recipients).replace(";", ",").split(",") if r.strip()]
    if not recips or len(recips) > 20:
        frappe.throw(_("Give between 1 and 20 recipients."))
    if reference_doctype and reference_name:
        frappe.get_doc(reference_doctype, reference_name).check_permission("read")
    frappe.sendmail(recipients=recips, subject=strip_html(subject)[:200], message=message,
                    reference_doctype=reference_doctype, reference_name=reference_name, now=False)
    return {"queued": True, "recipients": recips}


@tool("submit_document", "Submit a document",
      "Submit a draft document. Denied by the starter policy pack; an administrator must allow it explicitly.",
      {"doctype": S, "name": S, "__required__": ["doctype", "name"]},
      category="Actions", is_write=True, risk="High")
def submit_document(doctype, name):
    ensure_doctype(doctype, "submit")
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("submit")
    if doc.docstatus != 0:
        frappe.throw(_("Only drafts can be submitted."))
    doc.submit()
    return {"submitted": True, **_link(doc)}


@tool("approval_status", "Check an approval",
      "Check whether an action you requested earlier (CAP-xxxxx) was approved, rejected or executed, and its result.",
      {"approval": S, "__required__": ["approval"]}, category="Actions")
def approval_status(approval):
    doc = frappe.get_doc("Coworker Approval", approval)
    if doc.requested_by != frappe.session.user and not frappe.has_permission("Coworker Approval", "read", doc):
        raise frappe.PermissionError(_("Not your request."))
    return {"approval": doc.name, "status": doc.status, "summary": doc.summary, "decided_by": doc.decided_by,
            "comment": doc.decision_comment, "result": (doc.result_preview or "")[:2000]}
