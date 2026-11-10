# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Minimal MCP client (Streamable HTTP) so coworkers can use tools from external MCP servers.

Discovered tools are registered as ``mcp_<server>__<tool>`` and go through the same gateway as built-in
tools. Tools not listed as read-only on the server record are treated as changing data.
"""

from __future__ import annotations

import itertools
import json
import re

PROTOCOL = "2025-06-18"
_ids = itertools.count(1)


def slug(server_name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (server_name or "").lower())[:24] or "server"


def _parse(resp):
    ctype = resp.headers.get("Content-Type", "")
    if "text/event-stream" in ctype:
        last = None
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if isinstance(data, dict) and ("result" in data or "error" in data):
                    last = data
        if last is None:
            raise RuntimeError("The MCP server sent an event stream without a result.")
        return last
    return resp.json()


class Session:
    def __init__(self, url, headers=None, timeout=60):
        self.url = url
        self.headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                        **(headers or {})}
        self.timeout = timeout
        self.session_id = None

    def _post(self, payload, expect_reply=True):
        import requests

        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
            headers["MCP-Protocol-Version"] = PROTOCOL
        resp = requests.post(self.url, headers=headers, data=json.dumps(payload), timeout=self.timeout)
        if resp.headers.get("Mcp-Session-Id"):
            self.session_id = resp.headers["Mcp-Session-Id"]
        if not expect_reply:
            return None
        if resp.status_code >= 400:
            raise RuntimeError(f"MCP server returned HTTP {resp.status_code}: {resp.text[:300]}")
        data = _parse(resp)
        if "error" in data:
            raise RuntimeError(f"MCP error: {data['error'].get('message')}")
        return data.get("result")

    def open(self):
        self._post({"jsonrpc": "2.0", "id": next(_ids), "method": "initialize",
                    "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                               "clientInfo": {"name": "neotec-coworker", "version": "1"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_reply=False)
        return self

    def list_tools(self):
        tools, cursor = [], None
        for _ in range(20):
            params = {"cursor": cursor} if cursor else {}
            res = self._post({"jsonrpc": "2.0", "id": next(_ids), "method": "tools/list", "params": params}) or {}
            tools.extend(res.get("tools") or [])
            cursor = res.get("nextCursor")
            if not cursor:
                break
        return tools

    def call(self, name, arguments):
        return self._post({"jsonrpc": "2.0", "id": next(_ids), "method": "tools/call",
                           "params": {"name": name, "arguments": arguments or {}}})


def session_for(doc):
    headers = {}
    if doc.get("auth_header_value"):
        headers[doc.auth_header_name or "Authorization"] = doc.get_password("auth_header_value", raise_exception=False)
    return Session(doc.url, headers).open()


def sync(server_name: str) -> int:
    import frappe
    from frappe.utils import now_datetime

    doc = frappe.get_doc("Coworker MCP Server", server_name)
    try:
        tools = session_for(doc).list_tools()
    except Exception as e:  # noqa: BLE001
        doc.db_set("status", f"Failed: {str(e)[:300]}")
        raise
    slim = [{"name": t.get("name"), "description": (t.get("description") or "")[:1000],
             "inputSchema": t.get("inputSchema") or {"type": "object", "properties": {}},
             "readOnlyHint": bool((t.get("annotations") or {}).get("readOnlyHint"))} for t in tools if t.get("name")]
    doc.db_set({"tools_cache": json.dumps(slim, ensure_ascii=False, indent=1), "last_synced": now_datetime(),
                "status": f"OK: {len(slim)} tools"})
    from neotec_ai.agents.setup.seed import sync_tool_registry

    sync_tool_registry()
    return len(slim)


def registry_entries(row) -> dict:
    """Turns one cached server row into registry entries."""
    try:
        tools = json.loads(row.tools_cache or "[]")
    except ValueError:
        return {}
    read_only = {t.strip() for t in (row.read_only_tools or "").splitlines() if t.strip()}
    prefix = f"mcp_{slug(row.name)}__"
    out = {}
    for t in tools:
        tname = t["name"]
        schema = t.get("inputSchema") or {"type": "object", "properties": {}}
        if schema.get("type") != "object":
            schema = {"type": "object", "properties": {}}
        schema.setdefault("properties", {})
        out[prefix + tname] = {
            "name": prefix + tname,
            "label": f"{row.name}: {tname}",
            "description": f"[{row.name}] {t.get('description') or tname}",
            "schema": schema,
            "category": "External (MCP)",
            "is_write": tname not in read_only,
            "risk": "Medium",
            "source": "MCP",
            "fn": _caller(row.name, tname),
        }
    return out


def _caller(server_name, tool_name):
    def run(**kwargs):
        import frappe

        doc = frappe.get_doc("Coworker MCP Server", server_name)
        if not doc.enabled:
            frappe.throw(f"MCP server {server_name} is disabled.")
        res = session_for(doc).call(tool_name, kwargs) or {}
        texts = [c.get("text", "") for c in res.get("content") or [] if c.get("type") == "text"]
        out = {"server": server_name, "tool": tool_name, "is_error": bool(res.get("isError")),
               "text": "\n".join(texts)[:20000]}
        if res.get("structuredContent"):
            out["data"] = res["structuredContent"]
        return out

    return run
