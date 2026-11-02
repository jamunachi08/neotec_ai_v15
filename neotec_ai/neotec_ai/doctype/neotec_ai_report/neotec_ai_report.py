import json

import frappe
from frappe import _
from frappe.model.document import Document


class NeotecAIReport(Document):
    def validate(self):
        from neotec_ai.query_engine import PlanError
        from neotec_ai.reports import build_report

        try:
            query = json.loads(self.query_spec or "")
        except ValueError:
            frappe.throw(_("Query must be valid JSON."))
        if not isinstance(query, dict):
            frappe.throw(_("Query must be a JSON object."))
        self.query_spec = json.dumps(query, indent=1)

        try:
            report = build_report(self.get_spec())  # validates for the current user
        except PlanError as e:
            frappe.throw(_("This report is not valid: {0}").format(e))
        self.report_doctype = report["doctype"]
        chart = report["chart"] or {}
        self.chart_type = chart.get("type") or ""
        self.chart_x = ", ".join(chart.get("x") or [])
        self.chart_y = ", ".join(chart.get("y") or [])

    def get_spec(self):
        chart = None
        if self.chart_type and self.chart_x:
            chart = {
                "type": self.chart_type,
                "x": [c.strip() for c in self.chart_x.split(",") if c.strip()],
                "y": [c.strip() for c in (self.chart_y or "").split(",") if c.strip()],
            }
        return {
            "title": self.title,
            "description": self.description or "",
            "query": json.loads(self.query_spec or "{}"),
            "chart": chart,
        }
