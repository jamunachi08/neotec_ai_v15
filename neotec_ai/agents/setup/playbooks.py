# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Starter packs. Plain data (no Frappe import) so verify_tree.py can check it.

Every playbook only uses tools its coworker is granted in seed.py; verify_tree.py enforces that.
"""

PACKS = {
    "Finance Pack": ("حزمة المالية",
                     "Receivables, payables, cash and sales, with a morning brief that ranks what needs attention.",
                     "الذمم والمدفوعات والنقد والمبيعات مع موجز صباحي يرتب الأولويات."),
    "Operations Pack": ("حزمة العمليات",
                        "Overdue orders, expiring quotations, low stock, overdue follow-ups and purchase invoice matching.",
                        "الطلبات المتأخرة وعروض الأسعار المنتهية ونقص المخزون والمتابعات ومطابقة فواتير الشراء."),
    "KSA Compliance Pack": ("حزمة الامتثال السعودي",
                            "E-invoice readiness, supplier VAT and IBAN hygiene, and employee document expiry.",
                            "جاهزية الفوترة الإلكترونية وسلامة بيانات الموردين وانتهاء وثائق الموظفين."),
}

# name: dict(pack, title_ar, category, coworker, description, description_ar, parameter_label, default_parameter,
#            parameter_help, instructions, required_tools, silent, severity, dedupe_days, previous,
#            optional max_steps / max_tool_calls)
PLAYBOOKS = {
    "Receivables Watch": dict(
        pack="Finance Pack", title_ar="مراقبة الذمم المدينة", category="Finance", coworker="Finance Analyst",
        description="Customers drifting into 90+ days overdue and customer concentration risk.",
        description_ar="العملاء المتأخرون أكثر من 90 يوماً ومخاطر التركّز.",
        parameter_label="Minimum overdue amount", default_parameter="10000",
        parameter_help="Customers with less than this overdue are ignored.",
        instructions=(
            "Call receivables_aging for all companies.\n"
            "Findings:\n"
            "1. Each customer with more than {parameter} in the 91-180 or 180+ buckets. Key: ar90:<customer>.\n"
            "2. Any single customer above 25% of total outstanding. Key: arconc:<customer>.\n"
            "3. Overdue share of total above 40%. Key: aroverdue:<YYYY-MM>.\n"
            "Show a table: customer, 91-180, 180+, total, share of total. Then two lines on what changed since "
            "the previous result. Severity: critical if any customer has more than 180 days overdue above "
            "{parameter}; warn for other findings."),
        required_tools="receivables_aging, render_ui", silent=1, severity="warn", dedupe_days=7, previous=1),
    "Payables Due Soon": dict(
        pack="Finance Pack", title_ar="المستحقات للموردين قريباً", category="Finance", coworker="Finance Analyst",
        description="Supplier invoices falling due, grouped by week, with the largest payments first.",
        description_ar="فواتير الموردين المستحقة مجمعة أسبوعياً.",
        parameter_label="Days ahead", default_parameter="14",
        instructions=(
            "Call payables_due with days_ahead={parameter}. Report the total due, the total already overdue, "
            "and the ten largest items as a table (supplier, invoice, due date, amount). Mention suppliers that "
            "appear more than three times. Severity: warn if anything is already overdue, otherwise info."),
        required_tools="payables_due, render_ui", silent=0, severity="info", dedupe_days=0, previous=0),
    "Cash Position Brief": dict(
        pack="Finance Pack", title_ar="موجز السيولة", category="Finance", coworker="Finance Analyst",
        description="Cash and bank balances with the movement since the previous brief.",
        description_ar="أرصدة النقد والبنوك والتغير منذ الموجز السابق.",
        instructions=(
            "Call cash_position. Show KPI tiles: total cash, number of accounts, largest account. Compare with "
            "your previous result and state the change in amount and percent. Severity: warn if total cash "
            "fell more than 20% since the previous result, otherwise info."),
        required_tools="cash_position, render_ui", silent=0, severity="info", dedupe_days=0, previous=1),
    "Sales Pulse": dict(
        pack="Finance Pack", title_ar="نبض المبيعات", category="Sales", coworker="Finance Analyst",
        description="Sales for the period against the previous period, with top items and customers.",
        description_ar="المبيعات مقارنة بالفترة السابقة مع أعلى الأصناف والعملاء.",
        parameter_label="Period", default_parameter="this week",
        parameter_help="e.g. this week, last month, this quarter.",
        instructions=(
            "Call sales_summary for {parameter} grouped by customer, and sales_by_item for the same period. "
            "Show KPI tiles (net sales, change vs previous period, invoices) and a top-5 table for customers and "
            "items. Severity: warn if net sales fell more than 15% against the previous period, success if they "
            "grew more than 15%, otherwise info."),
        required_tools="sales_summary, sales_by_item, render_ui", silent=0, severity="info", dedupe_days=0,
        previous=0),
    "Priority Brief": dict(
        pack="Finance Pack", title_ar="موجز الأولويات", category="General", coworker="General Assistant",
        description="Reads the results of the earlier chain steps and ranks the three things to act on today.",
        description_ar="يقرأ نتائج الخطوات السابقة ويرتب أهم ثلاثة أمور اليوم.",
        instructions=(
            "Use only the results from the earlier chain steps; do not fetch the same data again. Rank the three "
            "things that most need a decision today. For each: what, why now, who should act, and the figure "
            "behind it. Then one line per remaining step: 'no change' or the change. If no step found anything, "
            "reply NOTHING_TO_REPORT. Severity: the highest severity that applies to your top item."),
        required_tools="render_ui", silent=1, severity="info", dedupe_days=0, previous=0),

    "Overdue Sales Orders": dict(
        pack="Operations Pack", title_ar="أوامر البيع المتأخرة", category="Sales", coworker="General Assistant",
        description="Submitted sales orders past their delivery date and not yet delivered.",
        description_ar="أوامر البيع المعتمدة التي تجاوزت تاريخ التسليم.",
        instructions=(
            "Use search_documents on Sales Order with filters docstatus=1, status in ['To Deliver and Bill', "
            "'To Deliver'] and delivery_date < {today}; fields name, customer, delivery_date, grand_total, "
            "per_delivered; order_by delivery_date asc; limit 50. Key: so:<name>. Table: order, customer, "
            "delivery date, days late, value, % delivered. Severity: critical if any order is more than 14 days "
            "late, warn otherwise."),
        required_tools="search_documents, render_ui", silent=1, severity="warn", dedupe_days=3, previous=0),
    "Expiring Quotations": dict(
        pack="Operations Pack", title_ar="عروض الأسعار قاربت الانتهاء", category="Sales", coworker="Sales Assistant",
        description="Open quotations whose validity ends soon, so sales can follow up in time.",
        description_ar="عروض الأسعار المفتوحة التي تنتهي صلاحيتها قريباً.",
        parameter_label="Days ahead", default_parameter="7",
        instructions=(
            "Use search_documents on Quotation with filters docstatus=1, status='Open' and valid_till between "
            "{today} and {parameter} days from today; fields name, party_name, valid_till, grand_total, owner. "
            "Key: qtn:<name>. Table: quotation, customer, valid till, value, prepared by. Suggest who should "
            "call whom, largest first. Severity: warn."),
        required_tools="search_documents, render_ui", silent=1, severity="warn", dedupe_days=3, previous=0),
    "Low Stock Radar": dict(
        pack="Operations Pack", title_ar="رادار نقص المخزون", category="Stock", coworker="Inventory Watch",
        description="Items below re-order level or projected negative, with suggested quantities.",
        description_ar="الأصناف تحت حد إعادة الطلب مع الكميات المقترحة.",
        parameter_label="Warehouse", default_parameter="", parameter_help="Empty = all warehouses.",
        instructions=(
            "Call low_stock (warehouse: {parameter} if given). Key: low:<item_code>@<warehouse>. Table: item, "
            "warehouse, projected qty, re-order level, shortfall, suggested qty. Severity: critical if any "
            "projected quantity is below zero, warn otherwise."),
        required_tools="low_stock, render_ui", silent=1, severity="warn", dedupe_days=2, previous=0),
    "Overdue Follow-ups": dict(
        pack="Operations Pack", title_ar="المتابعات المتأخرة", category="Operations", coworker="General Assistant",
        description="Your open assignments past their date, oldest first.",
        description_ar="المهام المسندة إليك والمتأخرة عن موعدها.",
        instructions=(
            "Call current_user. Then search_documents on ToDo with filters status='Open', allocated_to=<that "
            "user> and date < {today}; fields name, reference_type, reference_name, description, date, "
            "priority; order_by date asc; limit 40. Key: todo:<name>. Group by document type. Severity: warn if "
            "any is older than 7 days, otherwise info."),
        required_tools="current_user, search_documents, render_ui", silent=1, severity="info", dedupe_days=1,
        previous=0),
    "Purchase Invoice Match": dict(
        pack="Operations Pack", title_ar="مطابقة فاتورة الشراء", category="Procurement",
        coworker="Procurement Checker",
        description="Three-way match of one purchase invoice against its order and receipt, plus VAT checks.",
        description_ar="مطابقة ثلاثية لفاتورة شراء مع أمر الشراء والاستلام.",
        parameter_label="Purchase Invoice", parameter_help="The invoice number, e.g. ACC-PINV-2026-00012.",
        instructions=(
            "Open Purchase Invoice {parameter} with get_document. For each item, open the linked Purchase Order "
            "and Purchase Receipt and compare quantity and rate. Check the supplier VAT number with "
            "ksa_validate_vat_number and run ksa_invoice_check on the invoice. Report only differences: item, "
            "invoice qty/rate, order qty/rate, received qty, difference. If everything matches and all checks "
            "pass, reply NOTHING_TO_REPORT. Severity: critical if invoiced quantity exceeds received quantity "
            "or the rate is higher than ordered; warn for other differences."),
        required_tools="get_document, search_documents, ksa_validate_vat_number, ksa_invoice_check, render_ui",
        silent=1, severity="warn", dedupe_days=0, previous=0, max_steps=10, max_tool_calls=24),

    "E-Invoice Readiness Sweep": dict(
        pack="KSA Compliance Pack", title_ar="فحص جاهزية الفوترة الإلكترونية", category="Compliance",
        coworker="Finance Analyst",
        description="Checks yesterday's submitted sales invoices for common e-invoicing problems.",
        description_ar="يفحص فواتير المبيعات المعتمدة أمس بحثاً عن مشكلات الفوترة الإلكترونية.",
        parameter_label="Posting date", default_parameter="yesterday",
        instructions=(
            "Find submitted Sales Invoices posted on {parameter} (search_documents, docstatus=1, limit 30, "
            "newest first). Run ksa_invoice_check on each. Key: einv:<invoice>:<check>. Table of failed checks "
            "only: invoice, customer, check, detail. Say how many invoices passed. Severity: critical if a "
            "buyer VAT number or the seller VAT number fails, warn otherwise."),
        required_tools="search_documents, ksa_invoice_check, render_ui", silent=1, severity="warn",
        dedupe_days=14, previous=0, max_steps=12, max_tool_calls=45),
    "Supplier Master Hygiene": dict(
        pack="KSA Compliance Pack", title_ar="سلامة بيانات الموردين", category="Compliance",
        coworker="Procurement Checker",
        description="Active Saudi suppliers with a missing or invalid VAT number.",
        description_ar="الموردون السعوديون النشطون بأرقام ضريبية مفقودة أو غير صحيحة.",
        instructions=(
            "search_documents on Supplier with filters disabled=0 and country='Saudi Arabia'; fields name, "
            "supplier_name, tax_id, supplier_type; limit 60. Suppliers without tax_id are findings on their own; "
            "check every other tax_id with ksa_validate_vat_number. "
            "Key: sup:<name>:vat. Table: supplier, VAT number, problem. Severity: warn."),
        required_tools="search_documents, ksa_validate_vat_number, render_ui", silent=1, severity="warn",
        dedupe_days=30, previous=0, max_steps=12, max_tool_calls=70),
    "Employee Document Expiry": dict(
        pack="KSA Compliance Pack", title_ar="انتهاء وثائق الموظفين", category="HR",
        coworker="HR & Labor Law Advisor",
        description="Active employees whose document expiry date falls within the next 60 days.",
        description_ar="الموظفون الذين تنتهي وثائقهم خلال 60 يوماً.",
        parameter_label="Expiry date field", default_parameter="valid_upto",
        parameter_help="Fieldname on Employee, e.g. valid_upto (passport) or a custom Iqama expiry field.",
        instructions=(
            "search_documents on Employee with filters status='Active' and {parameter} between {today} and 60 "
            "days from today; fields name, employee_name, department, {parameter}; limit 100. Key: "
            "doc:<employee>:{parameter}. Table: employee, name, department, expiry date, days left. Severity: "
            "critical if any expires within 14 days, warn otherwise. Employee records are sensitive: in Guarded "
            "residency this playbook needs an in-Kingdom or on-premises provider."),
        required_tools="search_documents, render_ui", silent=1, severity="warn", dedupe_days=7, previous=0),
}

CHAINS = {
    "Morning Finance Brief": dict(
        description="Receivables, payables, cash and sales, then one ranked brief. Schedule it with a routine "
                    "(target: Chain) for 07:00 on working days.",
        steps=[("Receivables Watch", "", 1, 0), ("Payables Due Soon", "", 1, 0), ("Cash Position Brief", "", 1, 0),
               ("Sales Pulse", "", 1, 0), ("Priority Brief", "", 1, 1)],
    ),
}

TRIGGERS = {
    "Match purchase invoices on submit": dict(
        document_type="Purchase Invoice", event="On Submit", playbook="Purchase Invoice Match",
        parameter_template="{name}", run_as="Document Owner", cooldown_minutes=60, condition="",
    ),
}

CHANNELS = {
    "Bell (run owner)": dict(channel_type="Bell", min_severity="info"),
}
