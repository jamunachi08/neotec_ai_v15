# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Neotec Blocks: the declarative answer format a coworker uses to show more than prose.

The model never sends HTML or code. It sends a list of typed blocks; the server validates and
caps them here, and the chat page renders each type with its own trusted component.

Block types
  text      {"type":"text","text":"markdown"}
  kpis      {"type":"kpis","items":[{"label","value","hint"?,"trend"?: "up"|"down"|"flat"}]}
  table     {"type":"table","columns":[...],"rows":[[...]],"caption"?}
  chart     {"type":"chart","chart":"bar"|"line"|"pie"|"donut"|"percentage","labels":[...],
             "datasets":[{"name","values":[...]}],"title"?}
  doclist   {"type":"doclist","items":[{"doctype","name","label"?,"hint"?}]}
  callout   {"type":"callout","tone":"info"|"success"|"warning"|"danger","text"}
  form      {"type":"form","id","title","fields":[{"fieldname","label","fieldtype","options"?,"default"?}],
             "submit_label"?}
  actions   {"type":"actions","items":[{"label","prompt"}]}

Pure Python.
"""

from __future__ import annotations

import re

MAX_BLOCKS = 12
MAX_ROWS = 200
MAX_COLS = 20
MAX_POINTS = 120
MAX_DATASETS = 6
MAX_TEXT = 8000
CHARTS = {"bar", "line", "pie", "donut", "percentage"}
TONES = {"info", "success", "warning", "danger"}
FIELD_TYPES = {"Data", "Int", "Float", "Currency", "Date", "Select", "Check", "Small Text"}
TRENDS = {"up", "down", "flat"}


def _s(v, limit=500) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)[:limit]


def _num(v):
    try:
        if isinstance(v, str):
            v = v.replace(",", "").strip()
        f = float(v)
        return int(f) if f.is_integer() else round(f, 4)
    except (TypeError, ValueError):
        return 0


def clean_blocks(blocks) -> tuple[list[dict], list[str]]:
    """Returns (clean_blocks, problems). Unknown or malformed blocks are dropped and reported."""
    clean, problems = [], []
    if not isinstance(blocks, list):
        return [], ["blocks must be a list"]
    for i, b in enumerate(blocks[:MAX_BLOCKS]):
        if not isinstance(b, dict):
            problems.append(f"block {i}: not an object")
            continue
        t = b.get("type")
        try:
            out = _CLEANERS[t](b) if t in _CLEANERS else None
        except Exception as e:  # noqa: BLE001
            out = None
            problems.append(f"block {i} ({t}): {e}")
            continue
        if out is None:
            problems.append(f"block {i}: unknown or empty type {t!r}")
        else:
            clean.append(out)
    if len(blocks) > MAX_BLOCKS:
        problems.append(f"only the first {MAX_BLOCKS} blocks are shown")
    return clean, problems


def _text(b):
    text = _s(b.get("text"), MAX_TEXT)
    return {"type": "text", "text": text} if text.strip() else None


def _kpis(b):
    items = []
    for it in (b.get("items") or [])[:8]:
        if not isinstance(it, dict) or not _s(it.get("label")):
            continue
        row = {"label": _s(it.get("label"), 80), "value": _s(it.get("value"), 60)}
        if it.get("hint"):
            row["hint"] = _s(it.get("hint"), 120)
        if it.get("trend") in TRENDS:
            row["trend"] = it["trend"]
        items.append(row)
    return {"type": "kpis", "items": items} if items else None


def _table(b):
    cols = [_s(c, 80) for c in (b.get("columns") or [])[:MAX_COLS]]
    if not cols:
        return None
    rows = []
    for r in (b.get("rows") or [])[:MAX_ROWS]:
        if isinstance(r, dict):
            r = [r.get(c) for c in cols]
        if not isinstance(r, (list, tuple)):
            continue
        r = [_s(v, 300) for v in list(r)[: len(cols)]]
        r += [""] * (len(cols) - len(r))
        rows.append(r)
    out = {"type": "table", "columns": cols, "rows": rows}
    if b.get("caption"):
        out["caption"] = _s(b["caption"], 200)
    return out


def _chart(b):
    kind = b.get("chart") if b.get("chart") in CHARTS else "bar"
    labels = [_s(x, 60) for x in (b.get("labels") or [])[:MAX_POINTS]]
    if not labels:
        return None
    datasets = []
    for ds in (b.get("datasets") or [])[:MAX_DATASETS]:
        if not isinstance(ds, dict):
            continue
        vals = [_num(v) for v in (ds.get("values") or [])[: len(labels)]]
        vals += [0] * (len(labels) - len(vals))
        datasets.append({"name": _s(ds.get("name") or "Value", 60), "values": vals})
    if not datasets:
        return None
    if kind in ("pie", "donut", "percentage"):
        datasets = datasets[:1]
    out = {"type": "chart", "chart": kind, "labels": labels, "datasets": datasets}
    if b.get("title"):
        out["title"] = _s(b["title"], 120)
    return out


_DOCNAME = re.compile(r"^[^<>\"'`]{1,140}$")


def _doclist(b):
    items = []
    for it in (b.get("items") or [])[:50]:
        if not isinstance(it, dict):
            continue
        dt, dn = _s(it.get("doctype"), 140), _s(it.get("name"), 140)
        if not (dt and dn and _DOCNAME.match(dt) and _DOCNAME.match(dn)):
            continue
        row = {"doctype": dt, "name": dn}
        if it.get("label"):
            row["label"] = _s(it["label"], 140)
        if it.get("hint"):
            row["hint"] = _s(it["hint"], 140)
        items.append(row)
    return {"type": "doclist", "items": items} if items else None


def _callout(b):
    text = _s(b.get("text"), 1000)
    if not text:
        return None
    return {"type": "callout", "tone": b.get("tone") if b.get("tone") in TONES else "info", "text": text}


_FIELDNAME = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


def _form(b):
    fields = []
    for f in (b.get("fields") or [])[:12]:
        if not isinstance(f, dict):
            continue
        fn = _s(f.get("fieldname"), 41).lower()
        if not _FIELDNAME.match(fn):
            continue
        row = {
            "fieldname": fn,
            "label": _s(f.get("label") or fn, 80),
            "fieldtype": f.get("fieldtype") if f.get("fieldtype") in FIELD_TYPES else "Data",
        }
        if f.get("options"):
            opts = f["options"]
            if isinstance(opts, list):
                opts = "\n".join(_s(o, 80) for o in opts[:30])
            row["options"] = _s(opts, 2000)
        if f.get("default") not in (None, ""):
            row["default"] = _s(f["default"], 200)
        fields.append(row)
    if not fields:
        return None
    return {
        "type": "form",
        "id": _s(b.get("id") or "form", 40),
        "title": _s(b.get("title"), 120),
        "fields": fields,
        "submit_label": _s(b.get("submit_label") or "Send", 40),
    }


def _actions(b):
    items = []
    for it in (b.get("items") or [])[:6]:
        if isinstance(it, dict) and _s(it.get("label")) and _s(it.get("prompt")):
            items.append({"label": _s(it["label"], 60), "prompt": _s(it["prompt"], 500)})
    return {"type": "actions", "items": items} if items else None


_CLEANERS = {
    "text": _text, "kpis": _kpis, "table": _table, "chart": _chart,
    "doclist": _doclist, "callout": _callout, "form": _form, "actions": _actions,
}

# A permissive schema every provider accepts (no additionalProperties, every object has properties).
_STR = {"type": "string"}
_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "label": _STR, "value": _STR, "hint": _STR, "trend": _STR,
        "doctype": _STR, "name": _STR, "prompt": _STR,
    },
}
BLOCK_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": sorted(_CLEANERS)},
        "text": _STR, "title": _STR, "caption": _STR, "tone": _STR, "chart": _STR,
        "id": _STR, "submit_label": _STR,
        "items": {"type": "array", "items": _ITEM_SCHEMA},
        "columns": {"type": "array", "items": _STR},
        "rows": {"type": "array", "items": {"type": "array", "items": _STR}},
        "labels": {"type": "array", "items": _STR},
        "datasets": {"type": "array", "items": {"type": "object", "properties": {
            "name": _STR, "values": {"type": "array", "items": {"type": "number"}}}}},
        "fields": {"type": "array", "items": {"type": "object", "properties": {
            "fieldname": _STR, "label": _STR, "fieldtype": _STR, "options": _STR, "default": _STR}}},
    },
    "required": ["type"],
}
