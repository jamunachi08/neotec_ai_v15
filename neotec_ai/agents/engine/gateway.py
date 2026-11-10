# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""The single door every tool call goes through.

    resolve tool -> check grant -> residency guard -> policy -> audit row (committed) -> run as user -> audit result

There is no other path from a model (chat, routine, MCP client) to a tool. If the audit row cannot be
written, nothing runs.
"""

from __future__ import annotations

import json
import time

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from neotec_ai.agents.engine import policy, redact, registry


def settings():
    return frappe.get_cached_doc("Coworker Settings")


def sensitive_doctypes() -> set[str]:
    return {r.document_type for r in (settings().sensitive_doctypes or [])}


def target_doctype(args: dict) -> str | None:
    for key in ("doctype", "reference_doctype", "document_type"):
        val = args.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def _clean_args(spec: dict, args: dict) -> dict:
    props = (spec.get("schema") or {}).get("properties") or {}
    if not props:
        return dict(args)
    return {k: v for k, v in args.items() if k in props}


def _log(ctx, tool_name, spec, args, decision, status, rule=None, reason=None, approval=None):
    log = frappe.get_doc({
        "doctype": "Coworker Action Log",
        "tool": tool_name,
        "status": status,
        "decision": decision,
        "is_write": 1 if spec and spec.get("is_write") else 0,
        "coworker": ctx.get("coworker"),
        "user": ctx.get("user"),
        "initiator": ctx.get("initiator") or "Chat",
        "provider": ctx.get("provider"),
        "conversation": ctx.get("conversation"),
        "rule": rule,
        "reason": (reason or "")[:1000],
        "approval": approval,
        "arguments": redact.to_json(redact.mask_obj(args), 20000),
    })
    log.flags.from_gateway = True
    log.insert(ignore_permissions=True)
    return log


def _finish_log(log_name, status, result=None, error=None, started=None, approval=None):
    values = {"status": status}
    if result is not None:
        values["result_preview"] = redact.mask_secrets(redact.to_json(result, 2000))
    if error:
        values["error"] = str(error)[:1000]
    if started:
        values["duration_ms"] = int((time.time() - started) * 1000)
    if approval:
        values["approval"] = approval
    frappe.db.set_value("Coworker Action Log", log_name, values, update_modified=False)


def _notify_approvers(approval):
    if not approval.approver_role:
        return
    users = frappe.get_all("Has Role", filters={"role": approval.approver_role, "parenttype": "User"},
                           pluck="parent", limit=25)
    for user in set(users):
        if user in ("Administrator", "Guest", approval.requested_by):
            continue
        if not frappe.db.get_value("User", user, "enabled"):
            continue
        frappe.get_doc({
            "doctype": "Notification Log",
            "for_user": user,
            "type": "Alert",
            "document_type": "Coworker Approval",
            "document_name": approval.name,
            "subject": _("Coworker action needs your approval: {0}").format(approval.summary),
            "email_content": approval.summary,
        }).insert(ignore_permissions=True)


def summarize(tool_label: str, args: dict) -> str:
    bits = []
    for k, v in list(args.items())[:4]:
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        bits.append(f"{k}={str(v)[:60]}")
    return f"{tool_label}: " + ", ".join(bits) if bits else tool_label


def _create_approval(ctx, tool_name, spec, args, decision, log):
    hours = int(settings().approval_expiry_hours or 72)
    appr = frappe.get_doc({
        "doctype": "Coworker Approval",
        "status": "Pending",
        "summary": summarize(spec.get("label") or tool_name, args)[:500],
        "tool": tool_name,
        "coworker": ctx.get("coworker"),
        "requested_by": ctx.get("user"),
        "approver_role": decision.get("approver_role"),
        "expires_on": add_to_date(now_datetime(), hours=hours),
        "arguments": json.dumps(args, ensure_ascii=False, default=str, indent=1),
        "conversation": ctx.get("conversation"),
        "message": ctx.get("message"),
        "action_log": log.name,
        "rule": decision.get("rule"),
    })
    appr.insert(ignore_permissions=True)
    _notify_approvers(appr)
    return appr


def _invoke(spec, args, user):
    """Runs the tool as ``user`` inside a savepoint. Raises on failure."""
    previous = frappe.session.user
    switched = previous != user
    if switched:
        frappe.set_user(user)
    frappe.db.savepoint("ntc_tool")
    try:
        for hook in frappe.get_hooks("neotec_ai_before_tool") or []:
            frappe.get_attr(hook)(tool=spec["name"], args=args, user=user)
        result = spec["fn"](**args)
        for hook in frappe.get_hooks("neotec_ai_after_tool") or []:
            frappe.get_attr(hook)(tool=spec["name"], args=args, user=user, result=result)
        return result
    except Exception:
        frappe.db.rollback(save_point="ntc_tool")
        raise
    finally:
        if switched:
            frappe.set_user(previous)


def _friendly_error(e: Exception) -> str:
    if isinstance(e, frappe.PermissionError):
        return "Permission denied for this user: " + (str(e) or "not permitted")
    if isinstance(e, frappe.DoesNotExistError):
        return "Not found: " + str(e)
    if isinstance(e, (frappe.ValidationError, TypeError, ValueError)):
        return frappe.utils.strip_html(str(e))[:800] or e.__class__.__name__
    return "The tool failed. The error was logged for the administrator."


def execute(ctx: dict, tool_name: str, args: dict) -> dict:
    """ctx keys: user, coworker, conversation, initiator, provider, provider_location, grants, message, roles,
    and for playbook runs: run, read_only, dry_run."""
    s = settings()
    args = args if isinstance(args, dict) else {}
    if "__invalid_json__" in args:
        return {"status": "error", "message": "The tool arguments were not valid JSON. Send a JSON object."}
    if not s.enabled:
        return {"status": "refused", "message": "Neotec AI is switched off by the administrator."}

    spec = registry.get_tool(tool_name)
    if not spec:
        return {"status": "refused", "message": f"There is no tool called {tool_name}."}
    grant_mode = (ctx.get("grants") or {}).get(tool_name)
    if not grant_mode or grant_mode == "Off":
        log = _log(ctx, tool_name, spec, args, "Refused", "Refused",
                   reason="Tool not granted to this coworker")
        frappe.db.commit()
        return {"status": "refused", "log": log.name,
                "message": f"This coworker has not been granted the tool {tool_name}. Tell the user; do not try another route."}
    if frappe.db.get_value("Coworker Tool", tool_name, "enabled") == 0:
        return {"status": "refused", "message": f"The tool {tool_name} is disabled by the administrator."}

    args = _clean_args(spec, args)
    doctype = target_doctype(args)
    roles = ctx.get("roles") or set(frappe.get_roles(ctx.get("user")))

    # Residency guard (PDPL): sensitive records never go to an External provider in Guarded mode.
    if (s.residency_mode == "Guarded" and ctx.get("provider_location") == "External"
            and doctype and doctype in sensitive_doctypes()):
        msg = (f"{doctype} is marked sensitive. It cannot be processed by an external AI provider. "
               "Ask the administrator to use an in-Kingdom or on-premises provider for this coworker.")
        log = _log(ctx, tool_name, spec, args, "Refused", "Refused", reason=msg)
        frappe.db.commit()
        return {"status": "refused", "message": msg, "log": log.name}

    pctx = {"tool": tool_name, "args": args, "doctype": doctype, "is_write": spec["is_write"],
            "risk": spec.get("risk"), "user": ctx.get("user"), "roles": roles,
            "coworker": ctx.get("coworker"), "initiator": ctx.get("initiator") or "Chat"}
    decision = policy.decide(policy.load_rules(), pctx, grant_mode, policy.frappe_evaluator)

    if spec["is_write"] and ctx.get("read_only"):
        why = ctx.get("read_only_reason")
        if why == "Plan First":
            msg = ("Plan First mode: nothing is changed. Add this change to your plan; the user switches the chat to "
                   "Standard to carry it out.")
        elif why == "Read Only":
            msg = "This chat is in Read Only mode. Describe the change for the user instead; do not try another route."
        else:
            msg = "This playbook is read-only. Report the change for a person to make; do not try another route."
        log = _log(ctx, tool_name, spec, args, "Refused", "Refused", reason=why or "Read-only playbook")
        frappe.db.commit()
        return {"status": "refused", "message": msg, "log": log.name}

    if decision["effect"] == policy.DENY:
        log = _log(ctx, tool_name, spec, args, "Refused", "Refused", decision.get("rule"), decision["message"])
        frappe.db.commit()
        return {"status": "refused", "message": decision["message"], "log": log.name}

    if spec["is_write"] and ctx.get("dry_run"):
        note = (f" In a real run it would need approval by {decision.get('approver_role') or 'the user'}."
                if decision["effect"] == policy.APPROVE else "")
        log = _log(ctx, tool_name, spec, args, "Refused", "Refused", decision.get("rule"), "Dry run: not executed")
        frappe.db.commit()
        return {"status": "refused", "dry_run": True, "log": log.name,
                "message": "Dry run: not executed. Describe exactly what this call would have done, with the "
                           "document and values." + note}

    if (decision["effect"] == policy.APPROVE and not decision.get("rule") and not decision.get("approver_role")
            and tool_name in (ctx.get("allowed_tools") or ())):
        # The user said "always allow in this chat" for this tool. Policy rules that name an approver are never
        # bypassed (segregation of duties); only the user's own confirmation is remembered.
        decision = {"effect": policy.ALLOW, "rule": None, "message": "", "remembered": True}

    if decision["effect"] == policy.APPROVE:
        if ctx.get("initiator") in ("Routine", "Delegated", "Brief"):
            log = _log(ctx, tool_name, spec, args, "Refused", "Refused", decision.get("rule"),
                       "Routines cannot wait for approval")
            frappe.db.commit()
            return {"status": "refused", "log": log.name,
                    "message": "This action needs a person's approval, which a scheduled routine cannot get. Report it instead."}
        log = _log(ctx, tool_name, spec, args, "Approval Required", "Pending Approval",
                   decision.get("rule"), decision["message"])
        appr = _create_approval(ctx, tool_name, spec, args, decision, log)
        frappe.db.set_value("Coworker Action Log", log.name, "approval", appr.name, update_modified=False)
        frappe.db.commit()
        who = (f"a user with the role {decision['approver_role']}" if decision.get("approver_role")
               else "the user")
        return {"status": "pending", "approval": appr.name, "log": log.name,
                "message": f"Waiting for approval by {who} ({appr.name}). Do not claim it is done."}

    log = _log(ctx, tool_name, spec, args, "Allowed", "Executing", decision.get("rule"))
    frappe.db.commit()  # the record exists before the action does
    started = time.time()
    try:
        result = _invoke(spec, args, ctx.get("user"))
    except Exception as e:  # noqa: BLE001
        if not isinstance(e, (frappe.ValidationError, frappe.PermissionError, TypeError, ValueError)):
            frappe.log_error(title=f"Neotec AI tool {tool_name} failed")
        _finish_log(log.name, "Failed", error=e, started=started)
        frappe.db.commit()
        return {"status": "error", "message": _friendly_error(e), "log": log.name}
    _finish_log(log.name, "Succeeded", result=result, started=started)
    frappe.db.commit()
    return {"status": "ok", "result": result, "log": log.name}


# ---------------------------------------------------------------- approvals

def can_decide(approval, user=None) -> tuple[bool, str]:
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    if approval.status != "Pending":
        return False, _("This request is already {0}.").format(approval.status)
    if approval.approver_role:
        if user == approval.requested_by:
            return False, _("Segregation of duties: someone other than the requester must approve this.")
        if approval.approver_role in roles or "System Manager" in roles:
            return True, ""
        return False, _("Only users with the role {0} can approve this.").format(approval.approver_role)
    if user == approval.requested_by and settings().allow_self_approval:
        return True, ""
    if roles & {"Coworker Approver", "Coworker Admin", "System Manager"}:
        return True, ""
    return False, _("You cannot approve this request.")


def _update_tool_message(approval, status, payload):
    if not approval.message:
        return
    frappe.db.set_value("Coworker Message", approval.message,
                        {"status": status, "content": redact.to_json(payload, 20000)}, update_modified=False)


def remember_tool(approval) -> bool:
    """Adds the approval's tool to its chat's always-allowed list. Only for confirmations the requester could
    give themselves (no policy rule, no approver role)."""
    if approval.rule or approval.approver_role or not approval.conversation:
        return False
    if frappe.session.user != approval.requested_by:
        return False
    raw = frappe.db.get_value("Coworker Conversation", approval.conversation, "allowed_tools")
    try:
        tools = json.loads(raw) if raw else []
    except ValueError:
        tools = []
    if approval.tool not in tools:
        tools.append(approval.tool)
        frappe.db.set_value("Coworker Conversation", approval.conversation, "allowed_tools", json.dumps(tools),
                            update_modified=False)
    return True


def decide(approval_name: str, approve: bool, comment: str = "", remember: bool = False) -> dict:
    approval = frappe.get_doc("Coworker Approval", approval_name)
    ok, why = can_decide(approval)
    if not ok:
        frappe.throw(why, frappe.PermissionError)
    if approve and remember and remember_tool(approval):
        approval.remember = 1

    approval.decided_by = frappe.session.user
    approval.decided_on = now_datetime()
    approval.decision_comment = comment

    if not approve:
        approval.status = "Rejected"
        approval.flags.from_gateway = True
        approval.save(ignore_permissions=True)
        if approval.action_log:
            _finish_log(approval.action_log, "Rejected", error=comment or "Rejected")
        _update_tool_message(approval, "rejected", {
            "status": "rejected", "message": f"{frappe.session.user} rejected this action. {comment}".strip()})
        frappe.db.commit()
        resume(approval.conversation)
        return {"status": "Rejected"}

    spec = registry.get_tool(approval.tool)
    if not spec:
        frappe.throw(_("The tool {0} no longer exists.").format(approval.tool))
    args = json.loads(approval.arguments or "{}")
    started = time.time()
    try:
        result = _invoke(spec, args, approval.requested_by)
    except Exception as e:  # noqa: BLE001
        msg = _friendly_error(e)
        approval.status = "Failed"
        approval.result_preview = msg
        approval.flags.from_gateway = True
        approval.save(ignore_permissions=True)
        if approval.action_log:
            _finish_log(approval.action_log, "Failed", error=e, started=started)
        _update_tool_message(approval, "error", {"status": "error", "message": msg})
        frappe.db.commit()
        resume(approval.conversation)
        return {"status": "Failed", "message": msg}

    approval.status = "Executed"
    approval.result_preview = redact.to_json(result, 4000)
    approval.flags.from_gateway = True
    approval.save(ignore_permissions=True)
    if approval.action_log:
        _finish_log(approval.action_log, "Succeeded", result=result, started=started)
    _update_tool_message(approval, "ok", {"status": "ok", "approved_by": frappe.session.user, "result": result})
    frappe.db.commit()
    resume(approval.conversation)
    return {"status": "Executed"}


def resume(conversation: str | None):
    """Continues the conversation once nothing is waiting for a decision."""
    if not conversation or not frappe.db.exists("Coworker Conversation", conversation):
        return
    pending = frappe.db.count("Coworker Message", {"conversation": conversation, "status": "pending"})
    if pending:
        return
    from neotec_ai.agents.engine import runner

    runner.enqueue_turn(conversation, resume=True)


def expire_approvals():
    """Daily: pending requests past their expiry are closed so conversations do not hang."""
    from neotec_ai.agents.takeover import legacy_installed

    if legacy_installed():
        return
    for name in frappe.get_all("Coworker Approval",
                               filters={"status": "Pending", "expires_on": ("<", now_datetime())}, pluck="name"):
        appr = frappe.get_doc("Coworker Approval", name)
        appr.status = "Expired"
        appr.flags.from_gateway = True
        appr.save(ignore_permissions=True)
        if appr.action_log:
            _finish_log(appr.action_log, "Expired")
        _update_tool_message(appr, "expired", {"status": "expired", "message": "Nobody decided in time."})
        if appr.conversation:
            frappe.db.set_value("Coworker Conversation", appr.conversation, "status", "Idle")
    frappe.db.commit()


def purge_old_logs():
    from neotec_ai.agents.takeover import legacy_installed

    if legacy_installed():
        return
    days = int(settings().audit_retention_days or 0)
    if days <= 0:
        return
    cutoff = add_to_date(now_datetime(), days=-days)
    frappe.db.delete("Coworker Action Log", {"creation": ("<", cutoff)})
    frappe.db.commit()
