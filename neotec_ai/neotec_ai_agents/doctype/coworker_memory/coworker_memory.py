# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe import _
from frappe.model.document import Document


class CoworkerMemory(Document):
	def validate(self):
		from neotec_ai.agents.engine.redact import mask_all

		self.fact = (self.fact or "").strip()[:280]
		if mask_all(self.fact) != self.fact:
			frappe.throw(_("Memory cannot hold personal or secret data such as ID numbers, IBANs or keys."))
		admin = set(frappe.get_roles()) & {"Coworker Admin", "System Manager"}
		if self.user != frappe.session.user and not admin:
			frappe.throw(_("You can only keep memory for yourself."))
