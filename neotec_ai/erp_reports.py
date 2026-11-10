"""Run ERPNext's own reports (Script / Query reports) for the chat, BI builder, dashboards and schedules.

Why: financial figures such as Profit & Loss, Balance Sheet or receivables ageing are best taken from
ERPNext's own reports rather than rebuilt from raw tables.

How it stays safe
- A report runs through frappe.desk.query_report.run as the current user, which applies the same
  checks as opening the report in Desk (report roles + 'report' permission on its reference DocType).
- By default only reports listed (and enabled) in "Neotec ERP Report" are offered.
- Reports on security/system DocTypes are never offered; sensitive columns are dropped.
- Filters are checked against the report's declared filters; Link values must exist (with suggestions).
"""

import datetime
import json
import re
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate, strip_html

from neotec_ai.bi.engine import AccessError
from neotec_ai.query_engine import PlanError
from neotec_ai.security import filter_sensitive_columns, is_blocked_doctype

REPORT_TYPES = ("Script Report", "Query Report")
BLOCKED_MODULES = {"Core", "Desk", "Email", "Integrations", "Custom", "Printing", "Website", "Automation"}
FILTER_CACHE_SECONDS = 3600
QUERY_TIMEOUT_SECONDS = 90

START_DATE_NAMES = {"from_date", "start_date", "period_start_date", "from_posting_date", "date_from"}
END_DATE_NAMES = {"to_date", "end_date", "period_end_date", "to_posting_date", "date_to"}
POINT_DATE_NAMES = {"report_date", "as_on_date", "as_of_date", "posting_date", "date", "on_date"}
FISCAL_YEAR_NAMES = {"fiscal_year", "from_fiscal_year", "to_fiscal_year"}


class ReportError(PlanError):
    """Invalid report request; the message is safe to show to the user and the AI."""


class ReportAccessError(AccessError):
    """The user may not run this report."""


# --------------------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------------------

def _settings():
    return frappe.get_cached_doc("Neotec Settings")


def is_enabled():
    return bool(cint(_settings().get("enable_erp_reports")))


def access_mode():
    return _settings().get("erp_report_access") or "Listed Reports Only"


def _cache_local():
    if not hasattr(frappe.local, "neotec_report_access"):
        frappe.local.neotec_report_access = {}
    return frappe.local.neotec_report_access


def can_run(report_name):
    """True when the current user may run the report in Desk and it is a usable report."""
    cache = _cache_local()
    if report_name in cache:
        return cache[report_name]
    ok = False
    row = frappe.db.get_value(
        "Report", report_name, ["report_type", "disabled", "ref_doctype", "module"], as_dict=True
    )
    if row and row.report_type in REPORT_TYPES and not row.disabled and not is_blocked_doctype(row.ref_doctype) \
            and row.module not in BLOCKED_MODULES:
        from frappe.desk.query_report import get_report_doc

        previous = frappe.flags.mute_messages
        frappe.flags.mute_messages = True
        try:
            get_report_doc(report_name)
            ok = bool(frappe.has_permission(row.ref_doctype, "report")) if row.ref_doctype else True
        except (frappe.PermissionError, frappe.ValidationError, frappe.DoesNotExistError):
            ok = False
        finally:
            frappe.flags.mute_messages = previous
            frappe.clear_last_message()
    cache[report_name] = ok
    return ok


def listing(report_name):
    if frappe.db.exists("Neotec ERP Report", report_name):
        return frappe.get_cached_doc("Neotec ERP Report", report_name)
    return None


def check_allowed(report_name):
    if not is_enabled():
        raise ReportError(_("Running ERPNext reports is turned off in Neotec Settings."))
    if not report_name or not frappe.db.exists("Report", report_name):
        raise ReportError(_("There is no report named '{0}'.").format(report_name))
    lst = listing(report_name)
    if access_mode() == "Listed Reports Only" and not (lst and lst.enabled):
        raise ReportError(_("The report '{0}' is not enabled for the AI. An administrator can add it under Neotec ERP Report.").format(report_name))
    if lst is not None and not lst.enabled:
        raise ReportError(_("The report '{0}' has been disabled for the AI.").format(report_name))
    if not can_run(report_name):
        raise ReportAccessError(_("You don't have permission to run the report '{0}'.").format(report_name))


def available_reports(limit=300):
    """Reports the current user can run: [{name, purpose, module, sample_questions, report_type}]."""
    if not is_enabled():
        return []
    listed = {
        r.name: r for r in frappe.get_all(
            "Neotec ERP Report",
            fields=["name", "enabled", "purpose", "sample_questions"],
        )
    }
    if access_mode() == "Listed Reports Only":
        names = [n for n, r in listed.items() if r.enabled]
    else:
        names = frappe.get_all(
            "Report",
            filters={"report_type": ["in", REPORT_TYPES], "disabled": 0, "module": ["not in", list(BLOCKED_MODULES)]},
            pluck="name",
            limit=limit,
        )
        names = [n for n in names if n not in listed or listed[n].enabled]
    out = []
    for name in names:
        if not can_run(name):
            continue
        meta = frappe.db.get_value("Report", name, ["module", "report_type", "ref_doctype"], as_dict=True) or {}
        lst = listed.get(name)
        out.append({
            "name": name,
            "purpose": (lst.purpose if lst else "") or f"{meta.get('report_type', 'Report')} on {meta.get('ref_doctype') or 'data'}",
            "sample_questions": (lst.sample_questions if lst else "") or "",
            "module": meta.get("module"),
            "report_type": meta.get("report_type"),
        })
    return out


# --------------------------------------------------------------------------------------
# Filter discovery (reads the filters a report declares in its JavaScript / filter table)
# --------------------------------------------------------------------------------------

def get_filter_defs(report_name):
    key = f"neotec_ai:report_filters:{report_name}"
    cache = frappe.cache if hasattr(frappe.cache, "get_value") else frappe.cache()
    cached = cache.get_value(key)
    if cached is not None:
        defs = cached
    else:
        defs = discover_filters(frappe.get_doc("Report", report_name))
        cache.set_value(key, defs, expires_in_sec=FILTER_CACHE_SECONDS)
    lst = listing(report_name)
    if lst and lst.default_filters:
        try:
            house = json.loads(lst.default_filters)
        except ValueError:
            house = {}
        defs = [dict(d) for d in defs]
        for d in defs:
            if d["fieldname"] in house:
                d["default"] = house[d["fieldname"]]
                d["dynamic_default"] = False
        known = {d["fieldname"] for d in defs}
        for k, v in house.items():
            if k not in known:
                defs.append({"fieldname": k, "label": k.replace("_", " ").title(), "fieldtype": "Data",
                             "options": None, "reqd": False, "default": v, "dynamic_default": False})
    return defs


def discover_filters(report_doc):
    defs = {}

    def add(d):
        if d.get("fieldname") and d["fieldname"] not in defs:
            defs[d["fieldname"]] = d

    for row in report_doc.get("filters") or []:  # Report Filter child table (custom reports)
        add(_clean_def({
            "fieldname": row.get("fieldname"), "label": row.get("label"), "fieldtype": row.get("fieldtype"),
            "options": row.get("options"), "reqd": row.get("mandatory"), "default": row.get("default"),
        }))

    for js in _report_js_sources(report_doc):
        for d in extract_js_filters(js):
            add(d)
    return list(defs.values())


def _report_js_sources(report_doc):
    sources = []
    if report_doc.get("javascript"):
        sources.append(report_doc.javascript)
    if report_doc.is_standard == "Yes" and report_doc.module:
        try:
            folder = frappe.scrub(report_doc.name)
            path = frappe.get_module_path(report_doc.module, "report", folder, f"{folder}.js")
            with open(path, encoding="utf-8") as fh:
                sources.append(fh.read())
        except (OSError, Exception):
            pass
    # Shared filter files referenced as erpnext.<namespace> (e.g. erpnext.financial_statements)
    seen = set()
    for js in list(sources):
        for ns in re.findall(r"\berpnext\.([a-z_]+)\b", js):
            if ns in seen or ns in ("utils", "queries", "stock", "accounts", "selling", "buying"):
                continue
            seen.add(ns)
            try:
                path = frappe.get_app_path("erpnext", "public", "js", f"{ns}.js")
                with open(path, encoding="utf-8") as fh:
                    sources.append(fh.read())
            except (OSError, Exception):
                continue
    return sources


_REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%<>~^")


def _mask_js(js):
    """Same-length copy of the source with string/regex contents and comments blanked out."""
    out = list(js)
    i, n = 0, len(js)
    prev = ""  # last significant character outside strings/comments
    while i < n:
        c = js[i]
        if c in "\"'`":
            q = c
            i += 1
            while i < n and js[i] != q:
                if js[i] == "\\":
                    out[i] = " "
                    i += 1
                if i < n:
                    out[i] = " " if js[i] != "\n" else "\n"
                i += 1
            i += 1
            prev = q
            continue
        if c == "/" and i + 1 < n and js[i + 1] == "/":
            while i < n and js[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if c == "/" and i + 1 < n and js[i + 1] == "*":
            while i < n and not (js[i] == "*" and i + 1 < n and js[i + 1] == "/"):
                out[i] = " " if js[i] != "\n" else "\n"
                i += 1
            if i < n:
                out[i] = " "
                if i + 1 < n:
                    out[i + 1] = " "
            i += 2
            continue
        if c == "/" and (prev == "" or prev in _REGEX_PRECEDERS):  # regex literal
            i += 1
            in_class = False
            while i < n and js[i] != "\n":
                ch = js[i]
                if ch == "\\":
                    out[i] = " "
                    i += 1
                    if i < n:
                        out[i] = " "
                    i += 1
                    continue
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    break
                out[i] = " "
                i += 1
            i += 1
            prev = "/"
            continue
        if not c.isspace():
            prev = c
        i += 1
    return "".join(out)


def _match_close(masked, start, opening, closing):
    depth = 0
    for i in range(start, len(masked)):
        ch = masked[i]
        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return i
    return -1


_FILTER_ARRAY = re.compile(r"""(?:^|[^\w$.])(["']?)filters\1\s*\]?\s*[:=]\s*\[""")
_FILTER_PUSH = re.compile(r"""(?:\[\s*["']filters["']\s*\]|\bfilters)\s*\.\s*(?:push|unshift|splice)\s*\(""")


def extract_js_filters(js):
    """Filter objects declared in `filters: [...]`, `filters = [...]` or `...filters.push(...)` (not dialog fields)."""
    masked = _mask_js(js)
    spans = []
    for m in _FILTER_ARRAY.finditer(js):
        start = m.end() - 1
        if masked[start] != "[":
            continue
        # the word 'filters' must be real code (an object key or variable), not text in a string or comment
        word = js.find("filters", m.start())
        if word < 0:
            continue
        if m.group(1):
            if masked[word - 1] != m.group(1):
                continue
        elif masked[word] != "f":
            continue
        end = _match_close(masked, start, "[", "]")
        if end > start:
            spans.append((start + 1, end))
    for m in _FILTER_PUSH.finditer(js):
        start = m.end() - 1
        if masked[start] != "(" or masked[m.start()] == " ":
            continue
        end = _match_close(masked, start, "(", ")")
        if end > start:
            spans.append((start + 1, end))

    found = []
    for a, b in spans:
        depth = 0
        i = a
        while i < b:
            ch = masked[i]
            if ch == "{" and depth == 0:
                close = _match_close(masked, i, "{", "}")
                if close < 0 or close > b:
                    break
                pairs = _top_level_pairs(js[i + 1 : close], masked[i + 1 : close])
                if "fieldname" in pairs:
                    d = _clean_def({k: _js_value(v) for k, v in pairs.items()})
                    if d.get("fieldname"):
                        found.append(d)
                i = close + 1
                continue
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            i += 1
    return found


def _top_level_pairs(body, masked):
    pairs, depth, last = {}, 0, 0
    pieces = []
    for i, ch in enumerate(masked):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            pieces.append((last, i))
            last = i + 1
    pieces.append((last, len(masked)))
    for a, b in pieces:
        k = a
        while k < b and masked[k].isspace():  # comments are blanked in the masked copy
            k += 1
        m = re.match(r"[\"']?([A-Za-z_$][\w$]*)[\"']?\s*:", body[k:b])
        if m:
            pairs[m.group(1)] = body[k + m.end() : b].strip()
    return pairs


_UNDEF = object()


def _js_value(raw):
    v = (raw or "").strip()
    m = re.fullmatch(r"__\(\s*([\"'`])(.*?)\1\s*(?:,.*)?\)", v, re.S)
    if m:
        return _unescape(m.group(2))
    m = re.fullmatch(r"([\"'`])(.*)\1", v, re.S)
    if m and "${" not in m.group(2):
        return _unescape(m.group(2))
    if re.fullmatch(r"-?\d+(\.\d+)?", v):
        return float(v) if "." in v else int(v)
    if v in ("true", "false"):
        return v == "true"
    if v.startswith("[") and v.endswith("]"):
        items = re.findall(r"""__\(\s*(["'`])(.*?)\1\s*\)|(["'`])(.*?)\3""", v[1:-1], re.S)
        inner = re.sub(r"""__\(\s*(["'`]).*?\1\s*\)|(["'`]).*?\2|[\s,]""", "", v[1:-1], flags=re.S)
        if items and not inner:
            return [_unescape(a[1] or a[3]) for a in items]
        values = re.findall(r"""\bvalue\s*:\s*(["'`])(.*?)\1""", v[1:-1], re.S)
        if values and v[1:-1].count("{") == len(values):
            return [_unescape(x[1]) for x in values]
    return _UNDEF


def _unescape(s):
    return s.replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"')


def _clean_def(d, raw=None):
    def val(k):
        x = d.get(k)
        return None if x is _UNDEF else x

    fieldname = val("fieldname")
    if not isinstance(fieldname, str) or not re.fullmatch(r"[A-Za-z_][\w]{0,139}", fieldname or ""):
        return {}
    options = val("options")
    if isinstance(options, str) and "\n" in options:
        options = [o for o in (x.strip() for x in options.split("\n")) if o]
    default = d.get("default")
    dynamic = default is _UNDEF
    return {
        "fieldname": fieldname,
        "label": str(val("label") or fieldname.replace("_", " ").title())[:140],
        "fieldtype": str(val("fieldtype") or "Data"),
        "options": options if isinstance(options, (str, list)) else None,
        "reqd": bool(val("reqd")),
        "default": None if dynamic else default,
        "dynamic_default": dynamic,
        "depends_on": val("depends_on") if isinstance(val("depends_on"), str) else None,
    }


def describe_filters(defs, limit=25):
    lines = []
    for d in defs[:limit]:
        bits = [d["fieldname"], d["fieldtype"]]
        opts = d.get("options")
        if isinstance(opts, list) and opts:
            bits.append("one of: " + " | ".join(str(o) for o in opts[:15]))
        elif isinstance(opts, str) and d["fieldtype"] in ("Link", "MultiSelectList", "Table MultiSelect"):
            bits.append(f"{opts} name(s)")
        if d.get("reqd"):
            bits.append("required")
        if d.get("default") not in (None, ""):
            bits.append(f"default {d['default']}")
        elif d.get("dynamic_default") or smart_default_kind(d):
            bits.append("auto-default")
        lines.append("  - " + ", ".join(str(b) for b in bits))
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Defaults and validation
# --------------------------------------------------------------------------------------

def smart_default_kind(d):
    name, ftype, opts = d["fieldname"], d["fieldtype"], d.get("options")
    if name == "company" or (ftype == "Link" and opts == "Company"):
        return "company"
    if name in FISCAL_YEAR_NAMES or (ftype == "Link" and opts == "Fiscal Year"):
        return "fiscal_year"
    if ftype in ("Date", "Datetime") or name in START_DATE_NAMES | END_DATE_NAMES | POINT_DATE_NAMES:
        if name in START_DATE_NAMES:
            return "start"
        if name in END_DATE_NAMES:
            return "end"
        if name in POINT_DATE_NAMES:
            return "point"
    if name in ("periodicity", "range") and isinstance(opts, list) and "Monthly" in opts:
        return "monthly"
    return None


def default_company():
    """The user's default company if they may read it, else the first company they can read."""
    for company in (frappe.defaults.get_user_default("Company"),
                    frappe.db.get_single_value("Global Defaults", "default_company")):
        if company and frappe.has_permission("Company", "read", doc=company):
            return company
    companies = frappe.get_list("Company", pluck="name", limit=1)
    return companies[0] if companies else None


def fiscal_year(date=None, company=None):
    """(name, start, end) of the fiscal year containing date, or a calendar year fallback."""
    date = getdate(date or nowdate())
    try:
        from erpnext.accounts.utils import get_fiscal_year

        fy = get_fiscal_year(date, company=company, as_dict=False)
        return fy[0], getdate(fy[1]), getdate(fy[2])
    except Exception:
        frappe.clear_last_message()
        row = frappe.db.sql(
            "select name, year_start_date, year_end_date from `tabFiscal Year` "
            "where %(d)s between year_start_date and year_end_date and disabled = 0 order by year_start_date desc limit 1",
            {"d": date}, as_dict=True,
        ) if frappe.db.exists("DocType", "Fiscal Year") else []
        if row:
            return row[0].name, getdate(row[0].year_start_date), getdate(row[0].year_end_date)
        return str(date.year), datetime.date(date.year, 1, 1), datetime.date(date.year, 12, 31)


def _smart_value(kind, filters, period=None):
    if kind == "company":
        return default_company()
    company = filters.get("company")
    if kind == "fiscal_year":
        return fiscal_year(period[1] if period else None, company)[0]
    if kind == "start":
        return str(period[0]) if period else str(fiscal_year(None, company)[1])
    if kind in ("end", "point"):
        return str(period[1]) if period else nowdate()
    if kind == "monthly":
        return "Monthly"
    return None


def resolve_filters(defs, supplied, period=None, company=None):
    """Return (filters, notes) or raise ReportError with every problem found.

    period: optional (start_date, end_date) imposed by a dashboard; company: optional company override.
    """
    supplied = dict(supplied or {})
    by_name = {d["fieldname"]: d for d in defs}
    if company and "company" in by_name:  # dashboard company filter, validated like any user value
        supplied["company"] = company
    filters, notes, errors = {}, [], []

    for d in defs:  # company first so fiscal-year defaults can use it
        if smart_default_kind(d) == "company" and d["fieldname"] not in supplied:
            v = d.get("default") or _smart_value("company", filters)
            if v:
                filters[d["fieldname"]] = v

    auto = {}  # values computed on the server (trusted, not re-validated)
    if period:
        names = set(by_name)
        if names & (START_DATE_NAMES | END_DATE_NAMES | POINT_DATE_NAMES):
            for n in names & START_DATE_NAMES:
                auto[n] = str(period[0])
            for n in names & (END_DATE_NAMES | POINT_DATE_NAMES):
                auto[n] = str(period[1])
            fb = by_name.get("filter_based_on")
            if fb and isinstance(fb.get("options"), list) and "Date Range" in fb["options"]:
                auto["filter_based_on"] = "Date Range"
        for n in names & FISCAL_YEAR_NAMES:
            auto[n] = fiscal_year(period[0] if n.startswith("from") else period[1],
                                  supplied.get("company") or filters.get("company"))[0]
        for k in auto:
            supplied.pop(k, None)

    for key, value in supplied.items():
        if not re.fullmatch(r"[A-Za-z_]\w{0,139}", str(key)):
            errors.append(f"'{key}' is not a valid filter name.")
            continue
        d = by_name.get(key)
        if d is None:  # only declared filters (and house defaults) reach the report
            notes.append(f"'{key}' is not a filter of this report and was ignored.")
            continue
        try:
            filters[key] = _check_value(d, value)
        except ReportError as e:
            errors.append(str(e))

    filters.update(auto)
    for d in defs:
        name = d["fieldname"]
        if name in filters:
            continue
        if d.get("default") not in (None, ""):
            filters[name] = d["default"]
            continue
        kind = smart_default_kind(d)
        if kind and (d.get("reqd") or d.get("dynamic_default")):  # an optional blank filter often means "all"
            v = _smart_value(kind, filters, period)
            if v not in (None, ""):
                filters[name] = v
                continue
        if d.get("reqd") and d["fieldtype"] == "Select" and isinstance(d.get("options"), list):
            first = next((o for o in d["options"] if str(o).strip()), None)
            if first is not None:
                filters[name] = first
                continue
        if d.get("reqd") and not d.get("depends_on"):
            errors.append(f"'{name}' ({d['label']}) is required" + (f"; choose one of: {', '.join(map(str, d['options'][:15]))}" if isinstance(d.get("options"), list) else "") + ".")

    if errors:
        raise ReportError("Filter problems: " + " ".join(errors))
    return filters, notes


MAX_VALUE_CHARS = 500


def _plain(v):
    if isinstance(v, list):
        return len(v) <= 100 and all(isinstance(x, (str, int, float)) and len(str(x)) <= MAX_VALUE_CHARS for x in v)
    if isinstance(v, str):
        return len(v) <= MAX_VALUE_CHARS
    return v is None or isinstance(v, (int, float, bool))


def _check_value(d, value):
    name, ftype, opts = d["fieldname"], d["fieldtype"], d.get("options")
    if not _plain(value):
        raise ReportError(f"'{name}' must be plain text (up to {MAX_VALUE_CHARS} characters), a number or a list of up to 100 names.")
    if ftype == "Select" and isinstance(opts, list) and opts and value not in (None, ""):
        match = next((o for o in opts if str(o).lower() == str(value).lower()), None)
        if match is None:
            raise ReportError(f"'{name}' must be one of: {', '.join(map(str, opts[:20]))} (got '{value}').")
        return match
    if ftype in ("Date", "Datetime") and value not in (None, ""):
        try:
            return str(getdate(value))
        except Exception:
            raise ReportError(f"'{name}' must be a date (YYYY-MM-DD), got '{value}'.")
    if ftype == "Check":
        return 1 if value in (1, True, "1", "true", "Yes", "yes") else 0
    if ftype in ("Int", "Float", "Currency", "Percent") and value not in (None, ""):
        try:
            return float(value) if ftype != "Int" else int(float(value))
        except (TypeError, ValueError):
            raise ReportError(f"'{name}' must be a number, got '{value}'.")
    if ftype in ("Link", "MultiSelectList", "Table MultiSelect") and isinstance(opts, str) and frappe.db.exists("DocType", opts):
        values = value if isinstance(value, list) else ([value] if value not in (None, "") else [])
        if ftype == "Link" and isinstance(value, list):
            raise ReportError(f"'{name}' takes a single {opts} name.")
        fixed = [resolve_link(opts, v, name) for v in values]
        if ftype == "Link":
            return fixed[0] if fixed else value
        return fixed
    return value


def resolve_link(doctype, value, filter_name):
    """Exact name, or a unique case-insensitive / title match; otherwise an error with suggestions."""
    value = str(value).strip()
    if frappe.db.exists(doctype, value):
        if not frappe.has_permission(doctype, "read", doc=value):
            raise ReportAccessError(_("You don't have access to {0} '{1}'.").format(_(doctype), value))
        return value
    meta = frappe.get_meta(doctype)
    title = meta.title_field if meta.title_field and meta.get_field(meta.title_field) else None
    safe = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    # get_list applies the user's permissions, so suggestions only include records they can read
    candidates = frappe.get_list(doctype, filters=[["name", "like", safe]], pluck="name", limit=2)
    if len(candidates) == 1:
        return candidates[0]
    found = []
    if title:
        found = frappe.get_list(doctype, filters=[[title, "like", f"%{safe}%"]], pluck="name", limit=6)
    found += [n for n in frappe.get_list(doctype, filters=[["name", "like", f"%{safe}%"]], pluck="name", limit=6) if n not in found]
    if len(found) == 1:
        return found[0]
    hint = f" Did you mean: {', '.join(found[:6])}?" if found else ""
    raise ReportError(f"'{value}' is not a {doctype} for filter '{filter_name}'.{hint}")


# --------------------------------------------------------------------------------------
# Running and normalising
# --------------------------------------------------------------------------------------

RUNS_PER_MINUTE = 30


def _check_run_rate():
    cache = frappe.cache if hasattr(frappe.cache, "get_value") else frappe.cache()
    key = f"neotec_ai:report_runs:{frappe.session.user}:{int(datetime.datetime.now().timestamp() // 60)}"
    count = cint(cache.get_value(key))
    if count >= RUNS_PER_MINUTE:
        raise ReportError(_("Too many report runs in the last minute. Please wait a moment and try again."))
    cache.set_value(key, count + 1, expires_in_sec=120)


def run(report_name, filters=None, max_rows=500, period=None, company=None):
    """Run a report as the current user. Returns a result in the BI engine's shape plus extras."""
    check_allowed(report_name)
    _check_run_rate()
    defs = get_filter_defs(report_name)
    resolved, notes = resolve_filters(defs, filters if isinstance(filters, dict) else {}, period, company)

    from frappe.desk.query_report import run as query_report_run

    mariadb = frappe.db.db_type == "mariadb"
    previous_timeout = None
    previous_mute = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        if mariadb:
            previous_timeout = frappe.db.sql("SELECT @@SESSION.max_statement_time")[0][0]
            frappe.db.sql(f"SET SESSION max_statement_time={int(QUERY_TIMEOUT_SECONDS)}")
        raw = query_report_run(report_name, filters=frappe._dict(resolved), user=frappe.session.user, ignore_prepared_report=True)
    except frappe.PermissionError:
        raise ReportAccessError(_("You don't have permission to run the report '{0}'.").format(report_name))
    except frappe.ValidationError as e:
        msg = strip_html(str(e) or (frappe.flags.error_message or "")) or _("The report rejected these filters.")
        raise ReportError(f"{report_name}: {msg}")
    finally:
        frappe.flags.mute_messages = previous_mute
        frappe.clear_last_message()
        if mariadb and previous_timeout is not None:
            try:
                frappe.db.sql(f"SET SESSION max_statement_time={float(previous_timeout)}")
            except Exception:
                pass

    result = normalise_result(raw or {}, max_rows)
    result.update({"source": report_name, "tables": [], "filters_used": resolved, "notes": notes, "report": report_name})
    return result


def normalise_result(raw, max_rows=500):
    raw_cols = raw.get("columns") or []
    data = raw.get("result") or []
    columns, dict_keys, used = [], [], set()
    for i, c in enumerate(raw_cols):
        if isinstance(c, dict):
            label = c.get("label") or c.get("fieldname") or f"Column {i + 1}"
            ftype = c.get("fieldtype") or "Data"
            source = c.get("fieldname") or label
        else:
            parts = str(c).split(":")
            label = parts[0] or f"Column {i + 1}"
            ftype = (parts[1].split("/")[0] if len(parts) > 1 and parts[1] else "Data") or "Data"
            source = label
        # dict rows are keyed by fieldname, or by the scrubbed label for "Label:Type" columns
        dict_keys.append([k for k in (c.get("fieldname") if isinstance(c, dict) else None, frappe.scrub(str(label))) if k])
        fieldname = re.sub(r"[^a-z0-9_]", "_", frappe.scrub(str(source)).lower())[:60] or f"col_{i}"
        if fieldname[0].isdigit():
            fieldname = f"c_{fieldname}"
        base, n = fieldname, 2
        while fieldname in used:
            fieldname = f"{base}_{n}"
            n += 1
        used.add(fieldname)
        columns.append({"fieldname": fieldname, "label": strip_html(str(label))[:140], "fieldtype": ftype})

    label_idx = next((i for i, c in enumerate(columns) if c["fieldtype"] in ("Data", "Link", "Dynamic Link", "Select")), 0)
    rows, total_row = [], None
    dict_rows = any(isinstance(r, dict) for r in data)
    for pos, r in enumerate(data):
        if isinstance(r, dict):
            vals = []
            for keys in dict_keys:
                vals.append(_clean(next((r[k] for k in keys if k in r), None)))
            indent = cint(r.get("indent") or 0)
        elif isinstance(r, (list, tuple)):
            vals = [_clean(r[i]) if i < len(r) else None for i in range(len(columns))]
            indent = 0
        else:
            continue
        if all(v in (None, "") for v in vals):
            continue
        first_text = next((v for v in vals if isinstance(v, str) and v.strip()), "")
        is_total = pos == len(data) - 1 and (
            (dict_rows and isinstance(r, (list, tuple))) or first_text.strip().lower() in ("total", "grand total")
        )
        if is_total:  # kept out of rows so charts and the AI don't count it twice
            total_row = vals
            continue
        if indent and columns and isinstance(vals[label_idx], str):
            vals[label_idx] = "\u00a0\u00a0" * min(indent, 8) + vals[label_idx]
        rows.append(vals)

    if total_row is not None:
        rows.append(total_row)
        columns, rows = filter_sensitive_columns(columns, rows)
        total_row = rows.pop()
    else:
        columns, rows = filter_sensitive_columns(columns, rows)
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]

    summary = []
    for s in raw.get("report_summary") or []:
        if isinstance(s, dict) and s.get("label") is not None:
            summary.append({"label": strip_html(str(s.get("label"))), "value": _clean(s.get("value")),
                            "currency": s.get("currency")})
    if total_row is not None and not summary:
        numeric = {"Currency", "Float", "Int", "Percent"}
        for c, v in zip(columns, total_row):
            if c["fieldtype"] in numeric and isinstance(v, (int, float)) and len(summary) < 6:
                summary.append({"label": f"Total {c['label']}", "value": v, "currency": None})
    message = raw.get("message")
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "summary": summary,
        "total_row": total_row,
        "message": strip_html(str(message))[:500] if isinstance(message, str) else None,
    }


def _clean(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, (datetime.date, datetime.datetime, datetime.timedelta)):
        return str(v)
    if isinstance(v, str):
        s = strip_html(v) if "<" in v else v
        s = s.strip()
        if len(s) > 1 and s[0] == s[-1] == "'":
            s = s[1:-1]
        return s
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)[:500]
    return v


# --------------------------------------------------------------------------------------
# Helpers used by chat / BI
# --------------------------------------------------------------------------------------

def run_for_definition(spec, extra=None, max_rows=None):
    """spec: {"report": name, "filters": {...}}; extra: dashboard filters {timespan|from_date,to_date, company}."""
    from neotec_ai.bi import engine

    if not isinstance(spec, dict) or not spec.get("report"):
        raise ReportError("An ERPNext report definition needs 'report' and optional 'filters'.")
    period, company = None, None
    extra = extra or {}
    if extra.get("timespan"):
        period = engine.timespan_range(str(extra["timespan"]).lower())
    elif extra.get("from_date") and extra.get("to_date"):
        period = (getdate(extra["from_date"]), getdate(extra["to_date"]))
    if extra.get("company"):
        company = extra["company"]
    filters = spec.get("filters") or {}
    if not isinstance(filters, dict):
        raise ReportError("Report 'filters' must be an object of filter name to value.")
    if period:  # dashboard period replaces the report's own dates
        defs = get_filter_defs(spec["report"])
        date_like = START_DATE_NAMES | END_DATE_NAMES | POINT_DATE_NAMES | FISCAL_YEAR_NAMES | {"filter_based_on"}
        filters = {k: v for k, v in filters.items() if k not in date_like or k not in {d["fieldname"] for d in defs}}
    return run(spec["report"], filters, max_rows=max_rows or engine._max_rows(), period=period, company=company)


def compact_for_ai(result, max_rows=40, max_chars=12000):
    cols = [c["fieldname"] for c in result["columns"]]
    lines = [f"Report: {result['report']} ({result['row_count']} rows{', truncated' if result['truncated'] else ''})",
             f"Filters used: {json.dumps(result['filters_used'], default=str)}",
             "Columns: " + ", ".join(f"{c['fieldname']} ({c['label']}, {c['fieldtype']})" for c in result["columns"])]
    if result.get("summary"):
        lines.append("Summary: " + "; ".join(f"{s['label']}: {s['value']}" for s in result["summary"]))
    if result.get("total_row"):
        lines.append("Report total row (not included in Rows): " + json.dumps(dict(zip(cols, result["total_row"])), default=str))
    if result.get("notes"):
        lines.append("Notes: " + " ".join(result["notes"]))
    data = [dict(zip(cols, r)) for r in result["rows"][:max_rows]]
    lines.append("Rows: " + json.dumps(data, default=str))
    if result["row_count"] > max_rows:
        lines.append(f"(Showing {max_rows} of {result['row_count']} rows. Put the report in your answer to show all rows.)")
    text = "\n".join(lines)
    return text[:max_chars] + ("\n...[TRUNCATED]" if len(text) > max_chars else "")
