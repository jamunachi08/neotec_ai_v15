# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Moving a site from the separate Coworker app (1.x) to Neotec AI 4.

Neotec AI ships the same coworker DocTypes and Pages under its own module, "Neotec AI Agents". This module makes
sure every one of them belongs to that module before the old app is uninstalled, because uninstalling an app
deletes the DocTypes (and their tables) of its modules. Nothing is copied: the records stay where they are.

    install Neotec AI 4 -> migrate (records move here) -> uninstall the old app -> done

Runs on every migrate (idempotent), on install, and again just before the old app is uninstalled.
While both apps are installed, Neotec AI's own coworker scheduler jobs and triggers stand aside so nothing runs
twice; see ``legacy_installed``.
"""

from __future__ import annotations

import json
import os

import frappe

LEGACY_APP = "neotec_coworker"
LEGACY_MODULE = "Neotec Coworker"
MODULE = "Neotec AI Agents"
LEGACY_MCP = "/api/method/neotec_coworker.mcp.server.handle"
MCP = "/api/method/neotec_ai.agents.mcp.server.handle"


def legacy_installed() -> bool:
    """True while the old app is still installed on this site (cached for the request)."""
    if frappe.flags.get("ntc_legacy") is None:
        try:
            frappe.flags.ntc_legacy = LEGACY_APP in (frappe.get_installed_apps() or [])
        except Exception:  # noqa: BLE001 - very early in install
            frappe.flags.ntc_legacy = False
    return bool(frappe.flags.ntc_legacy)


def owned(kind: str) -> list[str]:
    """Names of the DocTypes ('doctype') or Pages ('page') this app ships in the agents module."""
    folder = frappe.get_app_path("neotec_ai", "neotec_ai_agents", kind)
    out = []
    if not os.path.isdir(folder):
        return out
    for entry in sorted(os.listdir(folder)):
        path = os.path.join(folder, entry, f"{entry}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                out.append(json.load(fh)["name"])
    return out


def ensure_module_def():
    if not frappe.db.exists("Module Def", MODULE):
        frappe.get_doc({"doctype": "Module Def", "module_name": MODULE, "app_name": "neotec_ai",
                        "custom": 0}).insert(ignore_permissions=True)
    elif frappe.db.get_value("Module Def", MODULE, "app_name") != "neotec_ai":
        frappe.db.set_value("Module Def", MODULE, "app_name", "neotec_ai", update_modified=False)


def run() -> dict:
    ensure_module_def()
    moved = {"doctype": [], "page": []}
    for kind, doctype in (("doctype", "DocType"), ("page", "Page")):
        for name in owned(kind):
            current = frappe.db.get_value(doctype, name, "module")
            if current and current != MODULE:
                frappe.db.set_value(doctype, name, "module", MODULE, update_modified=False)
                moved[kind].append(name)

    if legacy_installed():
        # The old app's own sync may have re-imported its older definitions; make ours the current schema.
        for name in owned("doctype"):
            try:
                frappe.reload_doc(MODULE, "doctype", frappe.scrub(name), force=True)
            except Exception:  # noqa: BLE001 - a single DocType must not stop the move
                frappe.log_error(title=f"Neotec AI: could not reload {name} during the move")
        for name in owned("page"):
            try:
                frappe.reload_doc(MODULE, "page", frappe.scrub(name), force=True)
            except Exception:  # noqa: BLE001
                frappe.log_error(title=f"Neotec AI: could not reload page {name} during the move")
        for name in owned("doctype") + owned("page"):
            for doctype in ("DocType", "Page"):
                if frappe.db.get_value(doctype, name, "module") not in (None, MODULE):
                    frappe.db.set_value(doctype, name, "module", MODULE, update_modified=False)

    _fix_settings()
    if moved["doctype"] or moved["page"]:
        frappe.clear_cache()
    return moved


def _fix_settings():
    if not frappe.db.exists("DocType", "Coworker Settings"):
        return
    endpoint = frappe.db.get_single_value("Coworker Settings", "mcp_endpoint")
    if endpoint and LEGACY_MCP in endpoint:
        frappe.db.set_single_value("Coworker Settings", "mcp_endpoint", endpoint.replace(LEGACY_MCP, MCP))


def before_app_uninstall(app_name=None, *args, **kwargs):
    """Called by Frappe before any app is uninstalled. For the old Coworker app, claim the records first."""
    if app_name != LEGACY_APP:
        return
    run()
    frappe.db.commit()


def status() -> dict:
    """For the setup page: is the move finished, and is it safe to uninstall the old app?"""
    names = owned("doctype")
    pending = [n for n in names if frappe.db.get_value("DocType", n, "module") not in (None, MODULE)]
    pages = [n for n in owned("page") if frappe.db.get_value("Page", n, "module") not in (None, MODULE)]
    return {"legacy_installed": legacy_installed(), "doctypes": len(names), "pending": pending + pages,
            "safe_to_uninstall": not pending and not pages}
