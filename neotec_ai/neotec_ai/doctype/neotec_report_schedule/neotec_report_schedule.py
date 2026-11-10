import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from neotec_ai.bi.schedule import compute_next_run, recipient_list, validate_recipients


class NeotecReportSchedule(Document):
    def validate(self):
        if not frappe.db.exists(self.reference_type, self.reference_name):
            frappe.throw(_("{0} {1} does not exist.").format(_(self.reference_type), self.reference_name))
        if not frappe.has_permission(self.reference_type, "read", doc=self.reference_name):
            frappe.throw(
                _("You can only schedule reports and dashboards you can open."),
                frappe.PermissionError,
                title=_("Not Permitted"),
            )

        self.send_hour = max(0, min(cint(self.send_hour), 23))
        self.day_of_month = max(1, min(cint(self.day_of_month) or 1, 31))

        emails = recipient_list(self.recipients)
        validate_recipients(emails)
        self.recipients = ", ".join(emails)

        if self.enabled and (self.is_new() or self.has_value_changed("frequency") or self.has_value_changed("weekday")
                             or self.has_value_changed("day_of_month") or self.has_value_changed("send_hour")
                             or self.has_value_changed("enabled") or not self.next_run):
            self.next_run = compute_next_run(self)
        if not self.enabled:
            self.next_run = None
