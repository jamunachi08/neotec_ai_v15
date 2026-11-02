import frappe
from frappe import _
from frappe.model.document import Document


class NeotecSampleQuestion(Document):
    def validate(self):
        self.question = (self.question or "").strip()
        if self.scope == "Module" and not self.module:
            frappe.throw(_("Set the Module for a module-level question."))
        if self.scope in ("DocType", "Document") and not self.reference_doctype:
            frappe.throw(_("Set the DocType for this question."))
        if self.scope != "Module":
            self.module = None
        if self.scope not in ("DocType", "Document"):
            self.reference_doctype = None
