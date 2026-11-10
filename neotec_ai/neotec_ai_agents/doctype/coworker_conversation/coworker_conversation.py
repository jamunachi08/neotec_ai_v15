# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe.model.document import Document


class CoworkerConversation(Document):
	def on_trash(self):
		frappe.db.delete("Coworker Message", {"conversation": self.name})
