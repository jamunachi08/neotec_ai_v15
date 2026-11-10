# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""The shared AI gateway. Every model call from every app can go through ``complete``:

    resolve route -> order providers (residency, cool-downs, vision/tool needs) -> per provider:
        quota headroom -> mask personal data (External) -> compress (long requests) -> call
        -> on a transient error: rest the provider and try the next one
    -> unmask the answer -> one Neotec AI Call Log row -> return a Completion

Budgets: a route may carry a monthly token budget; when it is used up the call is refused (Blocked).
Governance (residency mode, masking, sensitive DocTypes) is read from Coworker Settings, so one policy covers
the assistant, coworkers, automation and every connected app.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_first_day, now_datetime, nowdate

from neotec_ai.agents.engine import llm
from neotec_ai.platform import compress, quota, router, shield

LOG_DT = "Neotec AI Call Log"
PROVIDER_FIELDS = ["name", "enabled", "data_location", "tool_test_status", "supports_vision", "rpm_limit",
                   "rpd_limit", "tpm_limit", "tpd_limit", "is_default"]


class PlatformError(Exception):
    """The call could not be answered. The message is safe to show to the user."""


class PlatformBlocked(PlatformError):
    """Governance stopped the call before anything was sent (disabled, budget, residency, no provider)."""


@dataclass
class Completion:
    text: str = ""
    tool_calls: list = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    provider: str = ""
    model: str = ""
    data_location: str = ""
    fell_back: bool = False
    attempts: list = field(default_factory=list)
    saved_chars: int = 0
    stop_reason: str = ""
    route: str = ""

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out


# ---------------------------------------------------------------- settings

def platform_settings():
    return frappe.get_cached_doc("Neotec Settings")


def governance():
    return frappe.get_cached_doc("Coworker Settings")


def sensitive_doctypes() -> set:
    try:
        return {r.document_type for r in (governance().sensitive_doctypes or [])}
    except Exception:  # noqa: BLE001
        return set()


def enabled() -> bool:
    try:
        s = platform_settings()
    except Exception:  # noqa: BLE001 - before first migrate
        return False
    return bool(cint(s.get("platform_enabled") if s.meta.has_field("platform_enabled") else 1))


def _routes() -> list[dict]:
    if not frappe.db.table_exists("Neotec AI Route"):
        return []
    return frappe.get_all("Neotec AI Route", fields=["name", "enabled", "used_by", "monthly_token_budget"],
                          order_by="creation asc")


def route_for(app=None, feature=None, purpose=None) -> dict | None:
    return router.pick_route(router.build_index(_routes()), app, feature, purpose)


def route_providers(route_name: str) -> list[str]:
    return frappe.get_all("Neotec AI Route Provider", filters={"parent": route_name, "parenttype": "Neotec AI Route"},
                          pluck="provider", order_by="idx asc")


def default_providers() -> list[str]:
    names = []
    try:
        dp = governance().get("default_provider")
        if dp:
            names.append(dp)
        fb = governance().get("fallback_provider")
        if fb:
            names.append(fb)
    except Exception:  # noqa: BLE001
        pass
    names += frappe.get_all("Coworker Provider", filters={"enabled": 1}, pluck="name",
                            order_by="is_default desc, creation asc")
    return names


def _provider_rows(names: list[str]) -> list[dict]:
    if not names:
        return []
    meta = frappe.get_meta("Coworker Provider")
    fields = [f for f in PROVIDER_FIELDS if f == "name" or meta.has_field(f)]
    rows = {r.name: r for r in frappe.get_all("Coworker Provider", filters={"name": ["in", list(set(names))]},
                                              fields=fields)}
    return [dict(rows[n]) for n in names if n in rows]


def _month_tokens(route_name: str) -> int:
    key = f"neotec_ai:route_month:{route_name}:{nowdate()[:7]}"
    c = quota._cache()
    try:
        cached = c.get_value(key)
        if cached is not None:
            return int(cached)
    except Exception:  # noqa: BLE001
        pass
    val = frappe.db.sql(f"""select ifnull(sum(tokens_in + tokens_out), 0) from `tab{LOG_DT}`
        where route = %s and creation >= %s and status = 'Success'""", (route_name, get_first_day(nowdate())))
    total = cint(val[0][0]) if val else 0
    try:
        c.set_value(key, total, expires_in_sec=60)
    except Exception:  # noqa: BLE001
        pass
    return total


# ---------------------------------------------------------------- the call

def complete(system: str = "", user: str | None = None, messages: list[dict] | None = None, *,
             app: str = "neotec_ai", feature: str = "adhoc", purpose: str | None = None, reference=None,
             provider: str | None = None, fallbacks: list[str] | None = None, tools: list[dict] | None = None,
             json_mode: bool = False, schema: dict | None = None, images: list[dict] | None = None,
             max_tokens: int | None = None, temperature: float | None = None, timeout: int | None = None,
             sensitive: bool | None = None, mask: bool | None = None, compress_mode: str | None = None,
             log: bool = True) -> Completion:
    """One governed model call.

    messages use the internal format (see agents/engine/llm.py); or pass ``user`` for a single question.
    images: [{"data": base64, "media_type": "image/png"}] attached to the last user message.
    provider: try this provider first (then ``fallbacks``, then the route). reference: (doctype, name).
    """
    if not enabled():
        raise PlatformBlocked(_("Neotec AI is switched off in Neotec Settings."))
    msgs = [dict(m) for m in (messages or [])]
    if user is not None:
        msgs.append({"role": "user", "content": user})
    if not msgs:
        raise PlatformError(_("Nothing to send to the AI."))
    if images:
        for m in reversed(msgs):
            if m.get("role") == "user":
                m["images"] = list(images)
                break

    gov = governance()
    residency = gov.get("residency_mode") or "Guarded"
    if sensitive is None:
        sensitive = bool(reference and reference[0] in sensitive_doctypes())

    route = None if provider and not purpose else route_for(app, feature, purpose)
    names = ([provider] if provider else []) + list(fallbacks or [])
    if route:
        names += route_providers(route["name"])
        budget = cint(route.get("monthly_token_budget"))
        if budget and _month_tokens(route["name"]) >= budget:
            _log(app, feature, route, None, "Blocked", error=f"Monthly token budget of route {route['name']} used up",
                 reference=reference, do_log=log)
            raise PlatformBlocked(_("The monthly AI budget for {0} is used up.").format(route["name"]))
    if not names or (route and not route_providers(route["name"]) and not provider):
        names += default_providers()

    rows = _provider_rows(names)
    chain, skipped = router.order_chain(rows, residency_mode=residency, sensitive=sensitive,
                                        cooled=quota.cooled([r["name"] for r in rows]), need_tools=bool(tools),
                                        need_vision=bool(images))
    if not chain:
        why = "; ".join(f"{n}: {r}" for n, r in skipped) or _("no AI provider is set up")
        _log(app, feature, route, None, "Blocked", error=why, reference=reference, do_log=log)
        raise PlatformBlocked(_("No AI provider can take this request ({0}). An administrator can add one in "
                                "Coworker Setup or Neotec AI Route.").format(why))

    mode = compress_mode or platform_settings().get("compression_mode") or "Lossless"
    trigger = cint(platform_settings().get("compression_trigger_chars")) or 24000
    total_chars = len(system or "") + sum(len(m.get("content") or "") for m in msgs if isinstance(m.get("content"), str))
    est = router.estimate_tokens(total_chars)

    attempts, last_error, started = [], None, time.time()
    for i, p in enumerate(chain):
        ok, why = quota.headroom(p, est)
        if not ok:
            attempts.append(f"{p['name']}: {why}")
            continue
        doc = frappe.get_cached_doc("Coworker Provider", p["name"])
        cfg = llm.config_from_doc(doc)
        if max_tokens:
            cfg.max_output_tokens = int(max_tokens)
        if timeout:
            cfg.timeout = int(timeout)
        external = (p.get("data_location") or "External") == "External"
        use_mask = mask if mask is not None else (external and cint(gov.get("redact_external")))
        vault: dict = {}
        sys_text, call_msgs = system or "", msgs
        if use_mask:
            sys_text, vault = shield.mask(sys_text, vault)
            call_msgs = shield.mask_messages(msgs, vault)
        saved = 0
        if mode != "Off" and total_chars >= trigger:
            call_msgs, saved = compress.compress_messages(call_msgs, mode)
        t0 = time.time()
        try:
            res = llm.chat(cfg, sys_text, call_msgs, tools or [], temperature=temperature, json_mode=json_mode,
                           schema=schema, retries=1 if len(chain) - i > 1 else 2)
        except llm.ProviderError as e:
            last_error = e
            attempts.append(f"{p['name']}: {str(e)[:200]}")
            if e.transient:
                quota.strike(p["name"])
            continue
        except Exception as e:  # noqa: BLE001 - network stack errors behave like an outage
            last_error = e
            attempts.append(f"{p['name']}: {e.__class__.__name__}")
            quota.strike(p["name"])
            continue
        quota.clear(p["name"])
        quota.record(p["name"], res.tokens_in + res.tokens_out)
        text = shield.unmask(res.text or "", vault)
        calls = [{**c, "arguments": shield.unmask_obj(c.get("arguments") or {}, vault)} for c in res.tool_calls]
        out = Completion(text=text, tool_calls=calls, tokens_in=res.tokens_in, tokens_out=res.tokens_out,
                         provider=p["name"], model=cfg.model, data_location=p.get("data_location") or "",
                         fell_back=i > 0 or bool(attempts), attempts=attempts, saved_chars=saved,
                         stop_reason=res.stop_reason, route=route["name"] if route else "")
        _log(app, feature, route, out, "Success", latency=int((time.time() - t0) * 1000), reference=reference,
             masked=bool(vault), do_log=log)
        return out

    _log(app, feature, route, Completion(provider=chain[0]["name"], attempts=attempts), "Failed",
         error=str(last_error or "")[:500], latency=int((time.time() - started) * 1000), reference=reference,
         do_log=log)
    if last_error is not None and isinstance(last_error, llm.ProviderError) and len(attempts) == 1:
        raise PlatformError(_("The AI provider returned an error: {0}").format(str(last_error)[:400]))
    raise PlatformError(_("No AI provider could answer: {0}").format(" | ".join(attempts)[:600]))


def complete_text(system: str, user: str, **kwargs) -> str:
    return complete(system, user, **kwargs).text


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


def extract_json(text: str):
    """Parses the first JSON object or array in a model answer (code fences and chatter tolerated)."""
    s = _FENCE.sub("", (text or "").strip())
    s = re.sub(r"(?s)<think>.*?</think>", "", s).strip()
    try:
        return json.loads(s)
    except ValueError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        a, b = s.find(open_ch), s.rfind(close_ch)
        if a >= 0 and b > a:
            try:
                return json.loads(s[a:b + 1])
            except ValueError:
                continue
    raise ValueError("The AI answer is not valid JSON.")


def complete_json(system: str, user: str, **kwargs):
    kwargs.setdefault("json_mode", True)
    res = complete(system, user, **kwargs)
    try:
        return extract_json(res.text)
    except ValueError as e:
        raise PlatformError(_("The AI did not return valid JSON ({0}).").format(kwargs.get("feature", "adhoc"))) from e


# ---------------------------------------------------------------- ledger

def _log(app, feature, route, comp, status, *, error=None, latency=0, reference=None, masked=False, do_log=True):
    if not do_log:
        return
    try:
        if not frappe.db.table_exists(LOG_DT):
            return
        doc = frappe.get_doc({
            "doctype": LOG_DT, "app": (app or "")[:60], "feature": (feature or "")[:140], "status": status,
            "route": route["name"] if route else None, "provider": comp.provider if comp else None,
            "model": (comp.model if comp else "")[:140], "user": frappe.session.user,
            "tokens_in": comp.tokens_in if comp else 0, "tokens_out": comp.tokens_out if comp else 0,
            "latency_ms": latency, "fell_back": 1 if comp and comp.fell_back else 0,
            "saved_chars": comp.saved_chars if comp else 0, "masked": 1 if masked else 0,
            "attempts": "\n".join(comp.attempts)[:2000] if comp and comp.attempts else None,
            "error": (error or "")[:1000] or None,
            "reference_doctype": reference[0] if reference else None,
            "reference_name": reference[1] if reference else None,
        })
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
    except Exception:  # noqa: BLE001 - the ledger never breaks a call
        pass


def purge_call_logs():
    days = cint(platform_settings().get("call_log_retention_days")) or 90
    if frappe.db.table_exists(LOG_DT):
        frappe.db.delete(LOG_DT, {"creation": ("<", add_days(now_datetime(), -days))})
        frappe.db.commit()


def usage(days: int = 30) -> dict:
    """Totals per app and provider for the platform dashboard."""
    since = add_days(nowdate(), -int(days or 30))
    by_app = frappe.db.sql(f"""select app, count(*) calls, ifnull(sum(tokens_in+tokens_out),0) tokens,
        sum(status='Failed') failed, sum(status='Blocked') blocked, sum(fell_back) fell_back
        from `tab{LOG_DT}` where creation >= %s group by app order by tokens desc""", since, as_dict=True)
    by_provider = frappe.db.sql(f"""select provider, count(*) calls, ifnull(sum(tokens_in+tokens_out),0) tokens,
        round(avg(latency_ms)) avg_ms from `tab{LOG_DT}` where creation >= %s and status='Success'
        group by provider order by tokens desc""", since, as_dict=True)
    return {"since": since, "by_app": by_app, "by_provider": by_provider}
