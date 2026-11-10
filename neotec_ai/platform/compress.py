# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Prompt compression for long requests.

ERP tool results are mostly JSON lists of records with the same keys repeated on every row, and long agent
sessions send the same record or report more than once. Shrinking that before the call keeps more of the
conversation inside the model's context window and lowers token cost. The model's answer is never rewritten.

Modes
  Off       nothing changes
  Lossless  whitespace hygiene, JSON lists of records encoded as {"columns": [...], "rows": [[...]]},
            repeated large blocks replaced by a pointer to the first copy
  Standard  Lossless plus: an older result of the same tool with the same arguments is replaced by a note
            that a newer result follows

Every engine is fail-open and checked by a fidelity gate: its output is discarded if it is not smaller, if it
throws, or if any number, date, document name or error line in the input is missing from the output.

Pure Python: no Frappe import.
"""

from __future__ import annotations

import json
import re

MODES = ("Off", "Lossless", "Standard")
MIN_TABLE_ROWS = 3
MIN_DEDUPE_CHARS = 400
TABLE_MARK = "__table__"

_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)*")
_ERROR_LINE = re.compile(r"(?im)^.*\b(error|refused|denied|failed|not permitted|exception)\b.*$")
_DOCNAME = re.compile(r"\b[A-Z][A-Z0-9]{1,8}-[A-Z0-9-]{2,}\b")


# ---------------------------------------------------------------- fidelity gate

def _facts(text: str) -> tuple[set, set, set]:
    return set(_NUMBER.findall(text)), set(_DOCNAME.findall(text)), {
        line.strip() for line in _ERROR_LINE.findall(text) if isinstance(line, str)}


def _error_lines(text: str) -> set:
    return {m.group(0).strip() for m in _ERROR_LINE.finditer(text)}


def faithful(before: str, after: str) -> bool:
    """True when every number, document name and error line of ``before`` is still present in ``after``."""
    nums_b, docs_b, _ = _facts(before)
    nums_a, docs_a, _ = _facts(after)
    if not nums_b <= nums_a or not docs_b <= docs_a:
        return False
    errors_after = after
    return all(line in errors_after or _loose(line) in _loose(errors_after) for line in _error_lines(before))


def _loose(text: str) -> str:
    return re.sub(r"[\s\"{}\[\],:]+", " ", text).strip()


# ---------------------------------------------------------------- engines on one text

def whitespace(text: str) -> str:
    lines = [ln.rstrip() for ln in text.splitlines()]
    out, blank = [], 0
    for ln in lines:
        if not ln.strip():
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        out.append(ln)
    return "\n".join(out).strip("\n")


def _encode(value):
    """Recursively turns lists of similar records into column/row tables."""
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, list):
        if (len(value) >= MIN_TABLE_ROWS and all(isinstance(r, dict) for r in value)):
            columns: list[str] = []
            for r in value:
                for k in r:
                    if k not in columns:
                        columns.append(k)
            if columns and len(columns) <= 40:
                # Only worth it when most rows share most keys.
                filled = sum(len(r) for r in value)
                if filled >= 0.6 * len(columns) * len(value):
                    return {TABLE_MARK: {"columns": columns,
                                         "rows": [[_encode(r.get(c)) for c in columns] for r in value]}}
        return [_encode(v) for v in value]
    return value


def decode(value):
    """Inverse of the table encoding (used by tests and by callers that need the records back)."""
    if isinstance(value, dict):
        if set(value) == {TABLE_MARK}:
            t = value[TABLE_MARK]
            return [{c: decode(v) for c, v in zip(t["columns"], row) if v is not None} for row in t["rows"]]
        return {k: decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode(v) for v in value]
    return value


def json_tables(text: str) -> str:
    """Encodes record lists when the whole text is JSON. Other text is returned unchanged."""
    s = text.strip()
    if not s or s[0] not in "[{":
        return text
    try:
        data = json.loads(s)
    except ValueError:
        return text
    encoded = _encode(data)
    if encoded == data:
        return text
    note = "(Lists of records are sent as __table__ objects with columns and rows.) "
    return note + json.dumps(encoded, ensure_ascii=False, separators=(",", ":"), default=str)


def _guard(fn, text: str) -> str:
    try:
        out = fn(text)
    except Exception:  # noqa: BLE001 - fail open
        return text
    if not isinstance(out, str) or len(out) >= len(text) or not faithful(text, out):
        return text
    return out


def compress_text(text: str, mode: str = "Lossless") -> str:
    if mode not in ("Lossless", "Standard") or not isinstance(text, str) or len(text) < 200:
        return text
    text = _guard(whitespace, text)
    text = _guard(json_tables, text)
    return text


# ---------------------------------------------------------------- engines across messages

def _args_key(call: dict) -> str:
    return call.get("name", "") + json.dumps(call.get("arguments") or {}, sort_keys=True, default=str)


def supersede(messages: list[dict]) -> list[dict]:
    """Standard mode: an earlier result of the same tool + arguments is replaced by a short note when the same
    call was made again later. The latest result always stays."""
    call_keys: dict[str, str] = {}
    for m in messages:
        if m.get("role") == "assistant":
            for c in m.get("tool_calls") or []:
                call_keys[c.get("id")] = _args_key(c)
    last_for_key: dict[str, int] = {}
    for i, m in enumerate(messages):
        if m.get("role") == "tool" and m.get("tool_call_id") in call_keys:
            last_for_key[call_keys[m["tool_call_id"]]] = i
    out = []
    for i, m in enumerate(messages):
        key = call_keys.get(m.get("tool_call_id")) if m.get("role") == "tool" else None
        if key and last_for_key.get(key) != i and len(m.get("content") or "") > 200:
            m = {**m, "content": f"[Superseded: {m.get('name') or 'this tool'} was called again with the same "
                                 "arguments; see the newer result below.]"}
        out.append(m)
    return out


def dedupe(messages: list[dict]) -> list[dict]:
    """A large message identical to an earlier one is replaced by a pointer to the first copy."""
    seen: dict[str, int] = {}
    out = []
    for i, m in enumerate(messages):
        content = m.get("content")
        if isinstance(content, str) and len(content) >= MIN_DEDUPE_CHARS:
            if content in seen:
                m = {**m, "content": f"[Same content as message {seen[content] + 1} above.]"}
            else:
                seen[content] = i
        out.append(m)
    return out


def compress_messages(messages: list[dict], mode: str = "Lossless") -> tuple[list[dict], int]:
    """Returns (messages, characters saved). The last user message is never altered."""
    if mode not in ("Lossless", "Standard") or not messages:
        return messages, 0
    before = sum(len(m.get("content") or "") for m in messages if isinstance(m.get("content"), str))
    last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
    work = list(messages)
    if mode == "Standard":
        work = supersede(work)
    work = dedupe(work)
    out = []
    for i, m in enumerate(work):
        if i == last_user:
            out.append(messages[i])   # the question being asked is sent exactly as written
            continue
        if isinstance(m.get("content"), str):
            m = {**m, "content": compress_text(m["content"], mode)}
        out.append(m)
    after = sum(len(m.get("content") or "") for m in out if isinstance(m.get("content"), str))
    return out, max(0, before - after)
