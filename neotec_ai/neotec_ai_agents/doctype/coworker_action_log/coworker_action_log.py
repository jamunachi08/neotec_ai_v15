# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe import _
from frappe.model.document import Document


class CoworkerActionLog(Document):
	"""Append-only audit record. Written only by the gateway."""

	def validate(self):
		if not self.flags.from_gateway:
			frappe.throw(_("Audit records are written by Neotec AI only."))

	def on_trash(self):
		frappe.throw(_("Audit records cannot be deleted. Configure retention in Coworker Settings."))
