# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
import frappe


def boot_session(bootinfo):
    if frappe.session.user == "Guest":
        return
    try:
        s = frappe.get_cached_doc("Coworker Settings")
    except Exception:  # noqa: BLE001 - before first migrate
        return
    roles = set(frappe.get_roles())
    bootinfo.neotec_ai_agents = {
        "enabled": int(s.enabled or 0),
        "setup_completed": int(s.setup_completed or 0),
        "show_form_button": int(s.show_form_button or 0),
        "can_use": int(bool(roles & {"Coworker User", "Coworker Admin", "System Manager"})),
        "is_admin": int(bool(roles & {"Coworker Admin", "System Manager"})),
        "legacy": int("neotec_coworker" in (frappe.get_installed_apps() or [])),
    }
