# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Masking for secrets (always, in the audit trail) and personal data (before an External provider).

Pure Python: no Frappe import, so it is unit-testable.
"""

from __future__ import annotations

import json
import re

_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)\btoken\s+[a-z0-9]{10,}:[a-z0-9]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"(?i)(password|passwd|secret|api_key|apikey)(\"?\s*[:=]\s*\"?)([^\s\",}]{4,})"),
]

_IBAN_SA = re.compile(r"\bSA\d{2}(?:\s?[A-Z0-9]){20}\b", re.I)
_NATIONAL_ID = re.compile(r"(?<![\d.])[12]\d{9}(?![\d.])")
_MOBILE_SA = re.compile(r"(?<!\d)(?:\+?966|00966|0)5\d{8}(?!\d)")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_CARD = re.compile(r"(?<!\d)(?:\d[ \-]?){12,18}\d(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def mask_secrets(text: str) -> str:
    if not text:
        return text
    for pat in _SECRET_PATTERNS:
        if pat.groups >= 3:
            text = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}[secret]", text)
        else:
            text = pat.sub("[secret]", text)
    return text


def mask_personal(text: str) -> str:
    if not text:
        return text

    def card(m):
        digits = re.sub(r"\D", "", m.group(0))
        return "[card]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else m.group(0)

    text = _IBAN_SA.sub("[iban]", text)
    text = _CARD.sub(card, text)
    text = _MOBILE_SA.sub("[mobile]", text)
    text = _NATIONAL_ID.sub("[id-number]", text)
    text = _EMAIL.sub("[email]", text)
    return text


def mask_all(text: str) -> str:
    return mask_personal(mask_secrets(text))


def mask_obj(obj, personal: bool = False):
    """Masks every string inside a JSON-like structure."""
    fn = mask_all if personal else mask_secrets
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and re.search(r"(?i)password|secret|api_key|token", k) and isinstance(v, str):
                out[k] = "[secret]"
            else:
                out[k] = mask_obj(v, personal)
        return out
    if isinstance(obj, (list, tuple)):
        return [mask_obj(v, personal) for v in obj]
    return obj


def to_json(obj, limit: int | None = None) -> str:
    text = json.dumps(obj, ensure_ascii=False, default=str)
    if limit and len(text) > limit:
        cut = len(text) - limit
        text = text[:limit] + f" …[truncated {cut} more characters; narrow the request]"
    return text
