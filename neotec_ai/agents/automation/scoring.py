# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Quality score for playbook results, from a small model. Best effort: a missing score never fails a run.

Residency: the scoring provider must keep data at least as close as the provider that produced the result.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

from neotec_ai.agents.automation import common

PROMPT = """You grade automated business reports produced inside an ERP system.
Score 5: specific, uses concrete figures and document names, follows the task, actionable.
Score 3: on task but generic, or missing figures the task asked for.
Score 1: empty, off task, contradicts itself, or claims actions without evidence.
Reply with JSON only: {"score": <1-5>, "note": "<one short sentence>"}"""


def score_run(run: str):
    from neotec_ai.agents.engine import llm, redact

    s = frappe.get_cached_doc("Coworker Settings")
    if not (cint(s.score_runs) and s.scoring_provider):
        return
    doc = frappe.get_doc("Coworker Run", run)
    if doc.status != "Succeeded" or not doc.output:
        return
    scorer = frappe.get_doc("Coworker Provider", s.scoring_provider)
    if not cint(scorer.enabled):
        return
    source_loc = frappe.db.get_value("Coworker Provider", doc.provider, "data_location") if doc.provider else "On-Premises"
    if not common.fallback_allowed(source_loc, scorer.data_location, s.residency_mode):
        frappe.db.set_value("Coworker Run", run, "score_note", "not scored: scoring provider is further away "
                            "than the run's provider", update_modified=False)
        return
    task = frappe.db.get_value("Coworker Playbook", doc.playbook, "instructions") or ""
    text = f"TASK:\n{task[:3000]}\n\nREPORT:\n{doc.output[:8000]}"
    if scorer.data_location == "External" and cint(s.redact_external):
        text = redact.mask_all(text)
    try:
        res = llm.chat(llm.config_from_doc(scorer), PROMPT, [{"role": "user", "content": text}], [], temperature=0)
    except llm.ProviderError as e:
        frappe.db.set_value("Coworker Run", run, "score_note", f"not scored: {str(e)[:200]}", update_modified=False)
        return
    score, note = common.parse_score(res.text)
    if score:
        frappe.db.set_value("Coworker Run", run, {"score": score, "score_note": note}, update_modified=False)
    frappe.db.commit()
