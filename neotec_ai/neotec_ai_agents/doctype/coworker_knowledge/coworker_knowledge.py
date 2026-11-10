# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary

import frappe
from frappe.model.document import Document


class CoworkerKnowledge(Document):
	def validate(self):
		if self.attachment and (self.is_new() or self.has_value_changed("attachment")):
			from neotec_ai.agents.tools.knowledge import extract_file_text

			text = extract_file_text(self.attachment)
			if text.strip():
				paras = [p.strip() for p in text.replace("\r", "").split("\n\n") if p.strip()]
				self.content = "".join(f"<p>{frappe.utils.escape_html(p)}</p>" for p in paras)

	def on_update(self):
		from neotec_ai.agents.tools.knowledge import reindex

		reindex(self)

	def on_trash(self):
		frappe.db.delete("Coworker Knowledge Chunk", {"knowledge": self.name})

	@frappe.whitelist()
	def rebuild_index(self):
		from neotec_ai.agents.tools.knowledge import reindex

		return reindex(self)
