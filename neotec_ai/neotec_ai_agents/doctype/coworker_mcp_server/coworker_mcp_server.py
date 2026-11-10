# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import re

import frappe
from frappe import _
from frappe.model.document import Document


class CoworkerMCPServer(Document):
	def validate(self):
		if not re.fullmatch(r"[A-Za-z0-9]{2,24}", self.server_name or ""):
			frappe.throw(_("Name: 2 to 24 letters or digits, no spaces."))
		if not (self.url or "").startswith("https://"):
			frappe.throw(_("MCP servers must use https://."))

	@frappe.whitelist()
	def sync_tools(self):
		from neotec_ai.agents.mcp.client import sync

		frappe.only_for(("Coworker Admin", "System Manager"))
		return sync(self.name)
