# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Tools on demand. A coworker with many granted tools starts with a core set plus ``find_tools``; when it
needs something else it searches, and the matches are loaded for the rest of the conversation. The gateway
still checks every call against the grants, so loading a tool never widens what a coworker may do.

Pure Python.
"""

from __future__ import annotations

import re

CORE = ("find_tools", "render_ui", "search_documents", "get_document", "describe_doctype", "count_documents",
        "aggregate", "current_user", "remember_fact", "approval_status", "global_search")

FIND_TOOLS_SPEC = {
    "name": "find_tools",
    "description": ("Find more tools you have been granted but are not loaded yet (finance, stock, KSA "
                    "compliance, reports, BI, automation, other apps). Describe the task in a few words; the "
                    "matching tools become available on your next step."),
    "schema": {"type": "object", "properties": {"query": {"type": "string", "description": "What you need to do"}},
               "required": ["query"]},
}

_WORD = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)
_STOP = {"the", "a", "an", "of", "for", "to", "and", "or", "in", "on", "by", "with", "me", "my", "show", "get",
         "list", "find", "tool", "tools", "need", "want", "please"}


def _tokens(text: str) -> list[str]:
    out = []
    for w in _WORD.findall((text or "").lower()):
        if w in _STOP or len(w) < 2:
            continue
        out.append(w[:-1] if len(w) > 4 and w.endswith("s") else w)
    return out


def rank(query: str, specs: list[dict], k: int = 8) -> list[dict]:
    """specs: [{"name", "description", "category"?, "label"?}] -> best k by keyword overlap."""
    q = set(_tokens(query))
    if not q:
        return []
    scored = []
    for s in specs:
        name_t = set(_tokens(s.get("name", "").replace("_", " ")))
        label_t = set(_tokens(s.get("label", "")))
        cat_t = set(_tokens(s.get("category", "")))
        desc_t = set(_tokens(s.get("description", "")))
        score = 3 * len(q & name_t) + 2 * len(q & label_t) + 2 * len(q & cat_t) + len(q & desc_t)
        for w in q:   # prefix matches ("receiv" ~ "receivables")
            if len(w) >= 4 and any(t.startswith(w) or w.startswith(t) for t in name_t | desc_t if len(t) >= 4):
                score += 1
        if score:
            scored.append((score, s["name"], s))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [s for _sc, _n, s in scored[:k]]


def split(specs: list[dict], active: list[str], threshold: int) -> tuple[list[dict], bool]:
    """Returns (specs to send, on_demand). Below the threshold every tool is sent."""
    if threshold <= 0 or len(specs) <= threshold:
        return specs, False
    keep = set(CORE) | set(active or [])
    chosen = [s for s in specs if s["name"] in keep]
    return chosen + [FIND_TOOLS_SPEC], True
