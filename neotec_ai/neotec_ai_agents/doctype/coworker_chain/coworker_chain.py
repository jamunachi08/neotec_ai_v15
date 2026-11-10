# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe.model.document import Document


class CoworkerChain(Document):
	def validate(self):
		from neotec_ai.agents.automation.chains import validate_chain

		validate_chain(self)

	@frappe.whitelist()
	def run_now(self, parameter=None):
		from neotec_ai.agents.automation.chains import run_from_form

		return run_from_form(self.name, parameter)
