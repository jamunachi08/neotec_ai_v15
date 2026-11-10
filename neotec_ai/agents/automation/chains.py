# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Chains: playbooks run one after another; later steps can read earlier results.

Each step is its own Coworker Run and its own background job, so a long chain never hits a worker time limit:
when a step finishes, ``after_step`` queues the next one. The first run of a chain is its "chain root"; every
step carries the root's name, which is how a step finds the results before it.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

MAX_STEPS = 12


def validate_chain(doc):
    if not doc.steps:
        frappe.throw(_("Add at least one step."))
    if len(doc.steps) > MAX_STEPS:
        frappe.throw(_("A chain can have at most {0} steps.").format(MAX_STEPS))
    off = [r.playbook for r in doc.steps if not cint(frappe.db.get_value("Coworker Playbook", r.playbook, "enabled"))]
    if off:
        frappe.msgprint(_("These playbooks are disabled and will stop the chain: {0}").format(", ".join(off)),
                        indicator="orange", alert=True)


def start(chain, parameter=None, source="Manual", run_as=None, routine=None, inline=False) -> str:
    from neotec_ai.agents.automation import playbooks

    ch = frappe.get_doc("Coworker Chain", chain)
    if not cint(ch.enabled):
        frappe.throw(_("The chain {0} is disabled.").format(chain))
    if not ch.steps:
        frappe.throw(_("The chain {0} has no steps.").format(chain))
    first = ch.steps[0]
    name = playbooks.start_run(first.playbook, first.parameter or parameter, source=source, run_as=run_as,
                               routine=routine, chain=ch.name, chain_step=1, chain_parameter=parameter,
                               enqueue=not inline)
    if inline:
        frappe.db.commit()
        playbooks.execute_run(name)
    return name


def run_from_form(chain, parameter=None):
    roles = set(frappe.get_roles())
    if not roles & {"Coworker User", "Coworker Admin", "System Manager"}:
        frappe.throw(_("Ask your administrator for the Coworker User role."), frappe.PermissionError)
    return start(chain, parameter, source="Manual", run_as=frappe.session.user)


def step_row(run):
    if not run.chain or not frappe.db.exists("Coworker Chain", run.chain):
        return None, None
    ch = frappe.get_cached_doc("Coworker Chain", run.chain)
    idx = cint(run.chain_step) - 1
    if idx < 0 or idx >= len(ch.steps):
        return ch, None
    return ch, ch.steps[idx]


def is_delivering_step(run) -> bool:
    """Intermediate steps stay quiet unless marked; the last step always delivers."""
    ch, row = step_row(run)
    if not ch or not row:
        return True
    return cint(row.deliver) or cint(run.chain_step) >= len(ch.steps)


def earlier_outputs(run) -> list[tuple[str, str, str]]:
    if not run.chain or not run.chain_root or cint(run.chain_step) <= 1:
        return []
    _ch, row = step_row(run)
    if row is not None and not cint(row.use_previous):
        return []
    rows = frappe.get_all("Coworker Run", filters={"chain_root": run.chain_root, "chain_step": ["<", run.chain_step]},
                          fields=["playbook", "status", "output", "chain_step"], order_by="chain_step asc")
    return [(r.playbook, r.status, r.output or "") for r in rows if r.status in ("Succeeded", "Nothing to Report")]


def after_step(run):
    from neotec_ai.agents.automation import playbooks

    ch, _row = step_row(run)
    if not ch:
        return
    failed = run.status in ("Failed", "Budget Exceeded")
    if failed and ch.on_error == "Stop":
        _bell(run.run_as, _("Chain {0} stopped at step {1} ({2}).").format(ch.name, run.chain_step, run.playbook),
              run.error or run.status, run.name)
        return
    if run.status == "Waiting Approval":
        return  # a person continues it by running the next step once they have decided
    nxt_idx = cint(run.chain_step)  # 0-based index of the next step
    if nxt_idx >= len(ch.steps):
        return
    nxt = ch.steps[nxt_idx]
    try:
        playbooks.start_run(nxt.playbook, nxt.parameter or run.chain_parameter, source=run.source, run_as=run.run_as,
                            routine=run.routine, chain=ch.name, chain_root=run.chain_root or run.name,
                            chain_step=nxt_idx + 1, chain_parameter=run.chain_parameter)
    except frappe.ValidationError as e:
        _bell(run.run_as, _("Chain {0} could not start step {1}.").format(ch.name, nxt_idx + 1), str(e), run.name)


def _bell(user, subject, body, run_name):
    frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert",
                    "subject": frappe.utils.strip_html(subject)[:140], "email_content": body,
                    "document_type": "Coworker Run", "document_name": run_name}).insert(ignore_permissions=True)
