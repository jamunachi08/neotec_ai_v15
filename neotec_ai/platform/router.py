# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Choosing which provider answers a call. Pure Python: no Frappe import.

Routes
  A route (Neotec AI Route) is a named, ordered list of providers. A call names its app, feature and purpose;
  the first route that matches wins:  "app:feature"  ->  "app"  ->  purpose  ->  "Default".
  A route matches a key when the key is its name or one of the lines in "Used by".

Chain order
  The first eligible provider sets the residency floor: a later provider is used only if it keeps data at
  least as close (On-Premises < In Kingdom (KSA) < External). Strict residency never uses External providers;
  Guarded residency skips External providers for calls marked sensitive. Providers resting after an error
  (cool-down) are moved to the end, not dropped, so a single provider still gets tried.
"""

from __future__ import annotations

DEFAULT_ROUTE = "Default"
LOCATION_RANK = {"On-Premises": 0, "In Kingdom (KSA)": 1, "External": 2}
COOLDOWN_LADDER = (30, 120, 600, 1800, 3600)   # seconds, per consecutive transient failure


def location_rank(location: str | None) -> int:
    return LOCATION_RANK.get(location or "External", 2)


def keys_for(app: str | None, feature: str | None, purpose: str | None) -> list[str]:
    out = []
    if app and feature:
        out.append(f"{app}:{feature}")
    if app:
        out.append(app)
    if purpose:
        out.append(purpose)
    out.append(DEFAULT_ROUTE)
    seen, keys = set(), []
    for k in out:
        k = k.strip().lower()
        if k and k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


def build_index(routes: list[dict]) -> dict[str, dict]:
    """routes: [{"name", "enabled", "used_by", ...}] -> {lower-case key: route}. Earlier routes win."""
    index: dict[str, dict] = {}
    for r in routes:
        if not r.get("enabled", 1):
            continue
        keys = [r.get("name") or ""]
        for line in (r.get("used_by") or "").replace(",", "\n").splitlines():
            keys.append(line)
        for k in keys:
            k = k.strip().lower()
            if k and k not in index:
                index[k] = r
    return index


def pick_route(index: dict[str, dict], app=None, feature=None, purpose=None) -> dict | None:
    for k in keys_for(app, feature, purpose):
        if k in index:
            return index[k]
    return None


def order_chain(providers: list[dict], *, residency_mode: str | None = "Guarded", sensitive: bool = False,
                cooled: dict | None = None, need_tools: bool = False, need_vision: bool = False
                ) -> tuple[list[dict], list[tuple[str, str]]]:
    """providers: ordered dicts with name, enabled, data_location, tool_test_status, supports_vision.
    Returns (chain, skipped) where skipped is [(name, reason)]."""
    cooled = cooled or {}
    chain, skipped, seen = [], [], set()
    anchor = None
    for p in providers:
        name = p.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        loc = p.get("data_location") or "External"
        if not p.get("enabled", 1):
            skipped.append((name, "disabled"))
            continue
        if residency_mode == "Strict" and loc == "External":
            skipped.append((name, "residency: Strict mode blocks external providers"))
            continue
        if sensitive and residency_mode != "Open" and loc == "External":
            skipped.append((name, "residency: sensitive data stays off external providers"))
            continue
        if need_vision and not p.get("supports_vision"):
            skipped.append((name, "cannot read images"))
            continue
        if anchor is not None:
            if location_rank(loc) > location_rank(anchor):
                skipped.append((name, "fallback would move data further away"))
                continue
            if need_tools and p.get("tool_test_status") == "Failed":
                skipped.append((name, "failed the tool-calling self-test"))
                continue
        else:
            anchor = loc
        chain.append(p)
    resting = [p for p in chain if cooled.get(p["name"])]
    ready = [p for p in chain if not cooled.get(p["name"])]
    return ready + resting, skipped


def cooldown_seconds(strikes: int) -> int:
    if strikes <= 0:
        return 0
    return COOLDOWN_LADDER[min(strikes, len(COOLDOWN_LADDER)) - 1]


def estimate_tokens(chars: int) -> int:
    return int(chars or 0) // 4 + 1


def within(limit, used, extra=0) -> bool:
    """A limit of 0 or empty means unlimited."""
    limit = int(limit or 0)
    return limit <= 0 or int(used or 0) + int(extra or 0) <= limit
