# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe.model.document import Document


class CoworkerRoutine(Document):
	def validate(self):
		from neotec_ai.agents.routines import validate_routine

		validate_routine(self)

	@frappe.whitelist()
	def run_now(self):
		from neotec_ai.agents.routines import run_now

		return run_now(self.name)
