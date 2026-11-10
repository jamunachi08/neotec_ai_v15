# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Policy evaluation. Fail closed.

Order of outcomes:
  1. any matching Deny rule                  -> deny
  2. any matching Require Approval rule      -> approval (with the rule's approver role)
  3. tool granted in "Ask" mode              -> approval
  4. any matching Allow rule                 -> allow
  5. a read tool, or a write tool an admin granted in "Auto" mode -> allow
  6. otherwise (write tool, "Default" grant) -> approval

A condition that raises counts as matched for Deny and Require Approval rules (so a broken rule
refuses rather than opens) and as not matched for Allow rules.
"""

from __future__ import annotations

from fnmatch import fnmatchcase

ALLOW, DENY, APPROVE = "allow", "deny", "approve"


def _rule_scope_matches(rule: dict, ctx: dict) -> bool:
    pattern = (rule.get("tool_pattern") or "*").strip() or "*"
    if not any(fnmatchcase(ctx["tool"], p.strip()) for p in pattern.split(",") if p.strip()):
        return False
    if rule.get("target_doctype") and rule["target_doctype"] != ctx.get("doctype"):
        return False
    if rule.get("coworker") and rule["coworker"] != ctx.get("coworker"):
        return False
    initiator = rule.get("initiator") or "Any"
    if initiator != "Any" and initiator != ctx.get("initiator"):
        return False
    role = rule.get("applies_to_role")
    if role and role not in (ctx.get("roles") or ()):
        return False
    return True


def rule_matches(rule: dict, ctx: dict, evaluator) -> bool:
    if not _rule_scope_matches(rule, ctx):
        return False
    cond = (rule.get("condition") or "").strip()
    if not cond:
        return True
    try:
        return bool(evaluator(cond, ctx))
    except Exception:  # noqa: BLE001 - fail closed
        return rule.get("effect") in ("Deny", "Require Approval")


def decide(rules: list[dict], ctx: dict, grant_mode: str, evaluator) -> dict:
    matched = [r for r in rules if r.get("enabled", 1) and rule_matches(r, ctx, evaluator)]

    for r in matched:
        if r.get("effect") == "Deny":
            return {"effect": DENY, "rule": r.get("name"),
                    "message": r.get("message") or f"Refused by policy rule '{r.get('name')}'."}
    for r in matched:
        if r.get("effect") == "Require Approval":
            return {"effect": APPROVE, "rule": r.get("name"), "approver_role": r.get("approver_role"),
                    "message": r.get("message") or f"Needs approval under rule '{r.get('name')}'."}
    if grant_mode == "Ask":
        return {"effect": APPROVE, "rule": None, "approver_role": None,
                "message": "This coworker asks before using this tool."}
    for r in matched:
        if r.get("effect") == "Allow":
            return {"effect": ALLOW, "rule": r.get("name"), "message": ""}
    if not ctx.get("is_write") or grant_mode == "Auto":
        return {"effect": ALLOW, "rule": None, "message": ""}
    return {"effect": APPROVE, "rule": None, "approver_role": None,
            "message": "Changes to data need confirmation."}


# ---------------------------------------------------------------- Frappe glue

def load_rules() -> list[dict]:
    import frappe

    return frappe.get_all(
        "Coworker Policy Rule",
        filters={"enabled": 1},
        fields=["name", "enabled", "effect", "tool_pattern", "target_doctype", "coworker",
                "initiator", "applies_to_role", "condition", "approver_role", "message", "priority"],
        order_by="priority asc, name asc",
    )


def frappe_evaluator(expr: str, ctx: dict) -> bool:
    import frappe
    from frappe.utils import cint, flt, getdate, nowdate

    names = {
        "tool": ctx.get("tool"),
        "args": ctx.get("args") or {},
        "doctype": ctx.get("doctype"),
        "is_write": bool(ctx.get("is_write")),
        "risk": ctx.get("risk"),
        "user": ctx.get("user"),
        "roles": list(ctx.get("roles") or []),
        "coworker": ctx.get("coworker"),
        "initiator": ctx.get("initiator"),
        "flt": flt, "cint": cint, "getdate": getdate, "nowdate": nowdate,
    }
    return bool(frappe.safe_eval(expr, None, names))
