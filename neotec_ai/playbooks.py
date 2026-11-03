"""Business playbooks: titles/descriptions go in the prompt, full content is loaded on demand."""

import frappe
from frappe.utils import now_datetime

EXAMPLES = [
    {
        "title": "Sales commission (example)",
        "description": "Use when asked about sales commission, incentives or how much a sales person earned.",
        "content": (
            "# Sales commission\n\n"
            "- Commission is earned on **paid** sales invoices only (outstanding_amount = 0), by posting month.\n"
            "- Base = net total excluding tax (base_net_total). Credit notes (is_return = 1) reduce the base.\n"
            "- Rate: 2% up to 100,000 per month, 3% above that.\n"
            "- Use the *Sales Person-wise Transaction Summary* report to split by sales person.\n"
            "- Always show the period, the base and the rate used."
        ),
    },
    {
        "title": "Month-end close checklist (example)",
        "description": "Use when asked about month-end, closing the books, or why figures for a period may still change.",
        "content": (
            "# Month-end close\n\n"
            "1. All sales and purchase invoices for the month are submitted (no drafts dated in the month).\n"
            "2. Bank entries reconciled up to the last day.\n"
            "3. Stock entries posted; run *Stock Balance* and compare with the *Balance Sheet* stock account.\n"
            "4. Depreciation posted.\n"
            "5. Finance closes the period around the 5th of the next month; until then figures are provisional.\n"
            "When reporting a month that is not yet closed, say the figures are provisional."
        ),
    },
]


def accessible(user=None):
    """Enabled playbooks the user may use: [{name, title, description, always_include}]."""
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    rows = frappe.get_all(
        "Neotec Playbook",
        filters={"enabled": 1},
        fields=["name", "title", "description", "always_include"],
        order_by="title asc",
        limit=200,
    )
    if not rows:
        return []
    restricted = {}
    for r in frappe.get_all(
        "Neotec Playbook Role",
        filters={"parenttype": "Neotec Playbook", "parent": ["in", [x.name for x in rows]]},
        fields=["parent", "role"],
    ):
        restricted.setdefault(r.parent, set()).add(r.role)
    return [r for r in rows if r.name not in restricted or restricted[r.name] & roles or "System Manager" in roles]


def resolve(refs, user=None):
    """Match references (names or titles, case-insensitive) to accessible playbooks."""
    pool = accessible(user)
    by_key = {}
    for p in pool:
        by_key[p.name.lower()] = p
        by_key[(p.title or "").lower()] = p
    out = []
    for ref in refs or []:
        p = by_key.get(str(ref).strip().lower())
        if p and p not in out:
            out.append(p)
    return out


def contents(refs, user=None, max_chars=20000):
    found = resolve(refs, user)
    if not found:
        return "No matching playbooks (check the names in the playbook list).", []
    parts, names = [], []
    for p in found:
        doc = frappe.get_doc("Neotec Playbook", p.name)
        parts.append(f"### Playbook {doc.name}: {doc.title}\n{doc.content or ''}")
        names.append(doc.name)
        frappe.db.set_value("Neotec Playbook", doc.name, {
            "use_count": (doc.use_count or 0) + 1, "last_used": now_datetime(),
        }, update_modified=False)
    text = "\n\n".join(parts)
    return text[:max_chars], names


def always_included(user=None):
    rows = [p for p in accessible(user) if p.always_include]
    return [(p, frappe.db.get_value("Neotec Playbook", p.name, "content") or "") for p in rows]


def seed_examples():
    if frappe.db.count("Neotec Playbook"):
        return 0
    for ex in EXAMPLES:
        frappe.get_doc({"doctype": "Neotec Playbook", "enabled": 0, **ex}).insert(ignore_permissions=True)
    return len(EXAMPLES)
