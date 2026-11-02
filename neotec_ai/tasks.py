import frappe
from frappe.utils import add_days, now_datetime


def purge_old_logs():
    """Delete AI logs older than the configured retention period (0 = keep forever)."""
    days = frappe.db.get_single_value("Neotec Settings", "log_retention_days") or 0
    if days <= 0:
        return
    cutoff = add_days(now_datetime(), -days)
    frappe.db.delete("Neotec AI Log", {"creation": ("<", cutoff)})
    frappe.db.commit()
