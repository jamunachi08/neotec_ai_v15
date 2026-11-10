# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Configuration checks. Finds the mistakes that make automation fail quietly: a playbook whose coworker lacks a
tool, a routine that runs as a disabled user, a trigger watching a DocType that no longer exists after an
upgrade, a fallback provider that would send data further away, a channel with no address.

Each finding has a stable fingerprint, so the health job opens an issue once and closes it when fixed.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

from neotec_ai.agents.automation import common


def _f(code, obj, title, detail="", fix="", severity="warn", **links):
    return {"fingerprint": f"config:{code}:{obj}"[:140], "title": title[:140], "detail": detail, "fix": fix,
            "severity": severity, "links": links}


def _user_ok(user):
    return bool(user) and bool(frappe.db.get_value("User", user, "enabled"))


def checks() -> list[dict]:
    from neotec_ai.agents.engine import registry

    out = []
    s = frappe.get_single("Coworker Settings")
    tools = registry.all_tools()
    disabled_tools = set(frappe.get_all("Coworker Tool", filters={"enabled": 0}, pluck="name"))

    # providers
    default = s.default_provider or frappe.db.get_value("Coworker Provider", {"is_default": 1, "enabled": 1}, "name")
    if not default:
        out.append(_f("provider", "default", "No default AI provider", fix="Add one in the setup wizard.",
                      severity="critical"))
    from neotec_ai.agents.setup import open_models

    in_use = {default, s.fallback_provider}
    in_use |= set(frappe.get_all("AI Coworker", filters={"enabled": 1, "provider": ["is", "set"]}, pluck="provider"))
    in_use |= set(frappe.get_all("Coworker Playbook", filters={"enabled": 1, "provider": ["is", "set"]},
                                 pluck="provider"))
    in_use.discard(None)
    for p in frappe.get_all("Coworker Provider", filters={"enabled": 1},
                            fields=["name", "data_location", "base_url", "api_key", "provider_type", "model",
                                    "tool_test_status"]):
        if p.name in in_use and p.tool_test_status == "Failed":
            out.append(_f("selftest", p.name, f"Provider {p.name} failed the tool-calling self-test",
                          severity="critical", provider=p.name,
                          detail=f"Model {p.model}. Playbooks using it will not run.",
                          fix="Pick a stronger model (see Open models guide) and press Test tool calling."))
        elif p.name in in_use and (p.tool_test_status or "Not tested") == "Not tested":
            out.append(_f("selftest-none", p.name, f"Provider {p.name} has not run the tool-calling self-test",
                          severity="info", provider=p.name, fix="Open the provider and press Test tool calling."))
        if open_models.is_free_hosted(p.base_url, p.model):
            out.append(_f("freetier", p.name, f"Provider {p.name} uses a free hosted model", provider=p.name,
                          detail="Free tiers may log prompts or use them for training.",
                          fix="Keep it away from sensitive coworkers, keep residency Guarded or Strict, and use a "
                              "self-hosted or paid provider for production."))
        if s.residency_mode == "Strict" and p.data_location == "External":
            out.append(_f("strict", p.name, f"Provider {p.name} is external but residency is Strict",
                          fix="Disable it or change the residency mode.", provider=p.name))
        local = any(h in (p.base_url or "") for h in ("localhost", "127.0.0.1", "11434"))
        if p.data_location == "External" and not p.api_key and not local:
            out.append(_f("nokey", p.name, f"Provider {p.name} has no API key", provider=p.name,
                          fix="Enter the API key and run Test connection."))
    if s.fallback_provider and default:
        a = frappe.db.get_value("Coworker Provider", default, "data_location")
        b = frappe.db.get_value("Coworker Provider", s.fallback_provider, "data_location")
        if not common.fallback_allowed(a, b, s.residency_mode):
            out.append(_f("fallback", s.fallback_provider, "Fallback provider is further away than the main one",
                          detail=f"Main: {a}. Fallback: {b}. It will never be used.",
                          fix="Pick a fallback in the same or a closer location.", provider=s.fallback_provider))

    # coworkers
    for cw in frappe.get_all("AI Coworker", filters={"enabled": 1}, pluck="name"):
        doc = frappe.get_cached_doc("AI Coworker", cw)
        bad = [g.tool for g in doc.tools if (g.mode or "Default") != "Off"
               and (g.tool not in tools or g.tool in disabled_tools)]
        if bad:
            out.append(_f("grant", cw, f"Coworker {cw} is granted missing or disabled tools",
                          detail=", ".join(bad), fix="Remove the grants or enable the tools.", severity="info"))

    # playbooks
    for pb in frappe.get_all("Coworker Playbook", filters={"enabled": 1}, pluck="name"):
        doc = frappe.get_cached_doc("Coworker Playbook", pb)
        if not frappe.db.exists("AI Coworker", doc.coworker) or not cint(
                frappe.db.get_value("AI Coworker", doc.coworker, "enabled")):
            out.append(_f("pbcw", pb, f"Playbook {pb} uses a disabled coworker", playbook=pb, severity="critical",
                          fix=f"Enable {doc.coworker} or pick another coworker."))
            continue
        cw = frappe.get_cached_doc("AI Coworker", doc.coworker)
        granted = {g.tool for g in cw.tools if (g.mode or "Default") != "Off"}
        missing = [t for t in common.normalise_tools(doc.required_tools)
                   if t not in granted or t not in tools or t in disabled_tools]
        if missing:
            out.append(_f("pbtools", pb, f"Playbook {pb} needs tools its coworker cannot use", playbook=pb,
                          detail=", ".join(missing), fix=f"Grant them to {cw.name} or edit Required tools."))
        if doc.provider and not cint(frappe.db.get_value("Coworker Provider", doc.provider, "enabled")):
            out.append(_f("pbprov", pb, f"Playbook {pb} overrides with a disabled provider", playbook=pb,
                          provider=doc.provider, fix="Clear the override or enable the provider."))

    # routines
    for r in frappe.get_all("Coworker Routine", filters={"enabled": 1},
                            fields=["name", "run_as", "target", "playbook", "chain", "next_run"]):
        if not _user_ok(r.run_as):
            out.append(_f("rtuser", r.name, f"Routine {r.name} runs as a disabled user", routine=r.name,
                          severity="critical", fix="Change Run As or disable the routine."))
        if r.target == "Playbook" and r.playbook and not cint(
                frappe.db.get_value("Coworker Playbook", r.playbook, "enabled")):
            out.append(_f("rtpb", r.name, f"Routine {r.name} runs a disabled playbook", routine=r.name,
                          playbook=r.playbook, fix="Enable the playbook or the routine will fail."))
        if r.target == "Chain" and r.chain and not cint(frappe.db.get_value("Coworker Chain", r.chain, "enabled")):
            out.append(_f("rtch", r.name, f"Routine {r.name} runs a disabled chain", routine=r.name, chain=r.chain,
                          fix="Enable the chain."))
        if not r.next_run:
            out.append(_f("rtnext", r.name, f"Routine {r.name} has no next run time", routine=r.name,
                          fix="Open and save the routine."))

    # triggers
    for t in frappe.get_all("Coworker Trigger", filters={"enabled": 1},
                            fields=["name", "document_type", "playbook", "condition", "run_as", "fixed_user"]):
        if not frappe.db.exists("DocType", t.document_type):
            out.append(_f("trdt", t.name, f"Trigger {t.name} watches a DocType that no longer exists",
                          trigger=t.name, severity="critical", detail=t.document_type,
                          fix="Point it at the new DocType or disable it."))
        if not cint(frappe.db.get_value("Coworker Playbook", t.playbook, "enabled")):
            out.append(_f("trpb", t.name, f"Trigger {t.name} starts a disabled playbook", trigger=t.name,
                          playbook=t.playbook))
        if (t.condition or "").strip():
            try:
                compile(t.condition, "<condition>", "eval")
            except SyntaxError:
                out.append(_f("trcond", t.name, f"Trigger {t.name} has an invalid condition", trigger=t.name,
                              severity="critical"))
        if t.run_as == "Fixed User" and not _user_ok(t.fixed_user):
            out.append(_f("truser", t.name, f"Trigger {t.name} runs as a disabled user", trigger=t.name))

    # chains
    for c in frappe.get_all("Coworker Chain", filters={"enabled": 1}, pluck="name"):
        doc = frappe.get_cached_doc("Coworker Chain", c)
        off = [r.playbook for r in doc.steps if not cint(frappe.db.get_value("Coworker Playbook", r.playbook, "enabled"))]
        if off:
            out.append(_f("chpb", c, f"Chain {c} has disabled steps", chain=c, detail=", ".join(off),
                          fix="Enable the playbooks or remove the steps."))

    # channels
    for ch in frappe.get_all("Coworker Channel", filters={"enabled": 1},
                             fields=["name", "last_error", "last_delivery"]):
        if ch.last_error:
            out.append(_f("chan", ch.name, f"Channel {ch.name} failed on its last delivery",
                          detail=ch.last_error, fix="Check the address, then press Send test.", severity="warn"))

    # MCP
    if frappe.db.table_exists("Coworker MCP Server"):
        for m in frappe.get_all("Coworker MCP Server", filters={"enabled": 1}, fields=["name", "tools_cache"]):
            if not m.tools_cache:
                out.append(_f("mcp", m.name, f"External MCP server {m.name} has no tools loaded", severity="info",
                              fix="Open it and refresh the tool list."))
    return out
