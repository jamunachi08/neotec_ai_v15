# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe.model.document import Document


class CoworkerPlaybook(Document):
	def validate(self):
		from neotec_ai.agents.automation.playbooks import validate_playbook

		validate_playbook(self)

	@frappe.whitelist()
	def run_now(self, parameter=None, dry_run=0):
		from neotec_ai.agents.automation.playbooks import run_from_form

		return run_from_form(self.name, parameter, dry_run)
