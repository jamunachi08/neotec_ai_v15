# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Playbooks: a named, reusable task that a coworker carries out on request, on a schedule, when a document
event happens, or as a step in a chain.

One run, end to end:

    start_run  -> Coworker Run (Queued) -> background job
    execute_run -> fresh conversation linked to the run -> the normal agent loop (same gateway, same policy,
                   same audit trail) with the playbook brief added to the system prompt
    finalize   -> read the output contract (severity / nothing to report) -> metrics and cost
               -> delivery -> optional quality score -> next chain step

A playbook never gets more than its coworker's grants. Read Only playbooks lose every write tool, and automated
runs keep the initiator "Routine", so the starter policy pack ("Routines cannot change data") applies to them.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_first_day, now_datetime, nowdate, time_diff_in_seconds

from neotec_ai.agents.automation import common

RUN_TIMEOUT = 1500
IMPLICIT_TOOLS = ("signals_check", "signals_record")
NEVER_IN_RUNS = ("run_playbook",)
ADMIN_ROLES = {"Coworker Admin", "System Manager"}
USE_ROLES = {"Coworker User"} | ADMIN_ROLES
CHANNEL_FOR_SOURCE = {"Manual": "Chat", "MCP": "MCP"}  # everything else runs as "Routine"

OUTPUT_CONTRACT = """Output contract
- Nobody is watching this run live. Do not ask questions; if something is missing, say so in the report.
- Start the report with one line: SEVERITY: info, SEVERITY: success, SEVERITY: warn or SEVERITY: critical.
  warn = someone should act this week; critical = someone should act today.
- Lead with what needs attention, then the figures. Use render_ui for more than three numbers.
- If nothing new needs attention, reply with exactly NOTHING_TO_REPORT and nothing else."""

DEDUPE_RULES = """Repeated findings
- Give each finding a short, stable key, e.g. "overdue:CUST-0012" or "lowstock:ITEM-001@Stores".
- Before reporting, call signals_check with your keys and leave out the ones already reported.
- After writing the report, call signals_record with the findings you reported (key and one-line summary)."""


# ---------------------------------------------------------------- helpers

def settings():
    return frappe.get_cached_doc("Coworker Settings")


def playbook_available(pb) -> bool:
    if not pb or not cint(pb.enabled):
        return False
    if pb.pack and not cint(frappe.db.get_value("Coworker Pack", pb.pack, "enabled")):
        return False
    return True


def month_tokens() -> int:
    first = get_first_day(nowdate())
    val = frappe.db.sql("""select ifnull(sum(tokens_in + tokens_out), 0) from `tabCoworker Run`
        where creation >= %s""", (first,))
    return cint(val[0][0])


def _can_use_playbook(pb, user=None) -> bool:
    from neotec_ai.agents.engine import runner

    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    if roles & ADMIN_ROLES:
        return True
    if not roles & USE_ROLES:
        return False
    return runner.can_use(frappe.get_cached_doc("AI Coworker", pb.coworker), user)


# ---------------------------------------------------------------- validation (controller)

def validate_playbook(doc):
    if not frappe.db.exists("AI Coworker", doc.coworker):
        frappe.throw(_("Coworker {0} does not exist.").format(doc.coworker))
    doc.required_tools = ", ".join(common.normalise_tools(doc.required_tools))
    if cint(doc.dedupe_days) < 0:
        doc.dedupe_days = 0
    if cint(doc.max_steps) < 0 or cint(doc.max_steps) > 30:
        frappe.throw(_("Max steps must be between 1 and 30."))
    if cint(doc.get("max_tool_calls")) < 0 or cint(doc.get("max_tool_calls")) > 200:
        frappe.throw(_("Max tool calls must be between 1 and 200."))
    if doc.default_severity not in common.SEVERITIES:
        doc.default_severity = "info"
    cw = frappe.get_doc("AI Coworker", doc.coworker)
    granted = {g.tool for g in cw.tools if (g.mode or "Default") != "Off"}
    missing = [t for t in common.normalise_tools(doc.required_tools) if t not in granted]
    if missing:
        frappe.msgprint(_("The coworker {0} has not been granted: {1}. The playbook may not be able to finish.")
                        .format(cw.name, ", ".join(missing)), indicator="orange", alert=True)


# ---------------------------------------------------------------- start

def start_run(playbook, parameter=None, source="Manual", run_as=None, dry_run=0, routine=None, trigger=None,
              chain=None, chain_root=None, chain_step=0, chain_parameter=None, reference_doctype=None,
              reference_name=None, enqueue=True) -> str:
    pb = frappe.get_cached_doc("Coworker Playbook", playbook)
    if not playbook_available(pb):
        frappe.throw(_("The playbook {0} is disabled.").format(playbook))
    run_as = run_as or frappe.session.user
    if parameter in (None, "") and pb.default_parameter:
        parameter = pb.default_parameter
    run = frappe.get_doc({
        "doctype": "Coworker Run", "playbook": pb.name, "parameter": (parameter or "")[:2000], "status": "Queued",
        "source": source, "run_as": run_as, "dry_run": cint(dry_run), "routine": routine, "trigger": trigger,
        "chain": chain, "chain_root": chain_root, "chain_step": cint(chain_step),
        "chain_parameter": chain_parameter, "reference_doctype": reference_doctype,
        "reference_name": reference_name,
    })
    run.owner = run_as
    run.insert(ignore_permissions=True)
    if chain and not chain_root:
        frappe.db.set_value("Coworker Run", run.name, "chain_root", run.name, update_modified=False)
    if enqueue:
        frappe.enqueue("neotec_ai.agents.automation.playbooks.execute_run", queue="long", timeout=RUN_TIMEOUT,
                       run=run.name, enqueue_after_commit=True)
    return run.name


def run_from_form(playbook, parameter=None, dry_run=0):
    pb = frappe.get_doc("Coworker Playbook", playbook)
    if not _can_use_playbook(pb):
        frappe.throw(_("You do not have access to the coworker this playbook uses."), frappe.PermissionError)
    return start_run(pb.name, parameter, source="Manual", run_as=frappe.session.user, dry_run=dry_run)


def rerun(run_name):
    old = frappe.get_doc("Coworker Run", run_name)
    old.check_permission("read")
    pb = frappe.get_doc("Coworker Playbook", old.playbook)
    if not _can_use_playbook(pb):
        frappe.throw(_("You do not have access to the coworker this playbook uses."), frappe.PermissionError)
    return start_run(pb.name, old.parameter, source="Manual", run_as=frappe.session.user, dry_run=old.dry_run,
                     reference_doctype=old.reference_doctype, reference_name=old.reference_name)


# ---------------------------------------------------------------- execute

def execute_run(run: str):
    from neotec_ai.agents.engine import runner

    doc = frappe.get_doc("Coworker Run", run)
    if doc.status != "Queued":
        return  # already handled (duplicate job or cancelled)
    frappe.set_user(doc.run_as)
    started = now_datetime()
    frappe.db.set_value("Coworker Run", run, {"status": "Running", "started_on": started}, update_modified=False)
    frappe.db.commit()

    error = None
    conv_name = None
    try:
        s = settings()
        if not cint(s.enabled):
            raise runner.TurnError(_("Neotec AI is switched off by the administrator."))
        pb = frappe.get_doc("Coworker Playbook", doc.playbook)
        if not playbook_available(pb):
            raise runner.TurnError(_("The playbook {0} is disabled.").format(pb.name))
        cap = cint(s.monthly_automation_tokens)
        if cap and month_tokens() >= cap:
            frappe.db.set_value("Coworker Run", run, "budget_exceeded", 1, update_modified=False)
            raise runner.TurnError(_("This month's automation token budget ({0}) is used up.").format(cap))

        context_dt = doc.reference_doctype if doc.reference_doctype and doc.reference_name else None
        conv = frappe.get_doc({
            "doctype": "Coworker Conversation", "coworker": pb.coworker, "user": doc.run_as,
            "title": f"Run: {pb.playbook_name}"[:80], "channel": CHANNEL_FOR_SOURCE.get(doc.source, "Routine"),
            "status": "Idle", "run": doc.name, "routine": doc.routine,
            "context_doctype": context_dt, "context_name": doc.reference_name if context_dt else None,
        }).insert(ignore_permissions=True)
        conv_name = conv.name
        frappe.db.set_value("Coworker Run", run, "conversation", conv_name, update_modified=False)
        label = pb.parameter_label or _("Parameter")
        ask = _("Run the playbook \"{0}\" now.").format(pb.playbook_name)
        if doc.parameter:
            ask += f"\n{label}: {doc.parameter}"
        runner.add_message(conv_name, "user", ask, status="ok")
        frappe.db.commit()
        runner.run_once(conv_name)
    except runner.TurnError as e:
        error = str(e)
    except Exception as e:  # noqa: BLE001
        frappe.db.rollback()
        frappe.log_error(title="Neotec AI playbook run failed", reference_doctype="Coworker Run",
                         reference_name=run)
        error = _("Unexpected error ({0}). Details are in the Error Log.").format(e.__class__.__name__)
    finalize(run, conv_name, started, error)


def _last_answer(conv_name):
    if not conv_name:
        return ""
    row = frappe.get_all("Coworker Message", filters={"conversation": conv_name, "role": "assistant",
                                                      "status": ["!=", "error"]},
                         fields=["content"], order_by="seq desc", limit_page_length=1)
    return (row[0].content or "") if row else ""


def _metrics(conv_name, provider):
    if not conv_name:
        return {}
    t = frappe.db.sql("""select ifnull(sum(tokens_in),0), ifnull(sum(tokens_out),0)
        from `tabCoworker Message` where conversation=%s""", conv_name)
    tin, tout = cint(t[0][0]), cint(t[0][1])
    prices = frappe.db.get_value("Coworker Provider", provider,
                                 ["cost_input_per_million", "cost_output_per_million"], as_dict=True) if provider else None
    return {
        "tokens_in": tin, "tokens_out": tout,
        "cost": common.cost_usd(tin, tout, flt(prices.cost_input_per_million) if prices else 0,
                                flt(prices.cost_output_per_million) if prices else 0),
        "tool_calls": frappe.db.count("Coworker Action Log", {"conversation": conv_name}),
        "refused_calls": frappe.db.count("Coworker Action Log", {"conversation": conv_name, "status": "Refused"}),
    }


def finalize(run, conv_name, started, error=None):
    from neotec_ai.agents import routines
    from neotec_ai.agents.automation import chains, delivery

    doc = frappe.get_doc("Coworker Run", run)
    pb = frappe.get_doc("Coworker Playbook", doc.playbook)
    ended = now_datetime()
    values = {"ended_on": ended, "duration_s": round(time_diff_in_seconds(ended, started), 1)}
    values.update(_metrics(conv_name, doc.provider))

    conv_status = frappe.db.get_value("Coworker Conversation", conv_name, "status") if conv_name else None
    text, severity, nothing = common.parse_output(_last_answer(conv_name), pb.default_severity or "info")
    blocks_text = routines._blocks_to_text(routines._latest_blocks(conv_name)) if conv_name else ""
    if blocks_text and not nothing:
        text = f"{text}\n\n{blocks_text}".strip()

    if error:
        status = "Budget Exceeded" if cint(doc.budget_exceeded) else "Failed"
        values["error"] = error[:2000]
    elif conv_status == "Waiting Approval":
        status = "Waiting Approval"
    elif cint(doc.budget_exceeded):
        status = "Budget Exceeded"
    elif nothing:
        status = "Nothing to Report"
    elif not text:
        status, values["error"] = "Failed", _("The coworker returned no answer.")
    else:
        status = "Succeeded"
    values.update({"status": status, "severity": severity if status != "Failed" else "warn", "output": text})
    frappe.db.set_value("Coworker Run", run, values, update_modified=False)
    frappe.db.set_value("Coworker Playbook", pb.name, {"last_run": ended, "last_status": status},
                        update_modified=False)
    if doc.routine:
        frappe.db.set_value("Coworker Routine", doc.routine, "last_run_record", run, update_modified=False)
    frappe.db.commit()

    doc.reload()
    try:
        delivery.deliver_run(doc, pb)
    except Exception:  # noqa: BLE001 - delivery problems never undo the run
        frappe.log_error(title="Neotec AI delivery failed", reference_doctype="Coworker Run",
                         reference_name=run)
    frappe.db.commit()

    s = settings()
    if status == "Succeeded" and cint(s.score_runs) and s.scoring_provider:
        frappe.enqueue("neotec_ai.agents.automation.scoring.score_run", queue="short", run=run,
                       enqueue_after_commit=True)
    if doc.chain:
        chains.after_step(doc)
        frappe.db.commit()
    return status


# ---------------------------------------------------------------- what the model sees (called by the agent loop)

def run_context(conv):
    name = conv.get("run")
    if not name or not frappe.db.exists("Coworker Run", name):
        return None
    run = frappe.get_doc("Coworker Run", name)
    pb = frappe.get_doc("Coworker Playbook", run.playbook) if run.playbook else None
    if not pb:
        return None
    return frappe._dict(
        run=run, playbook=pb, name=run.name, read_only=pb.mode == "Read Only", dry_run=cint(run.dry_run),
        provider=pb.provider or None, max_steps=cint(pb.max_steps), max_tokens=cint(pb.max_tokens),
        max_tool_calls=cint(pb.get("max_tool_calls")),
        dedupe_days=cint(pb.dedupe_days), automated=run.source not in ("Manual", "MCP"),
    )


def adjust_tools(rctx, grants: dict, specs: list[dict]):
    """Read Only removes write tools; dedupe adds the signal tools; runs never start other runs."""
    from neotec_ai.agents.engine import registry

    grants = dict(grants)
    keep = []
    for spec in specs:
        full = registry.get_tool(spec["name"]) or {}
        if spec["name"] in NEVER_IN_RUNS or (rctx.read_only and full.get("is_write")):
            grants.pop(spec["name"], None)
            continue
        keep.append(spec)
    if rctx.dedupe_days > 0:
        disabled = set(frappe.get_all("Coworker Tool", filters={"enabled": 0}, pluck="name"))
        have = {s["name"] for s in keep}
        for name in IMPLICIT_TOOLS:
            spec = registry.get_tool(name)
            if spec and name not in have and name not in disabled:
                grants[name] = "Default"
                keep.append({"name": spec["name"], "description": spec["description"], "schema": spec["schema"]})
    return grants, keep


def recent_signals(playbook, days, limit=40):
    if not days:
        return []
    since = add_to_date(now_datetime(), days=-cint(days))
    return frappe.get_all("Coworker Signal", filters={"playbook": playbook, "last_seen": [">=", since]},
                          fields=["signal_key", "summary", "last_seen"], order_by="last_seen desc",
                          limit_page_length=limit)


def _previous_output(run):
    filters = {"playbook": run.playbook, "status": "Succeeded", "name": ["!=", run.name],
               "parameter": run.parameter if run.parameter else ["is", "not set"]}
    rows = frappe.get_all("Coworker Run", filters=filters,
                          fields=["output", "ended_on"], order_by="creation desc", limit_page_length=1)
    return rows[0] if rows and rows[0].output else None


def brief(rctx, s) -> str:
    from neotec_ai.agents.automation import chains

    run, pb = rctx.run, rctx.playbook
    values = {"parameter": run.parameter or pb.default_parameter or "", "today": nowdate()}
    parts = []
    head = (f"Playbook run\nYou are running the playbook \"{pb.playbook_name}\" "
            f"(started by: {run.source}{', dry run' if rctx.dry_run else ''}).")
    if pb.parameter_label:
        head += f"\n{pb.parameter_label}: {values['parameter'] or '(not given; use a sensible default and say which)'}"
    parts.append(head)
    parts.append("Task\n" + common.substitute(pb.instructions, values).strip())

    if rctx.read_only:
        parts.append("This playbook is read-only. Report; do not change data.")
    elif rctx.automated:
        parts.append("This is an automated run. It cannot change data or wait for approval. Where a change is "
                     "needed, list it for a person to make.")
    if rctx.dry_run:
        parts.append("This is a dry run. Tools that change data are not executed. For each change you would make, "
                     "show the exact document and values.")

    earlier = chains.earlier_outputs(run)
    if earlier:
        txt = "\n\n".join(f"### {p} ({st})\n{(o or '')[:3000]}" for p, st, o in earlier)
        parts.append("Results from earlier steps in this chain (use them; do not fetch the same data again)\n" + txt)

    if cint(pb.include_previous_output):
        prev = _previous_output(run)
        if prev:
            parts.append(f"Your previous result ({str(prev.ended_on)[:16]}), for comparison. Say what changed.\n"
                         + prev.output[:2500])

    if rctx.dedupe_days > 0:
        rows = recent_signals(pb.name, rctx.dedupe_days)
        listed = "\n".join(f"- {r.signal_key}: {(r.summary or '')[:120]}" for r in rows) or "- (none)"
        parts.append(DEDUPE_RULES + f"\nAlready reported in the last {rctx.dedupe_days} day(s):\n{listed}")

    if s.get("voice"):
        parts.append("Voice for the report\n" + s.voice.strip())
    parts.append(OUTPUT_CONTRACT)
    return "\n\n".join(parts)


def after_resumed_turn(conv_name):
    """A run that waited for approval continues in a normal turn; close the run record when that turn ends."""
    try:
        run = frappe.db.get_value("Coworker Conversation", conv_name, "run")
        if not run:
            return
        doc = frappe.db.get_value("Coworker Run", run, ["status", "started_on"], as_dict=True)
        if not doc or doc.status != "Waiting Approval":
            return
        if frappe.db.get_value("Coworker Conversation", conv_name, "status") != "Idle":
            return
        last = frappe.get_all("Coworker Message", filters={"conversation": conv_name, "role": "assistant"},
                              fields=["content", "status"], order_by="seq desc", limit_page_length=1)
        error = last[0].content if last and last[0].status == "error" else None
        finalize(run, conv_name, doc.started_on or now_datetime(), error)
    except Exception:  # noqa: BLE001
        frappe.db.rollback()
        frappe.log_error(title="Neotec AI: closing a resumed run failed", reference_doctype="Coworker Run")


def mark_budget(run_name):
    frappe.db.set_value("Coworker Run", run_name, "budget_exceeded", 1, update_modified=False)


def set_provider(run_name, provider):
    frappe.db.set_value("Coworker Run", run_name, "provider", provider, update_modified=False)
