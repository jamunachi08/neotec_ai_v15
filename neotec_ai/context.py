"""Builds the AI's view of what it can use: data sources, ERPNext reports, playbooks and approvals.

Large dictionaries are sent as a one-line index plus full detail for the few sources most relevant
to the question; the AI can ask for more with the "describe" tool.
"""

import json

import frappe
from frappe.utils import cint

from neotec_ai import playbooks, relevance
from neotec_ai.bi import engine
from neotec_ai.query_engine import describe_catalog

AUTO_FULL_CHARS = 7000      # below this, the whole dictionary is sent
TOP_SOURCES = 4
TOP_REPORTS = 2
INDEX_DESC_CHARS = 140


class Context:
    def __init__(self, settings, question, history_text="", open_doctype=None):
        self.settings = settings
        self.question = question
        self.focus_text = f"{question} {history_text[-1500:]}"
        self.open_doctype = open_doctype
        self.env = engine.FrappeEnv()
        self.catalog = engine.user_catalog(self.env) if cint(settings.enable_db_queries) else {}
        self.reports = self._reports()
        self.playbooks = playbooks.accessible() if frappe.db.exists("DocType", "Neotec Playbook") else []
        self.approvals = bool(cint(settings.get("enable_approvals"))) and frappe.db.exists("DocType", "Workflow Action")

    def _reports(self):
        try:
            from neotec_ai import erp_reports

            return erp_reports.available_reports()
        except Exception:
            frappe.log_error(title="Neotec AI: could not list ERPNext reports")
            return []

    @property
    def has_tools(self):
        return bool(self.catalog or self.reports or self.playbooks or self.approvals)

    # ------------------------------------------------------------------ data sources
    def detailed_sources(self):
        mode = self.settings.get("catalog_mode") or "Auto"
        names = list(self.catalog)
        if mode == "Full":
            return names
        chosen = []
        if self.open_doctype in self.catalog:
            chosen.append(self.open_doctype)
        low = self.focus_text.lower()
        chosen += [dt for dt in names if dt.lower() in low and dt not in chosen]
        if mode == "Index Only":
            return chosen
        if len(describe_catalog(self.catalog)) <= AUTO_FULL_CHARS:
            return names
        ranked = relevance.rank(
            self.focus_text, names,
            key_name=lambda dt: dt,
            key_text=lambda dt: f"{self.catalog[dt]['description']} {self.catalog[dt].get('sample_questions', '')} {' '.join(self.catalog[dt]['fields'])}",
            k=TOP_SOURCES,
        )
        for dt, _s in ranked:
            if dt not in chosen:
                chosen.append(dt)
        # A child table is useless without its parent (and vice versa for line-item questions)
        for dt in list(chosen):
            parent = self.catalog[dt].get("parent_doctype")
            if parent in self.catalog and parent not in chosen:
                chosen.append(parent)
        return chosen[: TOP_SOURCES + 3]

    def describe_sources(self, names):
        sub = {dt: self.catalog[dt] for dt in names if dt in self.catalog}
        if not sub:
            return ""
        joins = {dt: engine.join_options(dt, self.catalog, self.env) for dt in sub}
        return describe_catalog(sub, joins)

    def source_index(self, exclude):
        lines = []
        for dt, src in self.catalog.items():
            if dt in exclude:
                continue
            desc = " ".join((src["description"] or "").split())
            lines.append(f"- {dt}: {desc[:INDEX_DESC_CHARS]}{'…' if len(desc) > INDEX_DESC_CHARS else ''}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ reports
    def relevant_reports(self):
        ranked = relevance.rank(
            self.focus_text, self.reports,
            key_name=lambda r: r["name"],
            key_text=lambda r: f"{r['purpose']} {r['sample_questions']}",
            k=TOP_REPORTS, min_score=2,
        )
        return [r for r, _s in ranked]

    def describe_reports(self, names):
        from neotec_ai import erp_reports

        out = []
        for name in names:
            try:
                erp_reports.check_allowed(name)
                defs = erp_reports.get_filter_defs(name)
            except Exception as e:
                frappe.clear_last_message()
                out.append(f"### {name}\n(unavailable: {e})")
                continue
            purpose = next((r["purpose"] for r in self.reports if r["name"] == name), "")
            out.append(f"### {name}\n{purpose}\nFilters:\n{erp_reports.describe_filters(defs) or '  (none declared)'}")
        return "\n\n".join(out)

    # ------------------------------------------------------------------ prompt sections
    def sections(self):
        parts = []
        if self.catalog:
            detailed = self.detailed_sources()
            text = "## Data dictionary (the only tables you can query)\n"
            if detailed:
                text += self.describe_sources(detailed)
            rest = self.source_index(set(detailed))
            if rest:
                text += ("\n### Other data sources (call describe for their fields before querying them)\n" + rest)
            parts.append(text)
        if self.reports:
            idx = "\n".join(f"- {r['name']}: {r['purpose'][:180]}" for r in self.reports)
            text = "## ERPNext reports you can run (run_report)\n" + idx
            rel = [r["name"] for r in self.relevant_reports()]
            if rel:
                text += "\n\n" + self.describe_reports(rel)
            parts.append(text)
        if self.playbooks:
            always = [p for p in self.playbooks if p.always_include]
            others = [p for p in self.playbooks if not p.always_include]
            if always:
                parts.append("## Company rules (always apply)\n" + "\n\n".join(
                    f"### {p.title}\n{content}" for p, content in playbooks.always_included()))
            if others:
                parts.append("## Company playbooks (load with describe when the question matches)\n" + "\n".join(
                    f"- [{p.name}] {p.title}: {' '.join((p.description or '').split())[:200]}" for p in others))
        return parts


def tool_protocol(ctx, steps):
    from neotec_ai.bi import prompt as bi_prompt

    lines = [
        "## Tools",
        f"To use a tool, reply with ONLY one JSON object (no other text); the result comes back to you. "
        f"You can use up to {steps} tools per question.",
        '- {"action": "describe", "sources": ["<DocType>"], "reports": ["<report>"], "playbooks": ["<id or title>"]}'
        " - fields of data sources, filters of ERPNext reports, or a playbook's content.",
    ]
    if ctx.catalog:
        lines.append('- {"action": "query", "queries": [<query>, ... up to 5]} - query the data dictionary (format below).')
    if ctx.reports:
        lines.append(
            '- {"action": "run_report", "report": "<report name>", "filters": {"<filter>": <value>}} - run an ERPNext report. '
            "Filters you leave out get defaults (company, current fiscal year, today). Prefer reports for P&L, balance sheet, "
            "cash flow, ledgers, receivable/payable ageing and stock balances; use queries for flexible breakdowns."
        )
    if ctx.approvals:
        lines.append('- {"action": "approvals", "doctype": "<optional DocType>"} - documents waiting for the user\'s approval.')
    if ctx.playbooks:
        lines.append("Check the playbook list first: if one matches the question, describe it and follow it.")
    lines.append(
        "If a tool reports PERMISSION DENIED, tell the user they don't have access to that data; never try to work around it."
    )
    lines.append("")
    if ctx.catalog:
        lines.append(bi_prompt.QUERY_FORMAT)
        lines.append("")
    lines.append(
        "## Answering\nAnswer in plain Markdown, or as JSON when including reports:\n"
        '{"action": "answer", "answer": "<2-5 sentence summary with key figures; do not repeat whole tables>", '
        '"reports": [ {"title": "...", "description": "<what, period, filters>", "query": <query>, "viz": <visualization>} ]}\n'
        'For an ERPNext report use "erp_report": {"report": "<name>", "filters": {...}} instead of "query".\n'
        "Include reports when the user asks for a report, table, list, chart, trend, breakdown or pivot, or when the answer "
        "has more than about 6 rows of figures. Up to 3 reports; they are re-run live and can be exported, saved, scheduled "
        "and added to dashboards."
    )
    lines.append(bi_prompt.VIZ_FORMAT)
    lines.append("Do not mention JSON, tools or DocType internals in the final answer unless the user asks.")
    return "\n".join(lines)
