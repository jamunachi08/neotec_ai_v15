# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""ERPNext as a governed MCP server (Streamable HTTP, JSON responses).

Endpoint:  POST https://<site>/api/method/neotec_ai.agents.mcp.server.handle
Auth:      Authorization: token <api_key>:<api_secret>   (a normal ERPNext API key of the person)

Every tools/call passes through the same gateway as chat: grants of the configured MCP coworker,
residency guard, policies, approvals and the audit trail. Calls run with that person's permissions.
"""

from __future__ import annotations

import json

import frappe
from werkzeug.wrappers import Response

import neotec_ai
from neotec_ai.agents.engine import gateway, registry, runner

SUPPORTED = ("2025-06-18", "2025-03-26", "2024-11-05")


def _reply(payload, status=200):
    return Response(json.dumps(payload, ensure_ascii=False, default=str), status=status,
                    content_type="application/json")


def _error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _coworker():
    s = gateway.settings()
    if not (s.enabled and s.mcp_enabled and s.mcp_coworker):
        return None
    cw = frappe.get_doc("AI Coworker", s.mcp_coworker)
    return cw if cw.enabled and runner.can_use(cw) else None


def _tools_list(cw):
    grants, specs = runner.granted_tools(cw)
    out = []
    for s in specs:
        full = registry.get_tool(s["name"])
        out.append({
            "name": s["name"],
            "title": full.get("label") if full else s["name"],
            "description": s["description"],
            "inputSchema": s["schema"],
            "annotations": {"readOnlyHint": not (full or {}).get("is_write", True),
                            "destructiveHint": (full or {}).get("risk") == "High"},
        })
    return out


def _call(cw, params):
    name = params.get("name")
    args = params.get("arguments") or {}
    grants, _specs = runner.granted_tools(cw)
    provider_loc = "External"  # an MCP client's model location is unknown: treat as external
    ctx = {"user": frappe.session.user, "coworker": cw.name, "conversation": None, "initiator": "MCP",
           "provider": None, "provider_location": provider_loc, "grants": grants,
           "roles": set(frappe.get_roles())}
    frappe.flags.ntc_external = True
    frappe.flags.ntc_coworker = cw.name
    frappe.flags.ntc_mcp_call = True
    frappe.flags.ntc_run = None
    out = gateway.execute(ctx, name, args)
    result = out.get("result")
    if isinstance(result, dict) and "__blocks__" in result:
        result = result["__blocks__"]
    payload = {k: v for k, v in out.items() if k not in ("result",)}
    if result is not None:
        payload["result"] = result
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if gateway.settings().redact_external:
        from neotec_ai.agents.engine.redact import mask_all

        text = mask_all(text)
    return {"content": [{"type": "text", "text": text}], "isError": out.get("status") != "ok"}


@frappe.whitelist(methods=["POST", "GET"])
def handle():
    if frappe.request.method == "GET":
        return Response("Use POST (Streamable HTTP, JSON responses).", status=405)
    if frappe.session.user == "Guest":
        return _reply(_error(None, -32001, "Authentication required"), 401)
    try:
        body = json.loads(frappe.request.get_data(as_text=True) or "{}")
    except ValueError:
        return _reply(_error(None, -32700, "Parse error"), 400)

    if isinstance(body, list):
        replies = [r for r in (_dispatch(m) for m in body) if r is not None]
        return _reply(replies) if replies else Response(status=202)
    reply = _dispatch(body)
    return _reply(reply) if reply is not None else Response(status=202)


def _dispatch(msg):
    rid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}
    if rid is None:  # notification
        return None
    try:
        if method == "initialize":
            requested = params.get("protocolVersion")
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": requested if requested in SUPPORTED else SUPPORTED[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "neotec-ai-erpnext", "version": neotec_ai.__version__},
                "instructions": "ERPNext tools governed by company policy. Writes may return status 'pending' "
                                "until a person approves them in ERPNext.",
            }}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": rid, "result": {}}
        cw = _coworker()
        if not cw:
            return _error(rid, -32002, "The MCP endpoint is disabled or you have no access to its coworker.")
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": rid, "result": {"tools": _tools_list(cw)}}
        if method == "tools/call":
            return {"jsonrpc": "2.0", "id": rid, "result": _call(cw, params)}
        return _error(rid, -32601, f"Method not found: {method}")
    except Exception as e:  # noqa: BLE001
        frappe.log_error(title="Neotec AI MCP request failed")
        return _error(rid, -32603, f"Internal error: {e.__class__.__name__}")
