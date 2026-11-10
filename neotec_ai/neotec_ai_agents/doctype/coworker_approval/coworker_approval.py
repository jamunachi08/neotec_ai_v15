# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe import _
from frappe.model.document import Document


class CoworkerApproval(Document):
	def validate(self):
		if self.is_new() or self.flags.from_gateway:
			return
		before = self.get_doc_before_save()
		if before and before.status != self.status:
			frappe.throw(_("Use the Approve or Reject buttons."))

	def on_trash(self):
		frappe.throw(_("Approval records are part of the audit trail and cannot be deleted."))

	@frappe.whitelist()
	def approve(self, comment=None):
		from neotec_ai.agents.engine import gateway

		return gateway.decide(self.name, True, comment or "")

	@frappe.whitelist()
	def reject(self, comment=None):
		from neotec_ai.agents.engine import gateway

		return gateway.decide(self.name, False, comment or "")

	@frappe.whitelist()
	def decision_rights(self):
		from neotec_ai.agents.engine import gateway

		ok, why = gateway.can_decide(self)
		return {"can_decide": ok, "why_not": why}
