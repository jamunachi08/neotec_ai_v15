# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Connected apps. An app that can send its AI calls through Neotec AI declares, in its hooks.py:

    neotec_ai_integrations = ["my_app.ai.neotec_integration"]

where the function returns {"app", "label", "description", "settings_doctype", "field", "on_value",
"off_value"}. The setup page lists these and switches them with one click; the app itself reads its own field.
"""

from __future__ import annotations

import frappe
from frappe import _


def _require_admin():
    if not (set(frappe.get_roles()) & {"System Manager", "Coworker Admin"}):
        frappe.throw(_("Only an administrator can change connected apps."), frappe.PermissionError)


def declared() -> list[dict]:
    out = []
    for path in frappe.get_hooks("neotec_ai_integrations") or []:
        try:
            spec = frappe.get_attr(path)()
            if isinstance(spec, dict) and spec.get("app") and spec.get("settings_doctype") and spec.get("field"):
                out.append(spec)
        except Exception:  # noqa: BLE001
            frappe.log_error(title="Neotec AI: integration hook failed", message=path)
    return out


@frappe.whitelist()
def list_integrations() -> list[dict]:
    _require_admin()
    rows = []
    for spec in declared():
        try:
            value = frappe.db.get_single_value(spec["settings_doctype"], spec["field"])
        except Exception:  # noqa: BLE001
            value = None
        rows.append({**spec, "value": value, "connected": value == spec.get("on_value")})
    return rows


@frappe.whitelist(methods=["POST"])
def set_integration(app: str, enabled) -> dict:
    _require_admin()
    spec = next((s for s in declared() if s["app"] == app), None)
    if not spec:
        frappe.throw(_("{0} does not offer a Neotec AI connection.").format(app))
    value = spec.get("on_value") if frappe.utils.cint(enabled) else spec.get("off_value")
    frappe.db.set_single_value(spec["settings_doctype"], spec["field"], value)
    frappe.clear_document_cache(spec["settings_doctype"], spec["settings_doctype"])
    return {"app": app, "value": value}


@frappe.whitelist()
def get_usage(days: int = 30) -> dict:
    _require_admin()
    from neotec_ai.platform import gateway

    return gateway.usage(days)


@frappe.whitelist(methods=["POST"])
def test_route(route: str | None = None) -> dict:
    """Sends a one-word check through a route (or the default chain) and reports who answered."""
    _require_admin()
    from neotec_ai.platform import gateway

    res = gateway.complete("You are a connectivity check.", "Reply with the single word OK.",
                           app="neotec_ai", feature="route_test", purpose=route or None, max_tokens=10)
    return {"provider": res.provider, "model": res.model, "fell_back": res.fell_back, "reply": res.text[:60],
            "attempts": res.attempts}
