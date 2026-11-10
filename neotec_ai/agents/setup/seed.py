# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Idempotent seeders. Safe on every migrate: they create what is missing and never overwrite an
administrator's changes (except tool metadata, which follows the code)."""

from __future__ import annotations

import json

import frappe

ROLES = {
    "Coworker User": "Can chat with coworkers they are allowed to use.",
    "Coworker Approver": "Can approve or reject actions coworkers request.",
    "Coworker Admin": "Configures providers, coworkers, policies and reads the audit trail.",
}

SENSITIVE = ["Employee", "Salary Slip", "Salary Structure Assignment", "Payroll Entry", "Additional Salary",
             "Employee Grievance", "Employee Separation", "Bank Account", "Contact"]

READ_CORE = ["describe_doctype", "search_documents", "get_document", "count_documents", "aggregate",
             "global_search", "current_user", "render_ui", "remember_fact", "approval_status"]

# name: (title, title_ar, icon, colour, description, description_ar, instructions, starters, tools{name: mode})
COWORKERS = {
    "General Assistant": (
        "General Assistant", "المساعد العام", "🧭", "#0F6E66",
        "Finds records, answers questions about ERPNext data and sets up follow-ups.",
        "يبحث في السجلات ويجيب عن أسئلة بيانات النظام ويُنشئ المتابعات.",
        "Help with any everyday ERPNext question. Prefer search_documents and aggregate. "
        "When a request belongs to finance, stock or HR, answer it but mention the specialist coworker.",
        "Which sales orders are overdue for delivery?\nShow open quotations above 50,000\nWho are my top 10 customers this year?\nلخص لي فواتير المبيعات غير المدفوعة",
        {**{t: "Default" for t in READ_CORE}, "list_reports": "Default", "run_report": "Default",
         "search_knowledge": "Default", "add_comment": "Default", "create_todo": "Default", "notify_user": "Auto",
         "list_playbooks": "Default", "run_playbook": "Default", "get_run": "Default"},
    ),
    "Finance Analyst": (
        "Finance Analyst", "المحلل المالي", "📊", "#1D4E89",
        "Receivables, payables, cash, sales performance and VAT, with the arithmetic done by tools.",
        "الذمم المدينة والدائنة والنقد وأداء المبيعات وضريبة القيمة المضافة.",
        "Use receivables_aging, payables_due, cash_position, sales_summary and sales_by_item before any generic "
        "search. Always state the period and the basis (net of VAT, company currency). Highlight risk: overdue "
        "above 90 days, concentration above 25% in one customer, negative growth. Present numbers with render_ui.",
        "Receivables aging with the riskiest customers\nCash position across all banks\nSales this quarter vs last quarter\nما المبالغ المستحقة للموردين خلال 30 يوماً؟",
        {**{t: "Default" for t in READ_CORE}, "receivables_aging": "Default", "payables_due": "Default",
         "sales_summary": "Default", "sales_by_item": "Default", "cash_position": "Default",
         "list_reports": "Default", "run_report": "Default", "ksa_vat": "Default", "ksa_invoice_check": "Default",
         "add_comment": "Default", "notify_user": "Auto"},
    ),
    "Sales Assistant": (
        "Sales Assistant", "مساعد المبيعات", "🤝", "#7A3E9D",
        "Pipeline, quotations and customer follow-ups; drafts quotations and e-mails for your approval.",
        "متابعة العملاء وعروض الأسعار وصياغة المسودات للاعتماد.",
        "Help sales staff follow up. Draft quotations with create_draft_document (never submit). "
        "Before drafting, confirm customer, items, quantities and validity. For e-mails, show the draft text first.",
        "Quotations expiring this week\nDraft a quotation for customer X\nWhich customers have not ordered in 90 days?\nأعد مسودة رسالة متابعة لعميل",
        {**{t: "Default" for t in READ_CORE}, "sales_summary": "Default", "receivables_aging": "Default",
         "create_draft_document": "Ask", "update_draft_document": "Ask", "add_comment": "Default",
         "create_todo": "Default", "send_email": "Ask", "notify_user": "Auto"},
    ),
    "Procurement Checker": (
        "Procurement Checker", "مدقق المشتريات", "🧾", "#8A5A00",
        "Checks purchase invoices against orders and receipts, supplier VAT numbers and IBANs.",
        "يطابق فواتير الشراء مع أوامر الشراء والاستلام ويتحقق من الأرقام الضريبية والآيبان.",
        "For a Purchase Invoice do a three-way match: compare item quantities and rates with the Purchase Order "
        "and Purchase Receipt (open each with get_document). Report differences as a table. Check the supplier "
        "VAT number with ksa_validate_vat_number and any IBAN with ksa_validate_iban. Never approve payment; "
        "list what a person must decide.",
        "Check purchase invoice ACC-PINV-…\nSupplier invoices due in the next 14 days\nValidate this IBAN: SA…",
        {**{t: "Default" for t in READ_CORE}, "payables_due": "Default", "ksa_validate_vat_number": "Default",
         "ksa_validate_iban": "Default", "ksa_vat": "Default", "ksa_invoice_check": "Default",
         "add_comment": "Default", "create_todo": "Default"},
    ),
    "HR & Labor Law Advisor": (
        "HR & Labor Law Advisor", "مستشار الموارد البشرية ونظام العمل", "⚖️", "#5B6B2F",
        "End-of-service calculations and HR policy answers under the Saudi Labor Law.",
        "حساب مكافأة نهاية الخدمة والإجابة عن سياسات الموارد البشرية وفق نظام العمل السعودي.",
        "Answer HR questions from the knowledge base and use ksa_end_of_service for awards. Always show the "
        "rule applied and the disclaimer. Employee records are sensitive: only open them when needed.",
        "End-of-service for 7 years at 12,000 SAR, resignation\nWhat does our leave policy say about Hajj leave?\nاحسب مكافأة نهاية الخدمة لموظف خدم 4 سنوات",
        {"search_knowledge": "Default", "ksa_end_of_service": "Default", "render_ui": "Default",
         "current_user": "Default", "search_documents": "Default", "get_document": "Default",
         "remember_fact": "Default"},
    ),
    "Inventory Watch": (
        "Inventory Watch", "مراقب المخزون", "📦", "#2F7D4F",
        "Stock levels, shortages against re-order levels and slow movers.",
        "مستويات المخزون والنواقص مقابل حد إعادة الطلب.",
        "Use stock_levels and low_stock. When flagging shortages, include the suggested quantity and warehouse. "
        "Offer to notify the purchasing user.",
        "What is below re-order level?\nStock of item X in all warehouses\nأين يوجد نقص في المستودع الرئيسي؟",
        {**{t: "Default" for t in READ_CORE}, "stock_levels": "Default", "low_stock": "Default",
         "notify_user": "Auto", "create_draft_document": "Ask"},
    ),
    "Knowledge Desk": (
        "Knowledge Desk", "مكتب المعرفة", "📚", "#3A5A7A",
        "Answers questions from company policies and manuals, with sources.",
        "يجيب من سياسات الشركة وأدلتها مع ذكر المصدر.",
        "Answer only from search_knowledge results and name the source title for each point. If nothing "
        "relevant is found, say so and suggest who to ask.",
        "What is the travel allowance policy?\nHow do we onboard a new supplier?\nما سياسة الإجازات؟",
        {"search_knowledge": "Default", "render_ui": "Default", "remember_fact": "Default"},
    ),
    "MCP Gateway": (
        "MCP Gateway", "بوابة MCP", "🔌", "#444444",
        "Service coworker whose grants define what external AI clients may do through the MCP endpoint.",
        "تحدد صلاحيات أدوات عملاء الذكاء الاصطناعي الخارجيين.",
        "", "",
        {**{t: "Default" for t in READ_CORE if t not in ("render_ui", "remember_fact")},
         "receivables_aging": "Default", "payables_due": "Default", "sales_summary": "Default",
         "stock_levels": "Default", "search_knowledge": "Default", "create_draft_document": "Ask",
         "add_comment": "Ask", "list_playbooks": "Default", "run_playbook": "Ask", "get_run": "Default"},
    ),
}

POLICIES = [
    {"rule_title": "Never submit documents", "effect": "Deny", "tool_pattern": "submit_document", "priority": 1,
     "message": "Coworkers prepare drafts; a person submits them in ERPNext."},
    {"rule_title": "Routines cannot change data", "effect": "Deny", "tool_pattern": "*", "initiator": "Routine",
     "condition": "is_write and tool != 'notify_user'", "priority": 2,
     "message": "Scheduled routines may read and notify, not change data."},
    {"rule_title": "No changes to sensitive HR records", "effect": "Deny", "tool_pattern": "*_draft_document",
     "condition": "doctype in ('Employee', 'Salary Slip', 'Salary Structure Assignment', 'Payroll Entry', 'Additional Salary')",
     "priority": 3, "message": "HR and payroll records are changed by HR in ERPNext, not by coworkers."},
    {"rule_title": "External e-mail needs an approver", "effect": "Require Approval", "tool_pattern": "send_email",
     "approver_role": "Coworker Approver", "priority": 5,
     "message": "E-mails leaving the company need a Coworker Approver."},
    {"rule_title": "Payments and journals need finance approval", "effect": "Require Approval",
     "tool_pattern": "*_draft_document", "approver_role": "Accounts Manager", "priority": 6,
     "condition": "doctype in ('Payment Entry', 'Journal Entry', 'Payment Request')",
     "message": "Draft payments and journals need an Accounts Manager."},
    {"rule_title": "MCP clients ask before any change", "effect": "Require Approval", "tool_pattern": "*",
     "initiator": "MCP", "condition": "is_write", "priority": 7,
     "message": "Changes requested by an external AI client need confirmation in ERPNext."},
    {"rule_title": "Notifications run without asking", "effect": "Allow", "tool_pattern": "notify_user",
     "priority": 20},
]


def ensure_roles():
    for role, desc in ROLES.items():
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1,
                            "description": desc}).insert(ignore_permissions=True)


def sync_tool_registry():
    from neotec_ai.agents.engine import registry

    tools = registry.all_tools()
    for name, spec in tools.items():
        values = {
            "label": spec["label"][:140], "category": spec["category"], "description": spec["description"],
            "source": spec["source"], "parameters_schema": json.dumps(spec["schema"], indent=1, ensure_ascii=False),
        }
        if frappe.db.exists("Coworker Tool", name):
            frappe.db.set_value("Coworker Tool", name, values, update_modified=False)
        else:
            frappe.get_doc({"doctype": "Coworker Tool", "tool_name": name, "enabled": 1,
                            "is_write": 1 if spec["is_write"] else 0, "risk_level": spec.get("risk") or "Low",
                            **values}).insert(ignore_permissions=True)
    for stale in frappe.get_all("Coworker Tool", filters={"source": ["in", ["Extension", "MCP"]]}, pluck="name"):
        if stale not in tools:
            frappe.db.set_value("Coworker Tool", stale, "enabled", 0, update_modified=False)
    return len(tools)


def ensure_settings():
    s = frappe.get_single("Coworker Settings")
    changed = False
    defaults = {"residency_mode": "Guarded", "max_steps": 8, "max_tool_calls": 12, "history_window": 30,
                "tool_result_char_limit": 12000, "approval_expiry_hours": 72, "max_routines_per_user": 20,
                "max_routine_failures": 5, "mcp_endpoint": "/api/method/neotec_ai.agents.mcp.server.handle"}
    for k, v in defaults.items():
        if not s.get(k):
            s.set(k, v)
            changed = True
    if not s.sensitive_doctypes:
        for dt in SENSITIVE:
            if frappe.db.exists("DocType", dt):
                s.append("sensitive_doctypes", {"document_type": dt})
                changed = True
    if not s.mcp_coworker and frappe.db.exists("AI Coworker", "MCP Gateway"):
        s.mcp_coworker = "MCP Gateway"
        changed = True
    if changed:
        s.flags.ignore_mandatory = True
        s.save(ignore_permissions=True)


def ensure_policies():
    for rule in POLICIES:
        if frappe.db.exists("Coworker Policy Rule", rule["rule_title"]):
            continue
        role = rule.get("approver_role")
        if role and not frappe.db.exists("Role", role):
            rule = {**rule, "approver_role": "Coworker Approver"}
        frappe.get_doc({"doctype": "Coworker Policy Rule", "enabled": 1, "initiator": rule.get("initiator", "Any"),
                        **rule}).insert(ignore_permissions=True)


def ensure_coworkers():
    existing_tools = set(frappe.get_all("Coworker Tool", pluck="name"))
    for name, (title, title_ar, icon, color, desc, desc_ar, instr, starters, tools) in COWORKERS.items():
        if frappe.db.exists("AI Coworker", name):
            continue
        doc = frappe.get_doc({
            "doctype": "AI Coworker", "coworker_name": name, "title": title, "title_ar": title_ar, "icon": icon,
            "color": color, "description": desc, "description_ar": desc_ar, "instructions": instr,
            "starter_prompts": starters, "enabled": 1, "use_knowledge": 1, "use_memory": 1,
            "chat_visible": 0 if name == "MCP Gateway" else 1,
        })
        for tool, mode in tools.items():
            if tool in existing_tools:
                doc.append("tools", {"tool": tool, "mode": mode})
        doc.insert(ignore_permissions=True)


def ensure_automation_settings():
    s = frappe.get_single("Coworker Settings")
    defaults = {"failures_before_issue": 3, "low_score_threshold": 2, "run_retention_days": 90}
    changed = False
    for k, v in defaults.items():
        if s.meta.has_field(k) and s.get(k) in (None, ""):
            s.set(k, v)
            changed = True
    if changed:
        s.flags.ignore_mandatory = True
        s.save(ignore_permissions=True)


def ensure_starter_packs():
    """Packs, playbooks, a chain, a (disabled) trigger and a bell channel. Created once; never overwritten."""
    from neotec_ai.agents.setup import playbooks as data

    for name, (title_ar, desc, desc_ar) in data.PACKS.items():
        if not frappe.db.exists("Coworker Pack", name):
            frappe.get_doc({"doctype": "Coworker Pack", "pack_name": name, "title_ar": title_ar, "enabled": 1,
                            "is_standard": 1, "description": desc, "description_ar": desc_ar}
                           ).insert(ignore_permissions=True)

    for name, ch in data.CHANNELS.items():
        if not frappe.db.exists("Coworker Channel", name):
            frappe.get_doc({"doctype": "Coworker Channel", "channel_name": name, "enabled": 1, **ch}
                           ).insert(ignore_permissions=True)

    for name, p in data.PLAYBOOKS.items():
        if frappe.db.exists("Coworker Playbook", name) or not frappe.db.exists("AI Coworker", p["coworker"]):
            continue
        doc = frappe.get_doc({
            "doctype": "Coworker Playbook", "playbook_name": name, "title_ar": p["title_ar"], "enabled": 1,
            "is_standard": 1, "pack": p["pack"], "category": p["category"], "coworker": p["coworker"],
            "mode": "Read Only", "description": p["description"], "description_ar": p["description_ar"],
            "parameter_label": p.get("parameter_label"), "default_parameter": p.get("default_parameter"),
            "parameter_help": p.get("parameter_help"), "instructions": p["instructions"],
            "required_tools": p["required_tools"], "silent_when_empty": p["silent"],
            "default_severity": p["severity"], "dedupe_days": p["dedupe_days"],
            "include_previous_output": p["previous"], "max_steps": p.get("max_steps"),
            "max_tool_calls": p.get("max_tool_calls"),
        })
        doc.flags.ignore_validate = True  # coworker grants are checked by the health job, not at install
        doc.insert(ignore_permissions=True)

    for name, c in data.CHAINS.items():
        if frappe.db.exists("Coworker Chain", name):
            continue
        if not all(frappe.db.exists("Coworker Playbook", st[0]) for st in c["steps"]):
            continue
        doc = frappe.get_doc({"doctype": "Coworker Chain", "chain_name": name, "enabled": 1, "is_standard": 1,
                              "on_error": "Continue", "description": c["description"]})
        for playbook, param, use_prev, deliver in c["steps"]:
            doc.append("steps", {"playbook": playbook, "parameter": param, "use_previous": use_prev,
                                 "deliver": deliver})
        doc.insert(ignore_permissions=True)

    for name, t in data.TRIGGERS.items():
        if frappe.db.exists("Coworker Trigger", name) or not frappe.db.exists("DocType", t["document_type"]):
            continue
        if not frappe.db.exists("Coworker Playbook", t["playbook"]):
            continue
        doc = frappe.get_doc({"doctype": "Coworker Trigger", "trigger_name": name, "enabled": 0, **t})
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True)


def run():
    ensure_roles()
    sync_tool_registry()
    ensure_policies()
    ensure_coworkers()
    ensure_settings()
    ensure_automation_settings()
    ensure_starter_packs()
    frappe.db.commit()
