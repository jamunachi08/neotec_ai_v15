import frappe
from frappe.model.document import Document


class NeotecAIProject(Document):
    def before_insert(self):
        self.user = self.user or frappe.session.user

    def on_trash(self):
        frappe.db.set_value("Neotec AI Conversation", {"project": self.name}, "project", None)
