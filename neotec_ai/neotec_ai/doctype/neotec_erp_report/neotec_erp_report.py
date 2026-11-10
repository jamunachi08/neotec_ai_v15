import json

import frappe
from frappe import _
from frappe.model.document import Document

from neotec_ai.erp_reports import BLOCKED_MODULES, REPORT_TYPES
from neotec_ai.security import is_blocked_doctype


class NeotecERPReport(Document):
    def validate(self):
        row = frappe.db.get_value("Report", self.report, ["report_type", "ref_doctype", "module"], as_dict=True)
        if not row:
            frappe.throw(_("Report {0} does not exist.").format(self.report))
        if row.report_type not in REPORT_TYPES:
            frappe.throw(_("Only Script and Query reports can be used. For Report Builder reports, add their DocType to the Data Dictionary instead."))
        if is_blocked_doctype(row.ref_doctype) or row.module in BLOCKED_MODULES:
            frappe.throw(_("Reports on security or system data cannot be used by the AI."))
        if self.default_filters:
            try:
                value = json.loads(self.default_filters)
            except ValueError:
                frappe.throw(_("House Default Filters must be valid JSON."))
            if not isinstance(value, dict):
                frappe.throw(_("House Default Filters must be a JSON object."))
            self.default_filters = json.dumps(value, indent=1)

    def on_update(self):
        cache = frappe.cache if hasattr(frappe.cache, "delete_value") else frappe.cache()
        cache.delete_value(f"neotec_ai:report_filters:{self.report}")


@frappe.whitelist()
def get_filters_preview(report):
    frappe.only_for("System Manager")
    from neotec_ai.erp_reports import discover_filters

    return discover_filters(frappe.get_doc("Report", report))
