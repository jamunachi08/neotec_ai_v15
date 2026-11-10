"""Install / migrate hooks: access role, settings defaults, starter Data Dictionary and sample questions."""

import frappe

AI_ROLE = "Neotec AI User"

# Starter Data Dictionary. Only DocTypes (and fields) that exist on the site are created,
# so this is safe on plain Frappe as well as ERPNext / HRMS sites. Field meanings are filled
# from neotec_ai.field_meanings. Keys: description, fields, parent (child tables),
# enabled (default 1), submitted_only (default: 1 if submittable), sample_questions.
SEED_SOURCES = {
    # ---------------- Selling / CRM ----------------
    "Customer": {
        "description": "Customers the business sells to. customer_group and territory classify them. disabled = 1 means inactive.",
        "fields": ["name", "customer_name", "customer_type", "customer_group", "territory", "industry", "default_currency", "disabled", "creation"],
        "sample_questions": "How many active customers by customer group\nNew customers this month\nCustomers by territory",
    },
    "Sales Invoice": {
        "description": (
            "Customer invoices = revenue. Sum base_grand_total (incl. tax) or base_net_total (excl. tax) for revenue "
            "in company currency. outstanding_amount is what the customer still owes (receivables). "
            "is_return = 1 marks credit notes. Overdue = past due_date and outstanding_amount > 0."
        ),
        "fields": ["name", "customer", "customer_name", "customer_group", "territory", "company", "posting_date", "due_date", "currency",
                   "base_net_total", "grand_total", "base_grand_total", "outstanding_amount", "status", "is_return", "sales_partner", "project", "cost_center"],
        "sample_questions": "Revenue by month this year\nTop 10 customers by revenue this year\nOverdue invoices with amounts\nTotal receivables by customer",
    },
    "Sales Invoice Item": {
        "parent": "Sales Invoice",
        "description": "Line items of Sales Invoices; parent = invoice ID. Use for item-wise and item-group-wise sales. Sum base_net_amount for revenue per item.",
        "fields": ["parent", "item_code", "item_name", "item_group", "brand", "qty", "stock_qty", "uom", "rate", "base_net_amount", "base_amount", "warehouse"],
        "sample_questions": "Best-selling items by quantity this month\nRevenue by item group this year",
    },
    "Sales Order": {
        "description": "Confirmed customer orders (bookings). per_delivered / per_billed show fulfilment progress. Open orders: status not in Completed, Closed, Cancelled.",
        "fields": ["name", "customer", "customer_name", "territory", "company", "transaction_date", "delivery_date",
                   "base_grand_total", "status", "per_delivered", "per_billed"],
        "sample_questions": "Orders pending delivery\nOrder bookings by month",
    },
    "Sales Order Item": {
        "parent": "Sales Order",
        "description": "Line items of Sales Orders; parent = order ID. delivered_qty vs qty shows what is still to deliver.",
        "fields": ["parent", "item_code", "item_name", "item_group", "qty", "delivered_qty", "base_net_amount", "delivery_date", "warehouse"],
    },
    "Quotation": {
        "description": "Quotes sent to customers or leads. status Ordered = won (converted to sales order), Lost = lost. Use for win rate.",
        "fields": ["name", "quotation_to", "party_name", "customer_name", "transaction_date", "valid_till", "base_grand_total", "status", "order_lost_reason"],
        "sample_questions": "Quotation win rate this quarter\nOpen quotations expiring this week",
    },
    "Delivery Note": {
        "description": "Goods shipped to customers. status To Bill = delivered but not invoiced yet.",
        "fields": ["name", "customer", "customer_name", "posting_date", "base_grand_total", "status", "per_billed", "is_return"],
    },
    "Lead": {
        "description": "Sales leads / prospects. Count name for number of leads; group by source for lead-source analysis.",
        "fields": ["name", "lead_name", "company_name", "lead_owner", "status", "source", "territory", "industry", "creation"],
        "sample_questions": "Leads this month by source\nLeads per owner\nConversion: leads by status",
    },
    "Opportunity": {
        "description": "Sales pipeline deals. Sum opportunity_amount for pipeline value; status Converted = won, Lost = lost.",
        "fields": ["name", "opportunity_from", "party_name", "customer_name", "opportunity_type", "status", "sales_stage",
                   "opportunity_amount", "probability", "expected_closing", "opportunity_owner", "source", "transaction_date"],
        "sample_questions": "Pipeline value by sales stage\nOpportunities closing this month",
    },
    # ---------------- Buying ----------------
    "Supplier": {
        "description": "Suppliers / vendors the business buys from.",
        "fields": ["name", "supplier_name", "supplier_group", "supplier_type", "country", "disabled", "creation"],
    },
    "Purchase Invoice": {
        "description": "Supplier bills = purchase spend / payables. Sum base_grand_total for spend. outstanding_amount is what we still owe. is_return = 1 marks debit notes.",
        "fields": ["name", "supplier", "supplier_name", "company", "posting_date", "due_date", "bill_no", "base_net_total",
                   "base_grand_total", "outstanding_amount", "status", "is_return", "project", "cost_center"],
        "sample_questions": "Payables by supplier\nPurchase spend by month\nBills due this week",
    },
    "Purchase Invoice Item": {
        "parent": "Purchase Invoice",
        "description": "Line items of Purchase Invoices; parent = bill ID. Use for item-wise purchase spend and price history.",
        "fields": ["parent", "item_code", "item_name", "item_group", "qty", "rate", "base_net_amount", "warehouse", "expense_account"],
    },
    "Purchase Order": {
        "description": "Orders placed with suppliers. per_received / per_billed show progress. Open: status not in Completed, Closed, Cancelled.",
        "fields": ["name", "supplier", "supplier_name", "company", "transaction_date", "schedule_date", "base_grand_total",
                   "status", "per_received", "per_billed"],
        "sample_questions": "Purchase orders not yet received\nPO value by supplier this year",
    },
    "Purchase Order Item": {
        "parent": "Purchase Order",
        "description": "Line items of Purchase Orders; parent = PO ID. received_qty vs qty shows what is pending.",
        "fields": ["parent", "item_code", "item_name", "qty", "received_qty", "rate", "base_net_amount", "schedule_date", "warehouse"],
    },
    "Purchase Receipt": {
        "description": "Goods received from suppliers. status To Bill = received but not billed.",
        "fields": ["name", "supplier", "supplier_name", "posting_date", "base_grand_total", "status", "per_billed", "is_return"],
    },
    "Material Request": {
        "description": "Internal requests for material (to purchase, transfer, issue or manufacture).",
        "fields": ["name", "material_request_type", "transaction_date", "schedule_date", "status", "per_ordered", "company"],
    },
    # ---------------- Stock ----------------
    "Item": {
        "description": "Products and services master. is_stock_item = 1 means inventory is tracked. disabled = 1 means not in use.",
        "fields": ["name", "item_name", "item_group", "brand", "stock_uom", "is_stock_item", "is_fixed_asset", "valuation_rate",
                   "standard_rate", "disabled", "creation"],
    },
    "Bin": {
        "description": (
            "Current stock per item per warehouse (one row each). actual_qty = on hand; projected_qty includes ordered, "
            "planned and reserved quantities; stock_value = valuation in company currency."
        ),
        "fields": ["item_code", "warehouse", "actual_qty", "reserved_qty", "ordered_qty", "planned_qty", "projected_qty", "valuation_rate", "stock_value"],
        "submitted_only": 0,
        "sample_questions": "Stock value by warehouse\nItems out of stock\nItems with negative projected quantity",
    },
    "Stock Ledger Entry": {
        "description": "Every stock movement. actual_qty is the change (+in / -out). Filter is_cancelled = 0. Use for stock movement history.",
        "fields": ["item_code", "warehouse", "posting_date", "voucher_type", "voucher_no", "actual_qty", "qty_after_transaction",
                   "valuation_rate", "stock_value_difference", "is_cancelled"],
        "submitted_only": 0,
    },
    "Stock Entry": {
        "description": "Stock movements: receipts, issues, transfers, manufacturing. stock_entry_type says which.",
        "fields": ["name", "stock_entry_type", "purpose", "posting_date", "from_warehouse", "to_warehouse", "total_outgoing_value",
                   "total_incoming_value", "work_order", "company"],
    },
    "Warehouse": {
        "description": "Stock locations. is_group = 1 are folders, not real locations.",
        "fields": ["name", "warehouse_name", "is_group", "parent_warehouse", "company", "disabled"],
        "submitted_only": 0,
    },
    # ---------------- Accounts ----------------
    "Payment Entry": {
        "description": "Money received (payment_type = Receive, from customers) or paid (Pay, to suppliers). Sum base_paid_amount for amounts in company currency.",
        "fields": ["name", "payment_type", "party_type", "party", "party_name", "company", "posting_date", "paid_amount",
                   "base_paid_amount", "mode_of_payment", "reference_no"],
        "sample_questions": "Collections this month\nPayments made to suppliers this month",
    },
    "GL Entry": {
        "description": (
            "General ledger postings (company currency). Always filter is_cancelled = 0. Income = credit - debit on income accounts; "
            "expense = debit - credit on expense accounts. Join account to Account for root_type."
        ),
        "fields": ["posting_date", "account", "party_type", "party", "debit", "credit", "voucher_type", "voucher_no",
                   "cost_center", "project", "company", "is_cancelled"],
        "submitted_only": 0,
        "sample_questions": "Expenses by account this month\nBank balance movements this week",
    },
    "Account": {
        "description": "Chart of accounts. root_type: Asset, Liability, Equity, Income, Expense. is_group = 1 are headings.",
        "fields": ["name", "account_name", "root_type", "account_type", "parent_account", "is_group", "company", "account_currency"],
        "submitted_only": 0,
    },
    "Journal Entry": {
        "description": "Manual accounting entries (adjustments, opening balances, bank entries).",
        "fields": ["name", "voucher_type", "posting_date", "total_debit", "total_credit", "user_remark", "company"],
    },
    # ---------------- Manufacturing ----------------
    "Work Order": {
        "description": "Production orders. qty = planned, produced_qty = done.",
        "fields": ["name", "production_item", "item_name", "bom_no", "qty", "produced_qty", "status", "planned_start_date",
                   "expected_delivery_date", "fg_warehouse", "company"],
    },
    "BOM": {
        "description": "Bills of materials. is_active and is_default mark the BOM in use. total_cost = cost per quantity.",
        "fields": ["name", "item", "item_name", "quantity", "is_active", "is_default", "total_cost", "company"],
    },
    # ---------------- Projects / Support ----------------
    "Project": {
        "description": "Projects with planned vs actual cost and billing.",
        "fields": ["name", "project_name", "status", "customer", "percent_complete", "expected_start_date", "expected_end_date",
                   "estimated_costing", "total_costing_amount", "total_billed_amount", "company"],
        "submitted_only": 0,
    },
    "Task": {
        "description": "Project tasks. Overdue = exp_end_date in the past and status not Completed/Cancelled.",
        "fields": ["name", "subject", "project", "status", "priority", "exp_start_date", "exp_end_date", "progress", "completed_on"],
        "submitted_only": 0,
    },
    "Timesheet": {
        "description": "Time logged by employees. total_hours worked, total_billable_hours billable.",
        "fields": ["name", "employee", "employee_name", "start_date", "end_date", "total_hours", "total_billable_hours",
                   "total_billable_amount", "status", "customer"],
    },
    "Issue": {
        "description": "Support tickets. Open tickets: status Open or Replied.",
        "fields": ["name", "subject", "status", "priority", "issue_type", "customer", "raised_by", "opening_date", "resolution_date"],
        "submitted_only": 0,
    },
    # ---------------- Assets ----------------
    "Asset": {
        "description": "Fixed assets. gross_purchase_amount = cost, value_after_depreciation = current book value.",
        "fields": ["name", "asset_name", "item_code", "asset_category", "location", "status", "purchase_date",
                   "gross_purchase_amount", "value_after_depreciation", "company"],
    },
    # ---------------- HR (personal data: seeded disabled) ----------------
    "Employee": {
        "description": "Employees. Headcount = count with status Active. Personal data: seeded disabled; enable deliberately.",
        "fields": ["name", "employee_name", "department", "designation", "branch", "status", "gender", "date_of_joining", "relieving_date", "company"],
        "enabled": 0,
        "submitted_only": 0,
    },
    "Leave Application": {
        "description": "Leave requests. status Approved = taken / to be taken.",
        "fields": ["name", "employee", "employee_name", "leave_type", "from_date", "to_date", "total_leave_days", "status", "department"],
        "enabled": 0,
    },
    "Attendance": {
        "description": "Daily attendance. status Present, Absent, On Leave, Half Day, Work From Home.",
        "fields": ["name", "employee", "employee_name", "attendance_date", "status", "department"],
        "enabled": 0,
    },
    "Expense Claim": {
        "description": "Employee expense claims.",
        "fields": ["name", "employee", "employee_name", "posting_date", "total_claimed_amount", "total_sanctioned_amount", "status", "approval_status"],
        "enabled": 0,
    },
    "Salary Slip": {
        "description": "Monthly salary slips. Highly sensitive: seeded disabled.",
        "fields": ["name", "employee", "employee_name", "department", "start_date", "end_date", "gross_pay", "total_deduction", "net_pay", "status"],
        "enabled": 0,
    },
}


# Extra permissions for the AI role (added as Custom DocPerm so they survive app updates).
ROLE_PERMISSIONS = {
    "Neotec AI Report": {
        "read": 1, "write": 1, "create": 1, "delete": 1, "share": 1,
        "export": 1, "print": 1, "report": 1, "if_owner": 1,
    },
    "Neotec Sample Question": {"read": 1},
    "Neotec Dashboard": {
        "read": 1, "write": 1, "create": 1, "delete": 1, "share": 1,
        "export": 1, "print": 1, "report": 1, "if_owner": 1,
    },
    "Neotec Report Schedule": {"read": 1, "write": 1, "create": 1, "delete": 1, "if_owner": 1},
}

PAGES = ("neotec-bi", "neotec-dashboard")


def before_install():
    """Roles must exist before DocTypes and Pages that reference them are synced."""
    ensure_role()
    from neotec_ai.agents.setup.seed import ensure_roles

    ensure_roles()


def before_migrate():
    """Sites upgraded from 3.x get the coworker roles and module before the new DocTypes are synced."""
    try:
        before_install()
        from neotec_ai.agents.takeover import ensure_module_def

        ensure_module_def()
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="Neotec AI: before_migrate role setup failed")


def after_install():
    ensure_role()
    ensure_permissions()
    ensure_page_roles()
    init_settings()
    seed_data_dictionary()
    seed_sample_questions()
    seed_erp_reports()
    seed_playbooks()
    _agents_and_platform(first_install=True)
    frappe.db.commit()


def after_migrate():
    ensure_role()
    ensure_permissions()
    ensure_page_roles()
    _agents_and_platform(first_install=False)
    frappe.db.commit()


def _agents_and_platform(first_install: bool):
    """Coworkers, the shared gateway and the move from the separate Coworker app. Each step is idempotent."""
    from neotec_ai.agents import install as agents_install
    from neotec_ai.agents import takeover
    from neotec_ai.platform import setup as platform_setup

    takeover.run()  # first: records owned by the old app become ours before anything else touches them
    if first_install:
        agents_install.after_install()
    else:
        agents_install.after_migrate()
    platform_setup.run()


def ensure_role():
    if not frappe.db.exists("Role", AI_ROLE):
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": AI_ROLE,
                "desk_access": 1,
                "description": "Can use the Neotec AI assistant. Data access still follows the user's own permissions.",
            }
        ).insert(ignore_permissions=True)


def ensure_permissions():
    from frappe.permissions import setup_custom_perms

    for doctype, perms in ROLE_PERMISSIONS.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": AI_ROLE}):
            continue
        setup_custom_perms(doctype)  # copy standard perms first so they stay in effect
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": doctype,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": AI_ROLE,
                "permlevel": 0,
                **perms,
            }
        ).insert(ignore_permissions=True)
        frappe.clear_cache(doctype=doctype)


def ensure_page_roles():
    """BI pages are open to System Managers and Neotec AI Users."""
    for page in PAGES:
        if not frappe.db.exists("Page", page):
            continue
        doc = frappe.get_doc("Page", page)
        have = {r.role for r in doc.roles}
        changed = False
        for role in ("System Manager", AI_ROLE):
            if role not in have:
                doc.append("roles", {"role": role})
                changed = True
        if changed:
            doc.flags.ignore_permissions = True
            doc.save()


def init_settings():
    """Persist the settings defaults so the single DocType starts with sane values."""
    settings = frappe.get_single("Neotec Settings")
    settings.flags.ignore_mandatory = True
    settings.save(ignore_permissions=True)


def seed_data_dictionary():
    from neotec_ai.neotec_ai.doctype.neotec_data_source.neotec_data_source import STANDARD_FIELDS

    created = 0
    for doctype, spec in SEED_SOURCES.items():
        if not frappe.db.exists("DocType", doctype) or frappe.db.exists("Neotec Data Source", doctype):
            continue
        parent = spec.get("parent")
        if parent and not frappe.db.exists("DocType", parent):
            continue

        meta = frappe.get_meta(doctype)
        rows = [
            {"fieldname": f, "enabled": 1}
            for f in spec["fields"]
            if f in STANDARD_FIELDS or meta.get_field(f)
        ]
        if not rows:
            continue

        try:
            doc = frappe.get_doc(
                {
                    "doctype": "Neotec Data Source",
                    "source_doctype": doctype,
                    "parent_doctype": parent,
                    "enabled": spec.get("enabled", 1),
                    "submitted_only": spec.get("submitted_only", 1 if (meta.is_submittable or meta.istable) else 0),
                    "description": spec["description"],
                    "sample_questions": spec.get("sample_questions"),
                    "data_fields": rows,
                }
            )
            doc.apply_sample_meanings()
            doc.insert(ignore_permissions=True)
            created += 1
        except Exception:
            frappe.log_error(title=f"Neotec AI: could not seed data source {doctype}")
    return created


def seed_erp_reports():
    """Add the starter ERPNext report list (only reports that exist and are Script/Query reports)."""
    from neotec_ai.erp_report_seed import SEED_REPORTS

    created = 0
    for entry in SEED_REPORTS:
        name, purpose, questions = entry[0], entry[1], entry[2]
        enabled = entry[3] if len(entry) > 3 else 1
        if frappe.db.exists("Neotec ERP Report", name):
            continue
        row = frappe.db.get_value("Report", name, ["report_type", "disabled"], as_dict=True)
        if not row or row.report_type not in ("Script Report", "Query Report") or row.disabled:
            continue
        try:
            frappe.get_doc({
                "doctype": "Neotec ERP Report", "report": name, "enabled": enabled,
                "purpose": purpose, "sample_questions": questions or None,
            }).insert(ignore_permissions=True)
            created += 1
        except Exception:
            frappe.log_error(title=f"Neotec AI: could not seed ERP report {name}")
    return created


def seed_playbooks():
    from neotec_ai.playbooks import seed_examples

    return seed_examples()


def seed_sample_questions():
    """Insert library questions that are not already present (matched by text + scope target)."""
    from neotec_ai.sample_questions import iter_questions

    existing = {
        (r.question.strip().lower(), r.scope, r.module or "", r.reference_doctype or "")
        for r in frappe.get_all(
            "Neotec Sample Question", fields=["question", "scope", "module", "reference_doctype"]
        )
    }
    modules = set(frappe.get_all("Module Def", pluck="name"))
    created = 0
    for q in iter_questions():
        if q["scope"] == "Module" and q["module"] not in modules:
            continue
        if q["scope"] in ("DocType", "Document") and not frappe.db.exists("DocType", q["reference_doctype"]):
            continue
        key = (q["question"].strip().lower(), q["scope"], q.get("module") or "", q.get("reference_doctype") or "")
        if key in existing:
            continue
        frappe.get_doc({"doctype": "Neotec Sample Question", "enabled": 1, **q}).insert(ignore_permissions=True)
        existing.add(key)
        created += 1
    return created
