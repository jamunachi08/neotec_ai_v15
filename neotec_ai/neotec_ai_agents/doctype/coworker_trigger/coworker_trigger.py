# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe.model.document import Document


class CoworkerTrigger(Document):
	def validate(self):
		from neotec_ai.agents.automation.triggers import validate_trigger

		validate_trigger(self)

	def on_update(self):
		from neotec_ai.agents.automation.triggers import clear_cache

		clear_cache()

	def on_trash(self):
		from neotec_ai.agents.automation.triggers import clear_cache

		clear_cache()

	@frappe.whitelist()
	def test_on(self, name, start=0):
		from neotec_ai.agents.automation.triggers import test_trigger

		return test_trigger(self.name, name, start)
