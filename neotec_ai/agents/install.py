# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
import frappe


def before_install():
    """Roles must exist before DocTypes and Pages that reference them are synced."""
    from neotec_ai.agents.setup.seed import ensure_roles

    ensure_roles()


def after_install():
    from neotec_ai.agents.setup import seed

    seed.run()
    _grant_admins()
    frappe.db.commit()


def after_migrate():
    from neotec_ai.agents.setup import seed

    seed.run()


def _grant_admins():
    """System Managers get the Coworker Admin role so they can open the setup wizard straight away."""
    users = frappe.get_all("Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent")
    for user in set(users):
        if user in ("Guest",) or not frappe.db.get_value("User", user, "enabled"):
            continue
        u = frappe.get_doc("User", user)
        have = {r.role for r in u.roles}
        added = False
        for role in ("Coworker Admin", "Coworker User", "Coworker Approver"):
            if role not in have:
                u.append("roles", {"role": role})
                added = True
        if added:
            u.flags.ignore_permissions = True
            u.save(ignore_permissions=True)
