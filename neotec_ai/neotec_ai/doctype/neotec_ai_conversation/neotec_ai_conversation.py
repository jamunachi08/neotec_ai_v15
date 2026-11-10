import frappe
from frappe.model.document import Document


class NeotecAIConversation(Document):
    def on_trash(self):
        frappe.db.delete("Neotec AI Message", {"conversation": self.name})
