# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe import _
from frappe.model.document import Document


class CoworkerProvider(Document):
	def validate(self):
		from neotec_ai.agents.api import PRESETS

		preset = PRESETS.get(self.preset or "")
		if preset:
			self.provider_type = preset["provider_type"]
			if not self.base_url:
				self.base_url = preset["base_url"]
			if not self.model and preset.get("model"):
				self.model = preset["model"]
		self.base_url = (self.base_url or "").strip().rstrip("/")
		if not self.base_url.startswith(("https://", "http://")):
			frappe.throw(_("Base URL must start with https:// (or http:// for a server on your own network)."))
		if self.base_url.startswith("http://") and self.data_location == "External":
			frappe.throw(_("External providers must use https://."))
		# A different model or server is a different test subject.
		if not self.is_new() and (self.has_value_changed("model") or self.has_value_changed("base_url")):
			self.tool_test_status = "Not tested"

	def on_update(self):
		if self.is_default:
			frappe.db.sql("update `tabCoworker Provider` set is_default=0 where name!=%s", self.name)
			if not frappe.db.get_single_value("Coworker Settings", "default_provider"):
				frappe.db.set_single_value("Coworker Settings", "default_provider", self.name)

	@frappe.whitelist()
	def test_connection(self):
		from neotec_ai.agents.api import test_provider

		return test_provider(self.name)

	@frappe.whitelist()
	def test_tool_calling(self):
		from neotec_ai.agents.api import test_tool_calling

		return test_tool_calling(self.name)

	@frappe.whitelist()
	def find_models(self):
		from neotec_ai.agents.api import discover_models

		return discover_models(provider=self.name)
