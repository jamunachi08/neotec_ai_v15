# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Reversible masking of personal data for calls that leave the site.

Before a prompt goes to an External provider, IBANs, card numbers, Saudi mobiles, national ID / iqama numbers
and e-mail addresses are swapped for placeholders such as ``⟦EMAIL_1⟧``. The vault (placeholder -> original)
stays on the server; the model's answer is unmasked before it is returned, so a translation or a drafted e-mail
still carries the real address. The same value always gets the same placeholder within one call.

Pure Python: no Frappe import.
"""

from __future__ import annotations

import re

from neotec_ai.agents.engine.redact import _CARD, _EMAIL, _IBAN_SA, _MOBILE_SA, _NATIONAL_ID, _luhn_ok

OPEN, CLOSE = "\u27e6", "\u27e7"
_PLACEHOLDER = re.compile(OPEN + r"[A-Z]+_\d+" + CLOSE)


def _card_ok(text: str) -> bool:
    digits = re.sub(r"\D", "", text)
    return 13 <= len(digits) <= 19 and _luhn_ok(digits)


# Order matters: the longest, most specific patterns first so an IBAN is not half-eaten as an ID number.
_KINDS = (
    ("IBAN", _IBAN_SA, None),
    ("CARD", _CARD, _card_ok),
    ("EMAIL", _EMAIL, None),
    ("MOBILE", _MOBILE_SA, None),
    ("ID", _NATIONAL_ID, None),
)


def mask(text: str, vault: dict | None = None) -> tuple[str, dict]:
    """Returns (masked_text, vault). Pass the same vault for every part of one call."""
    vault = {} if vault is None else vault
    if not text or not isinstance(text, str):
        return text, vault
    reverse = {v: k for k, v in vault.items()}
    counters: dict[str, int] = {}
    for key in vault:
        kind = key[1:].split("_")[0]
        counters[kind] = max(counters.get(kind, 0), int(key[1:-1].split("_")[1]))

    def placeholder(kind: str, value: str) -> str:
        if value in reverse:
            return reverse[value]
        counters[kind] = counters.get(kind, 0) + 1
        key = f"{OPEN}{kind}_{counters[kind]}{CLOSE}"
        vault[key] = value
        reverse[value] = key
        return key

    # Placeholders already in the text (from an earlier mask) are protected from being re-masked.
    parts = _PLACEHOLDER.split(text)
    keeps = _PLACEHOLDER.findall(text)
    out = []
    for i, part in enumerate(parts):
        for kind, pattern, check in _KINDS:
            def repl(m, kind=kind, check=check):
                value = m.group(0)
                if check and not check(value):
                    return value
                return placeholder(kind, value)

            part = pattern.sub(repl, part)
        out.append(part)
        if i < len(keeps):
            out.append(keeps[i])
    return "".join(out), vault


def unmask(text: str, vault: dict) -> str:
    if not text or not vault:
        return text
    for key, value in vault.items():
        text = text.replace(key, value)
    return text


def mask_messages(messages: list[dict], vault: dict) -> list[dict]:
    """Masks the text of every message (internal format). Tool-call arguments are left alone: they are the
    model's own earlier output and already use placeholders."""
    out = []
    for m in messages:
        m = dict(m)
        if isinstance(m.get("content"), str):
            m["content"], _ = mask(m["content"], vault)
        out.append(m)
    return out


def unmask_obj(obj, vault: dict):
    """Unmasks every string inside a JSON-like structure (tool-call arguments, parsed JSON answers)."""
    if not vault:
        return obj
    if isinstance(obj, str):
        return unmask(obj, vault)
    if isinstance(obj, dict):
        return {k: unmask_obj(v, vault) for k, v in obj.items()}
    if isinstance(obj, list):
        return [unmask_obj(v, vault) for v in obj]
    return obj
