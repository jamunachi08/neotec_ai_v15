# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Health loop. Daily it:

  1. opens an issue for a playbook whose last N runs failed, and closes it once a run succeeds;
  2. opens an issue when a playbook's recent quality scores are low;
  3. opens an issue when one AI provider keeps failing, or the monthly budget is reached;
  4. runs the configuration checks and keeps their issues in step;
  5. sends only the changes (opened / resolved) to the health channel;
  6. removes automated run history past the retention period.

Issues are keyed by a fingerprint, so a problem is one issue however often it is seen.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_first_day, now_datetime, nowdate

from neotec_ai.agents.automation import common

ADMIN_ROLES = {"Coworker Admin", "System Manager"}


def _require_admin():
    if not set(frappe.get_roles()) & ADMIN_ROLES:
        frappe.throw(_("Only a Coworker Admin can do this."), frappe.PermissionError)


# ---------------------------------------------------------------- issues

def open_issue(fingerprint, title, category, severity="warn", detail="", fix="", **links) -> str | None:
    """Creates or refreshes an open issue. Returns the name if it is new (for change notifications)."""
    name = frappe.db.get_value("Coworker Issue", {"fingerprint": fingerprint}, "name")
    now = now_datetime()
    if name:
        doc = frappe.get_doc("Coworker Issue", name)
        if doc.status == "Ignored":
            return None
        reopened = doc.status != "Open"
        doc.update({"status": "Open", "last_seen": now, "occurrences": cint(doc.occurrences) + 1, "detail": detail,
                    "fix_hint": fix, "severity": severity, "title": title, "resolved_on": None})
        doc.flags.ignore_permissions = True
        doc.save()
        return doc.name if reopened else None
    doc = frappe.get_doc({"doctype": "Coworker Issue", "fingerprint": fingerprint, "title": title[:140],
                          "category": category, "severity": severity, "status": "Open", "detail": detail,
                          "fix_hint": fix, "first_seen": now, "last_seen": now, "occurrences": 1,
                          **{k: v for k, v in links.items() if k in ("playbook", "routine", "trigger", "chain",
                                                                      "provider") and v}})
    doc.insert(ignore_permissions=True)
    return doc.name


def resolve_issue(fingerprint, note="") -> str | None:
    name = frappe.db.get_value("Coworker Issue", {"fingerprint": fingerprint, "status": "Open"}, "name")
    if not name:
        return None
    frappe.db.set_value("Coworker Issue", name, {"status": "Resolved", "resolved_on": now_datetime(),
                                                 "resolution": note or _("Recovered automatically.")})
    return name


# ---------------------------------------------------------------- evaluation

def _evaluate_playbooks(opened, resolved):
    s = frappe.get_cached_doc("Coworker Settings")
    limit = cint(s.failures_before_issue) or 3
    threshold = cint(s.low_score_threshold) or 2
    since = add_to_date(now_datetime(), days=-14)
    for pb in frappe.get_all("Coworker Run", filters={"creation": [">=", since]}, pluck="playbook", distinct=True):
        if not pb:
            continue
        rows = frappe.get_all("Coworker Run", filters={"playbook": pb, "status": ["not in", ["Queued", "Running"]]},
                              fields=["name", "status", "error", "score"], order_by="creation desc",
                              limit_page_length=max(limit, 5))
        statuses = [r.status for r in rows]
        fp = f"fail:{pb}"
        n = common.consecutive_failures(statuses)
        if n >= limit:
            errors = "\n".join(f"- {r.name}: {(r.error or r.status)[:200]}" for r in rows[:limit])
            new = open_issue(fp, f"Playbook {pb} failed {n} times in a row", "Failing Runs", "critical",
                             errors, _("Open the latest run and its conversation to see where it stopped."),
                             playbook=pb)
            if new:
                opened.append(new)
        elif statuses and statuses[0] not in ("Failed", "Budget Exceeded"):
            r = resolve_issue(fp)
            if r:
                resolved.append(r)

        scored = [cint(r.score) for r in rows if cint(r.score)]
        fq = f"quality:{pb}"
        if len(scored) >= 3:
            avg = sum(scored) / len(scored)
            if avg < threshold:
                new = open_issue(fq, f"Playbook {pb} results score low ({avg:.1f}/5)", "Low Quality", "warn",
                                 _("Average of the last {0} scored runs.").format(len(scored)),
                                 _("Make the instructions more specific: what to check, which figures to show, "
                                   "what counts as a finding."), playbook=pb)
                if new:
                    opened.append(new)
            else:
                r = resolve_issue(fq)
                if r:
                    resolved.append(r)


def _evaluate_providers(opened, resolved):
    since = add_to_date(now_datetime(), hours=-24)
    rows = frappe.db.sql("""select provider, count(*) from `tabCoworker Run`
        where creation >= %s and status = 'Failed' and provider is not null and error like %s
        group by provider""", (since, "%provider%"))
    failing = {p: c for p, c in rows if c >= 3}
    for p, c in failing.items():
        new = open_issue(f"provider:{p}", f"AI provider {p} failed {c} runs in 24 hours", "Provider", "critical",
                         fix=_("Run Test connection on the provider. Set a fallback provider in Coworker Settings."),
                         provider=p)
        if new:
            opened.append(new)
    for name in frappe.get_all("Coworker Issue", filters={"category": "Provider", "status": "Open"},
                               fields=["name", "fingerprint", "provider"]):
        if name.provider and name.provider not in failing:
            r = resolve_issue(name.fingerprint)
            if r:
                resolved.append(r)

    s = frappe.get_cached_doc("Coworker Settings")
    cap = cint(s.monthly_automation_tokens)
    fp = f"budget:{nowdate()[:7]}"
    if cap:
        from neotec_ai.agents.automation.playbooks import month_tokens

        used = month_tokens()
        if used >= cap:
            new = open_issue(fp, _("Monthly automation budget reached"), "Budget", "critical",
                             _("{0} of {1} tokens used this month. Playbook runs are paused until next month.")
                             .format(used, cap), _("Raise the budget in Coworker Settings or reduce schedules."))
            if new:
                opened.append(new)
        elif used >= cap * 0.8:
            new = open_issue(f"budget80:{nowdate()[:7]}", _("80% of the monthly automation budget used"), "Budget",
                             "warn", _("{0} of {1} tokens used this month.").format(used, cap))
            if new:
                opened.append(new)


def _evaluate_config(opened, resolved):
    from neotec_ai.agents.automation import doctor

    findings = doctor.checks()
    seen = set()
    for f in findings:
        seen.add(f["fingerprint"])
        new = open_issue(f["fingerprint"], f["title"], "Configuration", f["severity"], f["detail"], f["fix"],
                         **f["links"])
        if new:
            opened.append(new)
    for row in frappe.get_all("Coworker Issue", filters={"category": "Configuration", "status": "Open"},
                              fields=["fingerprint"]):
        if row.fingerprint not in seen:
            r = resolve_issue(row.fingerprint, _("The configuration was fixed."))
            if r:
                resolved.append(r)
    return findings


def _routines_switched_off(opened):
    s = frappe.get_cached_doc("Coworker Settings")
    limit = cint(s.max_routine_failures) or 5
    for r in frappe.get_all("Coworker Routine", filters={"enabled": 0, "consecutive_failures": [">=", limit]},
                            fields=["name", "last_result"]):
        new = open_issue(f"routine-off:{r.name}", f"Routine {r.name} was switched off after repeated failures",
                         "Failing Runs", "critical", (r.last_result or "")[:2000],
                         _("Fix the cause, then enable the routine again."), routine=r.name)
        if new:
            opened.append(new)


def _notify(opened, resolved):
    s = frappe.get_cached_doc("Coworker Settings")
    if not s.health_channel or not (opened or resolved):
        return
    from neotec_ai.agents.automation import delivery

    lines = []
    for name in opened:
        i = frappe.db.get_value("Coworker Issue", name, ["title", "severity"], as_dict=True)
        lines.append(f"- {common.SEVERITY_ICON.get(i.severity, '')} {_('Opened')}: {i.title} ({name})")
    for name in resolved:
        lines.append(f"- ✅ {_('Resolved')}: {frappe.db.get_value('Coworker Issue', name, 'title')} ({name})")
    worst = "critical" if any(frappe.db.get_value("Coworker Issue", n, "severity") == "critical" for n in opened) \
        else ("warn" if opened else "success")
    delivery.send([s.health_channel], _("Coworker health changed"), "\n".join(lines), worst, "Administrator",
                  ("Coworker Issue", None))


def purge_runs():
    s = frappe.get_cached_doc("Coworker Settings")
    days = cint(s.run_retention_days)
    if days <= 0:
        return 0
    cutoff = add_to_date(now_datetime(), days=-days)
    rows = frappe.get_all("Coworker Run", filters={"creation": ["<", cutoff], "source": ["!=", "Manual"]},
                          fields=["name", "conversation"], limit_page_length=5000)
    convs = [r.conversation for r in rows if r.conversation]
    if convs:
        frappe.db.delete("Coworker Message", {"conversation": ["in", convs]})
        frappe.db.delete("Coworker Conversation", {"name": ["in", convs]})
    if rows:
        frappe.db.delete("Coworker Run", {"name": ["in", [r.name for r in rows]]})
    frappe.db.delete("Coworker Signal", {"last_seen": ["<", cutoff]})
    return len(rows)


def evaluate():
    opened, resolved = [], []
    _evaluate_playbooks(opened, resolved)
    _evaluate_providers(opened, resolved)
    _routines_switched_off(opened)
    _evaluate_config(opened, resolved)
    frappe.db.commit()
    _notify(opened, resolved)
    frappe.db.commit()
    return opened, resolved


def daily():
    """Scheduler entry point."""
    from neotec_ai.agents.takeover import legacy_installed

    if legacy_installed():
        return
    if not cint(frappe.get_cached_doc("Coworker Settings").enabled):
        return
    try:
        evaluate()
    except Exception:  # noqa: BLE001
        frappe.db.rollback()
        frappe.log_error(title="Neotec AI health check failed")
    try:
        purge_runs()
        frappe.db.commit()
    except Exception:  # noqa: BLE001
        frappe.db.rollback()
        frappe.log_error(title="Neotec AI run purge failed")


# ---------------------------------------------------------------- dashboard API

@frappe.whitelist()
def run_checks():
    _require_admin()
    opened, resolved = evaluate()
    return {"opened": len(opened), "resolved": len(resolved),
            "open": frappe.db.count("Coworker Issue", {"status": "Open"})}


@frappe.whitelist()
def summary(days=7):
    _require_admin()
    days = min(max(cint(days) or 7, 1), 90)
    since = add_to_date(now_datetime(), days=-days)
    runs = frappe.get_all("Coworker Run", filters={"creation": [">=", since]},
                          fields=["playbook", "status", "duration_s", "tokens_in", "tokens_out", "cost", "score",
                                  "source"], limit_page_length=20000)
    done = [r for r in runs if r.status not in ("Queued", "Running")]
    ok = [r for r in done if r.status in ("Succeeded", "Nothing to Report")]
    scored = [cint(r.score) for r in done if cint(r.score)]
    per = {}
    for r in done:
        p = per.setdefault(r.playbook or "-", {"playbook": r.playbook or "-", "runs": 0, "ok": 0, "failed": 0,
                                               "quiet": 0, "tokens": 0, "cost": 0.0, "dur": 0.0, "scores": []})
        p["runs"] += 1
        p["ok"] += r.status in ("Succeeded", "Nothing to Report")
        p["failed"] += r.status in ("Failed", "Budget Exceeded")
        p["quiet"] += r.status == "Nothing to Report"
        p["tokens"] += cint(r.tokens_in) + cint(r.tokens_out)
        p["cost"] += flt(r.cost)
        p["dur"] += flt(r.duration_s)
        if cint(r.score):
            p["scores"].append(cint(r.score))
    table = []
    for p in per.values():
        last = frappe.db.get_value("Coworker Playbook", p["playbook"], "last_status") if p["playbook"] != "-" else ""
        table.append({"playbook": p["playbook"], "runs": p["runs"],
                      "success_rate": round(100 * p["ok"] / p["runs"]) if p["runs"] else 0,
                      "quiet": p["quiet"], "failed": p["failed"], "tokens": p["tokens"], "cost": round(p["cost"], 4),
                      "avg_duration": round(p["dur"] / p["runs"], 1) if p["runs"] else 0,
                      "avg_score": round(sum(p["scores"]) / len(p["scores"]), 1) if p["scores"] else None,
                      "last_status": last})
    for row in table:
        hist = frappe.get_all("Coworker Run", filters={"playbook": row["playbook"],
                                                      "status": ["not in", ["Queued", "Running"]]},
                              fields=["name", "status", "creation"], order_by="creation desc", limit_page_length=14)
        row["ribbon"] = [{"name": h.name, "status": h.status, "at": str(h.creation)[:16]} for h in reversed(hist)]
    table.sort(key=lambda x: (x["success_rate"], -x["runs"]))
    s = frappe.get_cached_doc("Coworker Settings")
    cap = cint(s.monthly_automation_tokens)
    from neotec_ai.agents.automation.playbooks import month_tokens

    issues = frappe.get_all("Coworker Issue", filters={"status": "Open"},
                            fields=["name", "title", "severity", "category", "last_seen", "occurrences", "fix_hint"],
                            order_by="last_seen desc", limit_page_length=100)
    rank = {"critical": 0, "warn": 1, "info": 2}
    issues.sort(key=lambda i: rank.get(i.severity, 3))
    by_source = {}
    for r in done:
        by_source[r.source or "-"] = by_source.get(r.source or "-", 0) + 1
    return {
        "days": days,
        "kpis": {
            "runs": len(done), "success_rate": round(100 * len(ok) / len(done)) if done else None,
            "avg_score": round(sum(scored) / len(scored), 1) if scored else None,
            "tokens": sum(cint(r.tokens_in) + cint(r.tokens_out) for r in done),
            "cost": round(sum(flt(r.cost) for r in done), 4),
            "open_issues": len(issues), "running": len(runs) - len(done),
            "month_tokens": month_tokens(), "month_cap": cap,
            "since_month": str(get_first_day(nowdate())),
        },
        "playbooks": table,
        "issues": issues,
        "by_source": by_source,
        "counts": {
            "playbooks": frappe.db.count("Coworker Playbook", {"enabled": 1}),
            "routines": frappe.db.count("Coworker Routine", {"enabled": 1}),
            "triggers": frappe.db.count("Coworker Trigger", {"enabled": 1}),
            "chains": frappe.db.count("Coworker Chain", {"enabled": 1}),
            "channels": frappe.db.count("Coworker Channel", {"enabled": 1}),
        },
    }
