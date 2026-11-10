# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Per-provider request/token windows and cool-downs, kept in the site cache (Redis).

Windows: requests per minute and per day, tokens per minute and per day (limits on Coworker Provider; 0 means
unlimited). Day windows follow the UTC day, as providers reset at midnight. A provider that returns a rate
limit or a server error rests on an escalating ladder (30 s, 2 min, 10 min, 30 min, 1 h) and the next provider
in the route is used; a success clears it.
"""

from __future__ import annotations

import time

import frappe

from neotec_ai.platform import router

PREFIX = "neotec_ai:q"


def _cache():
    c = frappe.cache
    return c() if callable(c) and not hasattr(c, "get_value") else c


def _get(key) -> int:
    try:
        return int(_cache().get_value(key) or 0)
    except Exception:  # noqa: BLE001 - the cache is an optimisation, never a blocker
        return 0


def _add(key, amount, ttl):
    try:
        c = _cache()
        c.set_value(key, int(c.get_value(key) or 0) + int(amount), expires_in_sec=ttl)
    except Exception:  # noqa: BLE001
        pass


def _keys(name):
    now = int(time.time())
    minute, day = now // 60, now // 86400
    return {
        "rpm": f"{PREFIX}:{name}:r:m:{minute}", "rpd": f"{PREFIX}:{name}:r:d:{day}",
        "tpm": f"{PREFIX}:{name}:t:m:{minute}", "tpd": f"{PREFIX}:{name}:t:d:{day}",
    }


def headroom(p: dict, est_tokens: int) -> tuple[bool, str]:
    k = _keys(p["name"])
    if not router.within(p.get("rpm_limit"), _get(k["rpm"]), 1):
        return False, "requests-per-minute limit reached"
    if not router.within(p.get("rpd_limit"), _get(k["rpd"]), 1):
        return False, "requests-per-day limit reached"
    if not router.within(p.get("tpm_limit"), _get(k["tpm"]), est_tokens):
        return False, "tokens-per-minute limit reached"
    if not router.within(p.get("tpd_limit"), _get(k["tpd"]), est_tokens):
        return False, "tokens-per-day limit reached"
    return True, ""


def record(name: str, tokens: int):
    k = _keys(name)
    _add(k["rpm"], 1, 120)
    _add(k["tpm"], tokens, 120)
    _add(k["rpd"], 1, 90000)
    _add(k["tpd"], tokens, 90000)


def cooled(names) -> dict:
    out = {}
    now = time.time()
    for n in names:
        until = _get(f"{PREFIX}:{n}:cool")
        if until and until > now:
            out[n] = until
    return out


def strike(name: str) -> int:
    strikes = _get(f"{PREFIX}:{name}:strikes") + 1
    secs = router.cooldown_seconds(strikes)
    try:
        c = _cache()
        c.set_value(f"{PREFIX}:{name}:strikes", strikes, expires_in_sec=7200)
        c.set_value(f"{PREFIX}:{name}:cool", int(time.time()) + secs, expires_in_sec=secs + 5)
    except Exception:  # noqa: BLE001
        pass
    return secs


def clear(name: str):
    try:
        c = _cache()
        c.delete_value(f"{PREFIX}:{name}:strikes")
        c.delete_value(f"{PREFIX}:{name}:cool")
    except Exception:  # noqa: BLE001
        pass


def snapshot(name: str) -> dict:
    k = _keys(name)
    return {"requests_this_minute": _get(k["rpm"]), "requests_today": _get(k["rpd"]),
            "tokens_this_minute": _get(k["tpm"]), "tokens_today": _get(k["tpd"]),
            "resting_until": _get(f"{PREFIX}:{name}:cool") or None}
