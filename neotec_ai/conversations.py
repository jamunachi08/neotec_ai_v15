"""Saved chats and projects. Every user sees only their own (System Managers can audit via Desk)."""

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

MAX_HISTORY_MESSAGES = 20
MAX_LIST = 50


def _check():
    from neotec_ai.api import _check_access

    _check_access()


def _own(doctype, name):
    if not name or not frappe.db.exists(doctype, name):
        frappe.throw(_("Not found."), frappe.DoesNotExistError)
    owner = frappe.db.get_value(doctype, name, "user")
    if owner != frappe.session.user:
        frappe.throw(_("This belongs to another user."), frappe.PermissionError, title=_("Not Permitted"))
    return frappe.get_doc(doctype, name)


# --------------------------------------------------------------------------------------
# Used by the chat endpoint
# --------------------------------------------------------------------------------------

def load(conversation):
    """Return (doc, model_history) for the user's conversation."""
    doc = _own("Neotec AI Conversation", conversation)
    rows = frappe.get_all(
        "Neotec AI Message",
        filters={"conversation": doc.name},
        fields=["role", "content"],
        order_by="seq desc, creation desc",
        limit=MAX_HISTORY_MESSAGES,
    )
    history = [{"role": r.role, "content": r.content or ""} for r in reversed(rows)]
    while history and history[0]["role"] != "user":
        history.pop(0)
    return doc, history


def project_instructions(project):
    if not project:
        return None, None
    doc = _own("Neotec AI Project", project)
    return doc.title, (doc.instructions or "").strip()


def save_turn(conversation, project, prompt, reply, model_content, report_defs, meta, tokens, context=None):
    """Persist one user + assistant exchange; creates the conversation when needed. Returns its name."""
    if conversation:
        conv = _own("Neotec AI Conversation", conversation)
    else:
        title = " ".join(prompt.split())[:80] or _("New chat")
        conv = frappe.get_doc({
            "doctype": "Neotec AI Conversation",
            "title": title,
            "user": frappe.session.user,
            "project": project or None,
            "message_count": 0,
        }).insert(ignore_permissions=True)
    seq = cint(conv.message_count)
    ctx_dt, ctx_dn = (context or (None, None))
    if ctx_dt and not frappe.db.exists("DocType", ctx_dt):
        ctx_dt = ctx_dn = None
    for role, display, content, reports, m, t in (
        ("user", prompt, prompt, None, None, 0),
        ("assistant", reply, model_content, report_defs or None, meta, tokens),
    ):
        seq += 1
        frappe.get_doc({
            "doctype": "Neotec AI Message",
            "conversation": conv.name,
            "role": role,
            "seq": seq,
            "display": display,
            "content": content,
            "reports": json.dumps(reports, default=str) if reports else None,
            "meta": m,
            "tokens": t,
            "context_doctype": ctx_dt,
            "context_name": ctx_dn,
        }).insert(ignore_permissions=True, ignore_links=True)
    conv.db_set({"message_count": seq, "last_activity": now_datetime()}, update_modified=False)
    return conv.name


# --------------------------------------------------------------------------------------
# Endpoints for the chat UI
# --------------------------------------------------------------------------------------

@frappe.whitelist()
def list_conversations(project=None, search=None, limit=30):
    _check()
    filters = {"user": frappe.session.user}
    if project:
        filters["project"] = project
    if search:
        filters["title"] = ["like", f"%{str(search)[:80]}%"]
    return frappe.get_all(
        "Neotec AI Conversation",
        filters=filters,
        fields=["name", "title", "project", "last_activity", "message_count", "pinned"],
        order_by="pinned desc, last_activity desc",
        limit=min(cint(limit) or 30, MAX_LIST),
    )


@frappe.whitelist()
def get_conversation(name):
    _check()
    doc = _own("Neotec AI Conversation", name)
    rows = frappe.get_all(
        "Neotec AI Message",
        filters={"conversation": doc.name},
        fields=["role", "display", "content", "reports", "meta"],
        order_by="seq asc, creation asc",
        limit=200,
    )
    messages = []
    for r in rows:
        try:
            reports = json.loads(r.reports) if r.reports else []
        except ValueError:
            reports = []
        messages.append({
            "role": r.role,
            "display": r.display or r.content or "",
            "content": r.content or "",
            "saved_reports": reports,
            "meta": r.meta,
        })
    return {"name": doc.name, "title": doc.title, "project": doc.project, "pinned": doc.pinned, "messages": messages}


@frappe.whitelist(methods=["POST"])
def update_conversation(name, title=None, pinned=None, project=None):
    _check()
    doc = _own("Neotec AI Conversation", name)
    values = {}
    if title is not None and title.strip():
        values["title"] = title.strip()[:140]
    if pinned is not None:
        values["pinned"] = 1 if cint(pinned) else 0
    if project is not None:
        if project:
            _own("Neotec AI Project", project)
        values["project"] = project or None
    if values:
        doc.db_set(values)
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def delete_conversation(name):
    _check()
    doc = _own("Neotec AI Conversation", name)
    frappe.db.delete("Neotec AI Message", {"conversation": doc.name})
    frappe.delete_doc("Neotec AI Conversation", doc.name, ignore_permissions=True)
    return {"ok": True}


@frappe.whitelist()
def list_projects():
    _check()
    return frappe.get_all(
        "Neotec AI Project",
        filters={"user": frappe.session.user},
        fields=["name", "title", "instructions"],
        order_by="title asc",
        limit=100,
    )


@frappe.whitelist(methods=["POST"])
def save_project(title, instructions=None, name=None):
    _check()
    title = (title or "").strip()[:140]
    if not title:
        frappe.throw(_("Give the project a title."))
    if len(instructions or "") > 4000:
        frappe.throw(_("Keep project instructions under 4000 characters."))
    if name:
        doc = _own("Neotec AI Project", name)
        doc.db_set({"title": title, "instructions": instructions or ""})
    else:
        doc = frappe.get_doc({
            "doctype": "Neotec AI Project", "title": title, "instructions": instructions or "", "user": frappe.session.user,
        }).insert(ignore_permissions=True)
    return {"name": doc.name, "title": title}


@frappe.whitelist(methods=["POST"])
def delete_project(name):
    _check()
    doc = _own("Neotec AI Project", name)
    frappe.db.set_value("Neotec AI Conversation", {"project": doc.name, "user": frappe.session.user}, "project", None)
    frappe.delete_doc("Neotec AI Project", doc.name, ignore_permissions=True)
    return {"ok": True}


def purge_old(days):
    from frappe.utils import add_days

    if not days or days <= 0:
        return 0
    cutoff = add_days(now_datetime(), -days)
    old = frappe.get_all("Neotec AI Conversation", filters={"last_activity": ["<", cutoff], "pinned": 0}, pluck="name", limit=5000)
    for name in old:
        frappe.db.delete("Neotec AI Message", {"conversation": name})
        frappe.db.delete("Neotec AI Conversation", {"name": name})
    return len(old)
