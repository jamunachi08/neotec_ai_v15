import frappe
from frappe import _
from frappe.model.document import Document

MAX_CONTENT = 20000
MAX_ALWAYS = 3000


class NeotecPlaybook(Document):
    def validate(self):
        self.title = (self.title or "").strip()
        if len(self.content or "") > MAX_CONTENT:
            frappe.throw(_("Keep a playbook under {0} characters; split long material into several playbooks.").format(MAX_CONTENT))
        if self.always_include and len(self.content or "") > MAX_ALWAYS:
            frappe.throw(_("'Always Include' playbooks must be short (under {0} characters) because they are sent with every question.").format(MAX_ALWAYS))
