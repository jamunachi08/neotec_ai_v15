import frappe
from frappe import _
from frappe.model.document import Document


class NeotecDashboard(Document):
    def validate(self):
        for row in self.items:
            if row.item_type == "Report" and not row.report:
                frappe.throw(_("Row {0}: choose a report.").format(row.idx))
            if row.item_type == "Text":
                row.report = None
            if row.date_field and "." not in row.date_field:
                frappe.throw(_("Row {0}: write the date field as 'DocType.fieldname'.").format(row.idx))
