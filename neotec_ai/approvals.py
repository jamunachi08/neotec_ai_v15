"""'What needs my approval?' — open workflow approvals the current user can actually act on."""

from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, get_url_to_form, nowdate

from neotec_ai.security import is_blocked_doctype

MAX_SCAN = 500
MAX_DETAIL = 25


def _open_actions(user, roles, doctype=None):
    base = [["status", "=", "Open"]]
    if doctype:
        base.append(["reference_doctype", "=", doctype])
    names = set()
    if roles:  # open actions whose permitted roles include one of the user's roles (child-table filter)
        names |= set(frappe.get_all(
            "Workflow Action",
            filters=base + [["Workflow Action Permitted Role", "role", "in", list(roles)]],
            pluck="name",
            limit=MAX_SCAN,
        ))
    names |= set(frappe.get_all("Workflow Action", filters=base + [["user", "=", user]], pluck="name", limit=MAX_SCAN))
    filters = {"status": "Open"}
    if doctype:
        filters["reference_doctype"] = doctype
    if not names:
        return []
    return frappe.get_all(
        "Workflow Action",
        filters={**filters, "name": ["in", list(names)]},
        fields=["name", "reference_doctype", "reference_name", "workflow_state", "modified"],
        order_by="modified desc",
        limit=MAX_SCAN,
    )


def _readable(actions, user):
    """Keep one action per document, only for documents the user may read (User Permissions applied)."""
    by_doctype, seen = {}, set()
    for a in actions:
        key = (a.reference_doctype, a.reference_name)
        if key in seen or is_blocked_doctype(a.reference_doctype):
            continue
        seen.add(key)
        by_doctype.setdefault(a.reference_doctype, []).append(a)
    keep = []
    for dt, rows in by_doctype.items():
        if not frappe.db.exists("DocType", dt):
            continue
        try:
            visible = set(frappe.get_list(dt, filters={"name": ["in", [r.reference_name for r in rows]]}, pluck="name", user=user))
        except frappe.PermissionError:
            frappe.clear_last_message()
            continue
        keep += [r for r in rows if r.reference_name in visible]
    keep.sort(key=lambda r: r.modified, reverse=True)
    return keep


def pending(doctype=None, limit=MAX_DETAIL, with_actions=True):
    """Returns {"count": n, "items": [...]} for the current user."""
    user = frappe.session.user
    roles = set(frappe.get_roles(user)) - {"All", "Guest"}
    if not frappe.db.exists("DocType", "Workflow Action"):
        return {"count": 0, "items": []}
    rows = _readable(_open_actions(user, roles, doctype), user)

    items = []
    if with_actions:
        from frappe.model.workflow import get_transitions

        for r in rows:
            if len(items) >= limit:
                break
            try:
                doc = frappe.get_doc(r.reference_doctype, r.reference_name)
                actions = sorted({t.get("action") for t in get_transitions(doc) if t.get("action")})
            except Exception:
                frappe.clear_last_message()
                continue
            if not actions:
                continue  # nothing this user can do on it
            meta = frappe.get_meta(r.reference_doctype)
            title = doc.get(meta.title_field) if meta.title_field else None
            item = {
                "doctype": r.reference_doctype,
                "name": r.reference_name,
                "title": title if title and title != r.reference_name else None,
                "state": doc.get("workflow_state") or r.workflow_state,
                "actions": actions,
                "waiting_since": str(r.modified)[:16],
                "owner": doc.owner,
                "url": get_url_to_form(r.reference_doctype, r.reference_name),
            }
            for f in ("grand_total", "base_grand_total", "total_amount", "posting_date", "transaction_date", "party_name", "customer", "supplier", "employee_name"):
                if meta.get_field(f) and doc.get(f) not in (None, "") and doc.has_permlevel_access_to(f):
                    item[f] = doc.get(f)
            items.append(item)
    return {"count": len(rows), "items": items}


def describe_for_ai(doctype=None):
    import json

    res = pending(doctype)
    if not res["count"]:
        return "The user has no open workflow approvals."
    return (
        f"Open approvals for the user: {res['count']} document(s). Details of the first {len(res['items'])} "
        f"the user can act on (state, allowed actions, link):\n" + json.dumps(res["items"], default=str)
        + "\nList them in a short table with links. The user approves in Desk; you cannot approve for them."
    )


def needs_you():
    """Small counts for the chat home: approvals and overdue to-dos."""
    out = []
    settings = frappe.get_cached_doc("Neotec Settings")
    if cint(settings.get("enable_approvals")) and frappe.db.exists("DocType", "Workflow Action"):
        n = pending(with_actions=False)["count"]
        if n:
            out.append({"key": "approvals", "count": n,
                        "label": _("{0} document(s) awaiting your approval").format(n),
                        "question": _("What needs my approval?")})
    todo = frappe.db.count("ToDo", {"allocated_to": frappe.session.user, "status": "Open", "date": ["<", nowdate()]})
    if todo:
        out.append({"key": "todos", "count": todo,
                    "label": _("{0} overdue to-do(s) assigned to you").format(todo),
                    "url": "/app/todo?status=Open&allocated_to=" + quote(frappe.session.user)})
    return out
