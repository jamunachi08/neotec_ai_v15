import frappe
from frappe.utils import add_days, now_datetime


def purge_old_logs():
    """Delete AI logs and chat history older than the configured retention periods (0 = keep forever)."""
    days = frappe.db.get_single_value("Neotec Settings", "log_retention_days") or 0
    if days > 0:
        cutoff = add_days(now_datetime(), -days)
        frappe.db.delete("Neotec AI Log", {"creation": ("<", cutoff)})

    chat_days = frappe.db.get_single_value("Neotec Settings", "conversation_retention_days") or 0
    if chat_days > 0:
        from neotec_ai.conversations import purge_old

        purge_old(chat_days)
    frappe.db.commit()
