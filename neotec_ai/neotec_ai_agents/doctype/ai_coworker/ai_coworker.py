# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe import _
from frappe.model.document import Document


class AICoworker(Document):
	def validate(self):
		seen = set()
		for row in self.tools:
			if row.tool in seen:
				frappe.throw(_("Tool {0} is listed twice.").format(row.tool))
			seen.add(row.tool)
			if not row.mode:
				row.mode = "Default"
		risky = [r.tool for r in self.tools if r.mode == "Auto" and r.is_write and r.tool != "notify_user"]
		if risky:
			frappe.msgprint(_("These tools change data and will run without asking: {0}. Policies still apply.").format(
				", ".join(risky)), indicator="orange", alert=True)

	@frappe.whitelist()
	def grant_read_tools(self):
		have = {r.tool for r in self.tools}
		for name in frappe.get_all("Coworker Tool", filters={"is_write": 0, "enabled": 1, "source": "Built-in"}, pluck="name"):
			if name not in have:
				self.append("tools", {"tool": name, "mode": "Default"})
		self.save()
		return len(self.tools)
