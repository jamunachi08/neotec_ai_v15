"""v3.1: ERPNext reports, playbooks, saved chats, sensitive-field block.

New Single fields read as empty on existing sites (their row already exists), so set them explicitly.
"""

import frappe

from neotec_ai.install import seed_erp_reports, seed_playbooks, seed_sample_questions


def execute():
    values = {
        "enable_erp_reports": 1,
        "erp_report_access": "Listed Reports Only",
        "enable_approvals": 1,
        "catalog_mode": "Auto",
        "conversation_retention_days": 180,
    }
    current = frappe.db.get_single_value("Neotec Settings", "max_query_rounds") or 0
    if current <= 3:  # the old default; tools now need more steps
        values["max_query_rounds"] = 6
    for field, value in values.items():
        if field == "max_query_rounds" or not frappe.db.get_single_value("Neotec Settings", field):
            frappe.db.set_single_value("Neotec Settings", field, value)
    frappe.clear_document_cache("Neotec Settings", "Neotec Settings")

    seed_erp_reports()
    seed_playbooks()
    seed_sample_questions()

    # Fields that the new sensitive-field rules block are disabled in existing data sources.
    from neotec_ai.security import is_sensitive_field

    for row in frappe.get_all("Neotec Data Field", filters={"parenttype": "Neotec Data Source", "enabled": 1},
                              fields=["name", "parent", "fieldname"]):
        if is_sensitive_field(row.fieldname, row.parent):
            frappe.db.set_value("Neotec Data Field", row.name, "enabled", 0, update_modified=False)
