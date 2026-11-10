# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe import _
from frappe.model.document import Document


class CoworkerSettings(Document):
	def validate(self):
		if self.mcp_enabled and not self.mcp_coworker:
			frappe.throw(_("Choose the coworker whose tools the MCP endpoint exposes."))
		for field, low, high in (("max_steps", 1, 30), ("max_tool_calls", 1, 60), ("history_window", 6, 200)):
			val = self.get(field) or 0
			if val and not low <= val <= high:
				frappe.throw(_("{0} must be between {1} and {2}.").format(self.meta.get_label(field), low, high))
