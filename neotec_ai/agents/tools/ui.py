# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""render_ui: lets a coworker answer with tables, KPI tiles, charts, document lists, forms and quick actions."""

from __future__ import annotations

from neotec_ai.agents.engine.blocks import BLOCK_SCHEMA, clean_blocks
from neotec_ai.agents.engine.registry import tool


@tool("render_ui", "Show tables and charts",
      "Show the user structured blocks instead of long prose: kpis, table, chart (bar/line/pie/donut/percentage), "
      "doclist (clickable ERPNext documents), callout, form (to collect inputs), actions (quick-reply buttons), text. "
      "Use real numbers from tools only. After calling it, add at most two sentences of interpretation.",
      {"title": {"type": "string"},
       "blocks": {"type": "array", "items": BLOCK_SCHEMA},
       "__required__": ["blocks"]}, category="Interface")
def render_ui(blocks, title=None):
    from neotec_ai.agents.tools._common import jarg

    clean, problems = clean_blocks(jarg(blocks, []))
    if not clean:
        return {"shown": False, "problems": problems or ["no valid blocks"]}
    return {"__blocks__": {"title": (title or "")[:120], "blocks": clean}, "shown": True, "problems": problems}
