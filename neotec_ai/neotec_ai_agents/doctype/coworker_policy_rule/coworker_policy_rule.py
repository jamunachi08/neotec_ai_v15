# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe import _
from frappe.model.document import Document


class CoworkerPolicyRule(Document):
	def validate(self):
		self.tool_pattern = (self.tool_pattern or "*").strip() or "*"
		if self.condition:
			try:
				compile(self.condition.strip(), "<policy condition>", "eval")
			except SyntaxError as e:
				frappe.throw(_("The condition is not a valid Python expression: {0}").format(e.msg))
		if self.effect != "Require Approval":
			self.approver_role = None
