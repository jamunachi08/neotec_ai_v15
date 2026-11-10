# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Neotec AI platform: the stable API other apps use.

    from neotec_ai.platform import complete_text, complete_json, is_available, PlatformError

    if is_available():
        text = complete_text(system, user, app="my_app", feature="summary", reference=("Lead", name))

Every call goes through one governed gateway (routes, fallback, quotas, residency, masking, compression,
usage ledger). See docs/PLATFORM.md. Names in this module are kept stable across releases.
"""

from __future__ import annotations


def is_available(app: str | None = None) -> bool:
    """True when the gateway is switched on and at least one enabled provider exists."""
    try:
        import frappe

        from neotec_ai.platform import gateway

        return gateway.enabled() and bool(frappe.db.exists("Coworker Provider", {"enabled": 1}))
    except Exception:  # noqa: BLE001
        return False


def complete(*args, **kwargs):
    from neotec_ai.platform import gateway

    return gateway.complete(*args, **kwargs)


def complete_text(system: str, user: str, **kwargs) -> str:
    from neotec_ai.platform import gateway

    return gateway.complete_text(system, user, **kwargs)


def complete_json(system: str, user: str, **kwargs):
    from neotec_ai.platform import gateway

    return gateway.complete_json(system, user, **kwargs)


def extract_json(text: str):
    from neotec_ai.platform import gateway

    return gateway.extract_json(text)


def __getattr__(name):  # PlatformError, PlatformBlocked, Completion without importing Frappe at import time
    if name in ("PlatformError", "PlatformBlocked", "Completion"):
        from neotec_ai.platform import gateway

        return getattr(gateway, name)
    raise AttributeError(name)
