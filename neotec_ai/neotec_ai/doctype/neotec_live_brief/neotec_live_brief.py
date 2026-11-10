# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
import frappe
from frappe import _
from frappe.model.document import Document


class NeotecLiveBrief(Document):
    def validate(self):
        if not self.run_as:
            self.run_as = frappe.session.user
        if self.run_as != frappe.session.user and not (set(frappe.get_roles()) & {"System Manager", "Coworker Admin"}):
            frappe.throw(_("Only an administrator can make a brief run as another user."))
        if self.frequency == "On Document Event" and not self.trigger_doctype:
            frappe.throw(_("Choose the document type that refreshes this brief."))
        from neotec_ai.agents.engine.runner import can_use

        if self.coworker and not can_use(frappe.get_doc("AI Coworker", self.coworker), self.run_as):
            frappe.throw(_("{0} may not use the coworker {1}.").format(self.run_as, self.coworker))
        from neotec_ai.briefs import compute_next_run

        self.next_run = compute_next_run(self) if self.enabled else None

    def on_update(self):
        from neotec_ai.briefs import clear_index

        clear_index()

    def on_trash(self):
        from neotec_ai.briefs import clear_index

        clear_index()
