# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe.model.document import Document


class CoworkerRun(Document):
	@frappe.whitelist()
	def run_again(self):
		from neotec_ai.agents.automation.playbooks import rerun

		return rerun(self.name)
