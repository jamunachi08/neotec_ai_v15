import json

import frappe
from frappe import _
from frappe.model.document import Document


class NeotecAIReport(Document):
    def validate(self):
        from neotec_ai.bi.engine import AccessError
        from neotec_ai.query_engine import PlanError
        from neotec_ai.reports import run_definition

        for field in ("query_spec", "viz_spec"):
            value = self.get(field)
            if not value:
                continue
            try:
                parsed = json.loads(value)
            except ValueError:
                frappe.throw(_("{0} must be valid JSON.").format(self.meta.get_label(field)))
            if not isinstance(parsed, dict):
                frappe.throw(_("{0} must be a JSON object.").format(self.meta.get_label(field)))

        try:
            report = run_definition(self.get_definition())  # validates with the saving user's permissions
        except PlanError as e:
            frappe.throw(_("This report is not valid: {0}").format(e), title=_("Invalid Report"))
        except AccessError as e:
            frappe.throw(str(e), frappe.PermissionError, title=_("Not Permitted"))

        d = report["definition"]
        self.report_doctype = report["doctype"]
        self.query_spec = json.dumps(d["query"], indent=1)
        self.viz_spec = json.dumps(report["viz"], indent=1)
        self.chart_type = self.chart_x = self.chart_y = None

    def get_definition(self):
        viz = json.loads(self.viz_spec) if self.viz_spec else None
        if not viz and self.chart_type and self.chart_x:  # v2.1 saved reports
            viz = {
                "type": self.chart_type,
                "x": [c.strip() for c in self.chart_x.split(",") if c.strip()],
                "y": [c.strip() for c in (self.chart_y or "").split(",") if c.strip()],
            }
        return {
            "title": self.title,
            "description": self.description or "",
            "query": json.loads(self.query_spec or "{}"),
            "viz": viz,
        }
