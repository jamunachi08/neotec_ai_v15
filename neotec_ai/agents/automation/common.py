# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Pure helpers for playbooks, delivery and health. No Frappe import, so they are unit-tested directly."""

from __future__ import annotations

import re

NOTHING_TO_REPORT = "NOTHING_TO_REPORT"
SEVERITIES = ("info", "success", "warn", "critical")
SEVERITY_RANK = {"info": 0, "success": 1, "warn": 2, "critical": 3}
SEVERITY_ICON = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "critical": "🚨"}

# Lower is closer to home. A fallback provider may never be further away than the main one.
LOCATION_RANK = {"On-Premises": 0, "In Kingdom (KSA)": 1, "External": 2}

_SEV_LINE = re.compile(r"^[\s>*_`#-]*SEVERITY\s*[:=]\s*\**\s*(info|success|warn|warning|critical)\b[\s*_`.]*$",
                       re.I)
_NOTHING = re.compile(r"^[\s*_`\"'.]*NOTHING[_ ]TO[_ ]REPORT[\s*_`\"'.!]*$", re.I)
_TOKEN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def severity_rank(sev: str | None) -> int:
    return SEVERITY_RANK.get((sev or "info").lower(), 0)


def passes_threshold(severity: str | None, minimum: str | None) -> bool:
    return severity_rank(severity) >= severity_rank(minimum)


def location_rank(location: str | None) -> int:
    return LOCATION_RANK.get(location or "External", 2)


def fallback_allowed(primary_location: str | None, fallback_location: str | None, residency_mode: str | None) -> bool:
    """A fallback keeps data at least as close as the main provider, and Strict mode never goes external."""
    if residency_mode == "Strict" and fallback_location == "External":
        return False
    return location_rank(fallback_location) <= location_rank(primary_location)


def parse_output(text: str | None, default_severity: str = "info") -> tuple[str, str, bool]:
    """Reads the output contract.

    Returns (clean_text, severity, nothing_to_report). The first line may be ``SEVERITY: warn``; the whole answer
    may be ``NOTHING_TO_REPORT``. Anything else is treated as a normal report with the default severity.
    """
    raw = (text or "").strip()
    default = default_severity if default_severity in SEVERITY_RANK else "info"
    if not raw:
        return "", default, False
    if _NOTHING.match(raw) or (raw.upper().startswith(NOTHING_TO_REPORT) and len(raw) <= 80):
        return "", default, True
    lines = raw.splitlines()
    severity = default
    for i, line in enumerate(lines[:4]):
        m = _SEV_LINE.match(line)
        if m:
            found = m.group(1).lower()
            severity = "warn" if found == "warning" else found
            del lines[i]
            break
    clean = "\n".join(lines).strip()
    if _NOTHING.match(clean):
        return "", severity, True
    return clean, severity, False


def substitute(template: str | None, values: dict) -> str:
    """Replaces {key} for keys present in ``values``; unknown braces are left alone (JSON in instructions is safe)."""

    def rep(m):
        key = m.group(1)
        if key in values and values[key] is not None:
            return str(values[key])
        return m.group(0)

    return _TOKEN.sub(rep, template or "")


def chunk_text(text: str, size: int = 3900) -> list[str]:
    """Splits on line boundaries where possible. Used for chat channels with message limits."""
    text = text or ""
    if len(text) <= size:
        return [text]
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:size])
            line = line[size:]
        if len(current) + len(line) > size:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    total = len(chunks)
    return [f"[{i}/{total}]\n{c}" for i, c in enumerate(chunks, 1)]


def to_chat_markdown(md: str) -> str:
    """Slack and Google Chat use *bold* and no headings; keep everything else readable."""
    out = []
    for line in (md or "").splitlines():
        h = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if h:
            line = f"*{h.group(1).strip()}*"
        line = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)
        line = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"<\2|\1>", line)
        out.append(line)
    return "\n".join(out)


def teams_payload(subject: str, body: str, severity: str = "info") -> dict:
    """Adaptive Card message accepted by Teams workflow webhooks."""
    color = {"warn": "Warning", "critical": "Attention", "success": "Good"}.get(severity, "Default")
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": subject, "weight": "Bolder", "size": "Medium", "wrap": True,
                     "color": color},
                    {"type": "TextBlock", "text": body[:20000], "wrap": True},
                ],
            },
        }],
    }


def render_parameter(template: str | None, doc: dict) -> str:
    """{name}, {doctype} or any scalar field of the document."""
    values = {k: v for k, v in (doc or {}).items() if isinstance(v, (str, int, float)) and not isinstance(v, bool)}
    return substitute(template or "{name}", values).strip()


def normalise_tools(value: str | None) -> list[str]:
    parts = re.split(r"[\s,;]+", value or "")
    seen, out = set(), []
    for p in parts:
        p = p.strip().lower()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def normalise_key(key) -> str:
    key = re.sub(r"\s+", " ", str(key or "")).strip()
    return key[:140]


def cost_usd(tokens_in: int, tokens_out: int, price_in: float | None, price_out: float | None) -> float:
    return round((tokens_in or 0) / 1e6 * (price_in or 0) + (tokens_out or 0) / 1e6 * (price_out or 0), 6)


def consecutive_failures(statuses: list[str]) -> int:
    """``statuses`` newest first. Counts failures until the first non-failure."""
    n = 0
    for s in statuses:
        if s in ("Failed", "Budget Exceeded"):
            n += 1
        else:
            break
    return n


def parse_score(text: str | None) -> tuple[int | None, str]:
    """Reads {"score": 1-5, "note": "..."} from a model reply, tolerating fences and prose around it."""
    import json

    if not text:
        return None, ""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None, ""
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None, ""
    try:
        score = int(round(float(data.get("score"))))
    except (TypeError, ValueError):
        return None, ""
    if not 1 <= score <= 5:
        return None, ""
    return score, str(data.get("note") or "")[:500]
