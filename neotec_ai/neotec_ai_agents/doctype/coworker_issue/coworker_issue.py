# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe.model.document import Document


class CoworkerIssue(Document):
	def validate(self):
		if self.has_value_changed("status") and self.status != "Open" and not self.resolved_on:
			self.resolved_on = frappe.utils.now_datetime()
