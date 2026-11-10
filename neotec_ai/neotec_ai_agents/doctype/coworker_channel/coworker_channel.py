# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe.model.document import Document


class CoworkerChannel(Document):
	def validate(self):
		from neotec_ai.agents.automation.delivery import validate_channel

		validate_channel(self)

	@frappe.whitelist()
	def send_test(self):
		from neotec_ai.agents.automation.delivery import send_test

		return send_test(self.name)
