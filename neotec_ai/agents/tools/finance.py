# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Finance tools with the arithmetic done in code, not by the model."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, date_diff, flt, get_first_day, get_last_day, getdate, nowdate

from neotec_ai.agents.engine.registry import tool
from neotec_ai.agents.tools._common import company_filter, ensure_doctype

S = {"type": "string"}
I = {"type": "integer"}
AGE_BUCKETS = [("Not due", None, -1), ("1-30", 1, 30), ("31-60", 31, 60), ("61-90", 61, 90),
               ("91-180", 91, 180), ("180+", 181, 10**6)]


def _age_bucket(days_overdue):
    for label, lo, hi in AGE_BUCKETS:
        if lo is None and days_overdue <= hi:
            return label
        if lo is not None and lo <= days_overdue <= hi:
            return label
    return "180+"


def period_range(period: str, from_date=None, to_date=None):
    today = getdate(nowdate())
    p = (period or "this_month").lower()
    if p == "custom":
        if not (from_date and to_date):
            frappe.throw(_("Custom period needs from_date and to_date."))
        return getdate(from_date), getdate(to_date)
    if p == "this_month":
        return get_first_day(today), today
    if p == "last_month":
        start = get_first_day(add_months(today, -1))
        return start, get_last_day(start)
    if p == "this_quarter":
        q_start = getdate(f"{today.year}-{((today.month - 1) // 3) * 3 + 1:02d}-01")
        return q_start, today
    if p == "last_quarter":
        q_start = getdate(f"{today.year}-{((today.month - 1) // 3) * 3 + 1:02d}-01")
        start = add_months(q_start, -3)
        return getdate(start), getdate(add_days(q_start, -1))
    if p in ("ytd", "this_year"):
        return getdate(f"{today.year}-01-01"), today
    if p == "last_year":
        return getdate(f"{today.year - 1}-01-01"), getdate(f"{today.year - 1}-12-31")
    if p.startswith("last_") and p.endswith("_days"):
        n = cint(p[5:-5]) or 30
        return getdate(add_days(today, -n + 1)), today
    frappe.throw(_("Unknown period {0}.").format(period))


def _previous_range(start, end):
    days = date_diff(end, start) + 1
    prev_end = add_days(start, -1)
    return getdate(add_days(prev_end, -days + 1)), getdate(prev_end)


@tool("receivables_aging", "Receivables aging",
      "Customer receivables grouped into aging buckets by days overdue (Not due, 1-30, 31-60, 61-90, 91-180, 180+), "
      "with the top customers. Computed from submitted Sales Invoices with an outstanding amount.",
      {"company": S, "customer": S, "as_on": {"type": "string", "description": "YYYY-MM-DD, default today"}},
      category="Finance")
def receivables_aging(company=None, customer=None, as_on=None):
    ensure_doctype("Sales Invoice")
    companies = company_filter(company)
    as_on = getdate(as_on or nowdate())
    filters = {"docstatus": 1, "outstanding_amount": [">", 0], "company": ["in", companies]}
    if customer:
        filters["customer"] = customer
    rows = frappe.get_list("Sales Invoice", filters=filters,
                           fields=["name", "customer", "customer_name", "due_date", "outstanding_amount",
                                   "currency", "company"], limit_page_length=50000)
    buckets = defaultdict(float)
    per_customer = defaultdict(lambda: defaultdict(float))
    names = {}
    currencies = set()
    for r in rows:
        overdue = date_diff(as_on, r.due_date) if r.due_date else 0
        b = _age_bucket(overdue)
        amt = flt(r.outstanding_amount)
        buckets[b] += amt
        per_customer[r.customer][b] += amt
        per_customer[r.customer]["total"] += amt
        names[r.customer] = r.customer_name
        currencies.add(r.currency)
    top = sorted(per_customer.items(), key=lambda kv: kv[1]["total"], reverse=True)[:15]
    total = sum(buckets.values())
    overdue_total = total - buckets.get("Not due", 0)
    return {
        "as_on": str(as_on), "companies": companies, "invoices": len(rows),
        "currencies": sorted(c for c in currencies if c),
        "total_outstanding": round(total, 2), "overdue": round(overdue_total, 2),
        "overdue_pct": round(overdue_total / total * 100, 1) if total else 0,
        "buckets": [{"bucket": label, "amount": round(buckets.get(label, 0), 2)} for label, *_ in AGE_BUCKETS],
        "top_customers": [{"customer": c, "customer_name": names.get(c),
                           **{k: round(v, 2) for k, v in d.items()}} for c, d in top],
        "note": "Amounts are in each invoice's party currency." if len(currencies) > 1 else "",
    }


@tool("payables_due", "Payables due",
      "Supplier invoices that are overdue or due within the next N days, from submitted Purchase Invoices.",
      {"company": S, "days_ahead": I, "supplier": S}, category="Finance")
def payables_due(company=None, days_ahead=30, supplier=None):
    ensure_doctype("Purchase Invoice")
    companies = company_filter(company)
    today = getdate(nowdate())
    horizon = getdate(add_days(today, cint(days_ahead) or 30))
    filters = {"docstatus": 1, "outstanding_amount": [">", 0], "company": ["in", companies]}
    if supplier:
        filters["supplier"] = supplier
    rows = frappe.get_list("Purchase Invoice", filters=filters,
                           fields=["name", "supplier", "supplier_name", "due_date", "outstanding_amount",
                                   "currency", "bill_no"], order_by="due_date asc", limit_page_length=50000)
    overdue, due_soon, later = [], [], 0.0
    for r in rows:
        d = getdate(r.due_date) if r.due_date else today
        item = {"invoice": r.name, "supplier": r.supplier_name or r.supplier, "bill_no": r.bill_no,
                "due_date": str(d), "outstanding": flt(r.outstanding_amount), "currency": r.currency}
        if d < today:
            item["days_overdue"] = date_diff(today, d)
            overdue.append(item)
        elif d <= horizon:
            due_soon.append(item)
        else:
            later += flt(r.outstanding_amount)
    return {
        "today": str(today), "horizon": str(horizon),
        "overdue_total": round(sum(i["outstanding"] for i in overdue), 2), "overdue_count": len(overdue),
        "due_soon_total": round(sum(i["outstanding"] for i in due_soon), 2), "due_soon_count": len(due_soon),
        "later_total": round(later, 2),
        "overdue": sorted(overdue, key=lambda i: -i["days_overdue"])[:25],
        "due_soon": due_soon[:25],
    }


GROUPS = {"customer": "customer", "customer_group": "customer_group", "territory": "territory",
          "company": "company", "month": "posting_date", "sales_partner": "sales_partner"}


@tool("sales_summary", "Sales summary",
      "Net sales from submitted Sales Invoices for a period, grouped, with the previous equal period for comparison. "
      "period: this_month, last_month, this_quarter, last_quarter, ytd, last_year, last_N_days or custom.",
      {"period": S, "group_by": {"type": "string", "enum": list(GROUPS)}, "company": S,
       "from_date": S, "to_date": S, "limit": I}, category="Finance")
def sales_summary(period="this_month", group_by="customer", company=None, from_date=None, to_date=None, limit=15):
    ensure_doctype("Sales Invoice")
    companies = company_filter(company)
    start, end = period_range(period, from_date, to_date)
    field = GROUPS.get(group_by or "customer", "customer")

    def fetch(s, e):
        return frappe.get_list("Sales Invoice",
                               filters={"docstatus": 1, "company": ["in", companies],
                                        "posting_date": ["between", [s, e]]},
                               fields=[field, "base_net_total"], limit_page_length=100000)

    rows = fetch(start, end)
    groups = defaultdict(float)
    for r in rows:
        key = r.get(field)
        if group_by == "month":
            key = getdate(key).strftime("%Y-%m")
        groups[key or "(blank)"] += flt(r.base_net_total)
    total = sum(groups.values())
    p_start, p_end = _previous_range(start, end)
    prev_total = sum(flt(r.base_net_total) for r in fetch(p_start, p_end))
    ordered = sorted(groups.items(), key=(lambda kv: kv[0]) if group_by == "month" else (lambda kv: -kv[1]))
    currency = frappe.db.get_value("Company", companies[0], "default_currency") if companies else None
    return {
        "period": {"from": str(start), "to": str(end)},
        "previous_period": {"from": str(p_start), "to": str(p_end), "net_sales": round(prev_total, 2)},
        "net_sales": round(total, 2), "invoices": len(rows), "currency": currency,
        "growth_pct": round((total - prev_total) / prev_total * 100, 1) if prev_total else None,
        "groups": [{"group": k, "net_sales": round(v, 2), "share_pct": round(v / total * 100, 1) if total else 0}
                   for k, v in ordered[: max(1, min(cint(limit) or 15, 100))]],
        "basis": "Net total in company currency, before VAT.",
    }


@tool("sales_by_item", "Top items sold",
      "Top items by net amount (or quantity) from submitted Sales Invoices in a period.",
      {"period": S, "company": S, "from_date": S, "to_date": S,
       "rank_by": {"type": "string", "enum": ["amount", "qty"]}, "limit": I}, category="Finance")
def sales_by_item(period="this_month", company=None, from_date=None, to_date=None, rank_by="amount", limit=15):
    ensure_doctype("Sales Invoice")
    companies = company_filter(company)
    if not companies:
        return {"items": []}
    start, end = period_range(period, from_date, to_date)
    order = "qty" if rank_by == "qty" else "amount"
    rows = frappe.db.sql(f"""
        select sii.item_code, max(sii.item_name) item_name, max(sii.item_group) item_group,
               sum(sii.stock_qty) qty, sum(sii.base_net_amount) amount
        from `tabSales Invoice Item` sii join `tabSales Invoice` si on si.name = sii.parent
        where si.docstatus = 1 and si.company in %(companies)s and si.posting_date between %(s)s and %(e)s
        group by sii.item_code order by {order} desc limit %(limit)s
    """, {"companies": tuple(companies), "s": start, "e": end, "limit": max(1, min(cint(limit) or 15, 100))},
        as_dict=True)
    return {"period": {"from": str(start), "to": str(end)},
            "items": [{"item_code": r.item_code, "item_name": r.item_name, "item_group": r.item_group,
                       "qty": flt(r.qty, 3), "net_amount": flt(r.amount, 2)} for r in rows]}


@tool("cash_position", "Cash and bank balances",
      "Current balance of every Cash and Bank account, from the General Ledger.",
      {"company": S}, category="Finance")
def cash_position(company=None):
    ensure_doctype("GL Entry")
    companies = company_filter(company)
    accounts = frappe.get_list("Account", filters={"account_type": ["in", ["Bank", "Cash"]], "is_group": 0,
                                                   "company": ["in", companies]},
                               fields=["name", "account_type", "account_currency", "company"], limit_page_length=500)
    if not accounts:
        return {"accounts": [], "note": "No Cash or Bank accounts found."}
    sums = frappe.db.sql("""
        select account, sum(debit) - sum(credit) balance,
               sum(debit_in_account_currency) - sum(credit_in_account_currency) balance_ac
        from `tabGL Entry` where is_cancelled = 0 and account in %(acc)s group by account
    """, {"acc": tuple(a.name for a in accounts)}, as_dict=True)
    by = {s.account: s for s in sums}
    out = []
    for a in accounts:
        s = by.get(a.name)
        out.append({"account": a.name, "type": a.account_type, "company": a.company,
                    "currency": a.account_currency,
                    "balance": flt(s.balance_ac if s else 0, 2), "balance_company_currency": flt(s.balance if s else 0, 2)})
    out.sort(key=lambda r: -r["balance_company_currency"])
    return {"as_on": nowdate(), "accounts": out,
            "total_company_currency": round(sum(r["balance_company_currency"] for r in out), 2)}
