# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Idempotent setup for the shared gateway, run on install and every migrate.

* Moves the assistant's own provider settings (Neotec Settings 3.x) into a Coworker Provider, once.
* Creates the standard routes (Default, Agents, Automation, Assistant, Writing, Vision); the administrator
  fills or reorders their providers. An empty route falls back to the default chain.
* Grants new 4.0 tools, and tools other apps offer with ``grant_to``, once per tool. A grant an administrator
  later removes is not added back.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

ROUTES = {
    "Default": "Used when nothing more specific matches.",
    "Agents": "Coworker chats (after the coworker's own provider).",
    "Automation": "Playbooks, routines, chains and live briefs.",
    "Assistant": "The Alt+K assistant and the BI builder's AI bar.",
    "Writing": "Spell check, translation and rewriting on text fields.",
    "Vision": "Reading images such as bank slips. Add providers marked Reads Images.",
}

V4_GRANTS = {
    "General Assistant": {"list_data_sources": "Default", "describe_data_source": "Default", "query_data": "Default",
                          "delegate_task": "Default"},
    "Finance Analyst": {"list_data_sources": "Default", "describe_data_source": "Default", "query_data": "Default",
                        "save_bi_report": "Default"},
    "Sales Assistant": {"list_data_sources": "Default", "describe_data_source": "Default", "query_data": "Default",
                        "delegate_task": "Default"},
}

LEGACY_PRESET = {"Google Gemini": ("Google Gemini", "OpenAI Compatible", "https://generativelanguage.googleapis.com/v1beta/openai"),
                 "Anthropic Claude": ("Anthropic Claude", "Anthropic", "https://api.anthropic.com/v1"),
                 "OpenAI": ("OpenAI", "OpenAI Compatible", "https://api.openai.com/v1"),
                 "OpenAI-Compatible / Ollama": ("Custom", "OpenAI Compatible", "http://localhost:11434/v1")}


def run():
    ensure_routes()
    migrate_assistant_provider()
    ensure_grants()
    frappe.db.commit()


def ensure_routes():
    default = frappe.db.get_single_value("Coworker Settings", "default_provider") or frappe.db.get_value(
        "Coworker Provider", {"enabled": 1, "is_default": 1}, "name")
    for name, desc in ROUTES.items():
        if frappe.db.exists("Neotec AI Route", name):
            continue
        doc = frappe.get_doc({"doctype": "Neotec AI Route", "route_name": name, "enabled": 1, "description": desc,
                              "used_by": {"Assistant": "Assistant\nBI", "Agents": "Agents"}.get(name, name)})
        if name == "Default" and default:
            doc.append("providers", {"provider": default})
        doc.insert(ignore_permissions=True)


def migrate_assistant_provider():
    """3.x kept the assistant's provider, model and key in Neotec Settings. Make it a Coworker Provider (once)
    so the assistant shares routes, fallback, residency and the usage ledger."""
    s = frappe.get_single("Neotec Settings")
    if not s.meta.has_field("ai_provider") or s.get("ai_provider"):
        return
    if not (s.get("provider") and s.get("model")):
        return
    key = s.get_password("api_key", raise_exception=False) if s.get("api_key") else None
    preset, ptype, base = LEGACY_PRESET.get(s.provider, ("Custom", "OpenAI Compatible", ""))
    base = (s.get("api_endpoint") or base or "").rstrip("/")
    if s.provider == "Google Gemini" and base.endswith("/v1beta"):
        base += "/openai"   # 3.x used Gemini's native API; the shared client speaks its OpenAI-compatible one
    name = f"Assistant ({s.provider})"[:140]
    if not frappe.db.exists("Coworker Provider", name):
        local = s.provider == "OpenAI-Compatible / Ollama" and any(h in base for h in ("localhost", "127.0.0.1", "192.168.", "10."))
        doc = frappe.get_doc({
            "doctype": "Coworker Provider", "provider_name": name, "preset": preset, "provider_type": ptype,
            "enabled": 1, "base_url": base, "model": s.model, "api_key": key or None,
            "data_location": "On-Premises" if local else "External",
            "temperature": s.get("temperature") or 0.2, "max_output_tokens": cint(s.get("max_tokens")) or 2048,
            "timeout": cint(s.get("request_timeout")) or 60,
        })
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True)
    frappe.db.set_single_value("Neotec Settings", "ai_provider", name)


def ensure_grants():
    from neotec_ai.agents.engine import registry

    tools = registry.all_tools()
    wanted: dict[str, dict] = {k: dict(v) for k, v in V4_GRANTS.items()}
    for name, spec in tools.items():
        for coworker, mode in (spec.get("grant_to") or {}).items():
            wanted.setdefault(coworker, {})[name] = mode or "Default"
    done = set(frappe.get_all("Coworker Tool", filters={"auto_granted": 1}, pluck="name")) \
        if frappe.get_meta("Coworker Tool").has_field("auto_granted") else set()
    granted_now = set()
    for coworker, grants in wanted.items():
        if not frappe.db.exists("AI Coworker", coworker):
            continue
        doc = frappe.get_doc("AI Coworker", coworker)
        have = {g.tool for g in doc.tools}
        changed = False
        for tool_name, mode in grants.items():
            if tool_name in done or tool_name in have or not frappe.db.exists("Coworker Tool", tool_name):
                continue
            doc.append("tools", {"tool": tool_name, "mode": mode})
            changed = True
            granted_now.add(tool_name)
        if changed:
            doc.flags.ignore_validate = True
            doc.save(ignore_permissions=True)
    for tool_name in granted_now | {t for g in wanted.values() for t in g if frappe.db.exists("Coworker Tool", t)}:
        frappe.db.set_value("Coworker Tool", tool_name, "auto_granted", 1, update_modified=False)
