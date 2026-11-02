"""Install / migrate hooks: create the access role and seed a starter Data Dictionary."""

import frappe

AI_ROLE = "Neotec AI User"

# Starter Data Dictionary. Only DocTypes (and fields) that exist on the site are created,
# so this is safe on plain Frappe as well as ERPNext / HRMS sites.
# Each entry: description, fields, optional parent (for child tables), enabled flag.
SEED_SOURCES = {
    "Customer": {
        "description": "Customers the business sells to. customer_group and territory classify them.",
        "fields": ["name", "customer_name", "customer_type", "customer_group", "territory", "disabled", "creation"],
    },
    "Supplier": {
        "description": "Suppliers / vendors the business buys from.",
        "fields": ["name", "supplier_name", "supplier_group", "supplier_type", "country", "disabled"],
    },
    "Item": {
        "description": "Products and services. is_stock_item = 1 means inventory is tracked.",
        "fields": ["name", "item_name", "item_group", "brand", "stock_uom", "is_stock_item", "disabled"],
    },
    "Sales Invoice": {
        "description": (
            "Customer invoices (revenue). Use base_grand_total for amounts in company currency. "
            "outstanding_amount is what the customer still owes. is_return = 1 marks credit notes."
        ),
        "fields": [
            "name", "customer", "customer_name", "company", "posting_date", "due_date", "currency",
            "grand_total", "base_grand_total", "outstanding_amount", "status", "is_return",
        ],
        "sample_questions": "Revenue this month; top 10 customers by sales this year; overdue invoices",
    },
    "Sales Invoice Item": {
        "parent": "Sales Invoice",
        "description": "Line items of Sales Invoices. parent is the invoice ID. Use for item-wise sales.",
        "fields": ["parent", "item_code", "item_name", "item_group", "qty", "rate", "amount", "base_amount", "warehouse"],
        "sample_questions": "Best-selling items by quantity last quarter",
    },
    "Sales Order": {
        "description": "Confirmed customer orders. per_delivered / per_billed show fulfilment progress (%).",
        "fields": [
            "name", "customer", "company", "transaction_date", "delivery_date",
            "grand_total", "base_grand_total", "status", "per_delivered", "per_billed",
        ],
    },
    "Purchase Invoice": {
        "description": "Supplier bills (expenses / payables). outstanding_amount is what the business still owes.",
        "fields": [
            "name", "supplier", "company", "posting_date", "due_date",
            "grand_total", "base_grand_total", "outstanding_amount", "status", "is_return",
        ],
    },
    "Purchase Order": {
        "description": "Orders placed with suppliers.",
        "fields": [
            "name", "supplier", "company", "transaction_date", "schedule_date",
            "grand_total", "base_grand_total", "status", "per_received", "per_billed",
        ],
    },
    "Payment Entry": {
        "description": "Money received (payment_type = Receive) or paid (payment_type = Pay).",
        "fields": [
            "name", "payment_type", "party_type", "party", "company", "posting_date",
            "paid_amount", "base_paid_amount", "mode_of_payment",
        ],
    },
    "Bin": {
        "description": (
            "Current stock per item per warehouse. actual_qty is on hand; projected_qty includes "
            "ordered and reserved quantities. stock_value is valuation in company currency."
        ),
        "fields": ["item_code", "warehouse", "actual_qty", "reserved_qty", "ordered_qty", "projected_qty", "stock_value"],
        "submitted_only": 0,
    },
    "Lead": {
        "description": "Sales leads / prospects.",
        "fields": ["name", "lead_name", "company_name", "status", "source", "territory", "creation"],
    },
    "Employee": {
        "description": "Employees. Disabled by default because it is personal data; enable deliberately.",
        "fields": ["name", "employee_name", "department", "designation", "status", "date_of_joining", "company"],
        "enabled": 0,
    },
}


def after_install():
    ensure_role()
    init_settings()
    seed_data_dictionary()
    frappe.db.commit()


def init_settings():
    """Persist the settings defaults so the single DocType starts with sane values."""
    settings = frappe.get_single("Neotec Settings")
    settings.flags.ignore_mandatory = True
    settings.save(ignore_permissions=True)


def after_migrate():
    ensure_role()


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


def seed_data_dictionary():
    from neotec_ai.neotec_ai.doctype.neotec_data_source.neotec_data_source import STANDARD_FIELDS

    for doctype, spec in SEED_SOURCES.items():
        if not frappe.db.exists("DocType", doctype) or frappe.db.exists("Neotec Data Source", doctype):
            continue
        parent = spec.get("parent")
        if parent and not frappe.db.exists("DocType", parent):
            continue

        meta = frappe.get_meta(doctype)
        rows = []
        for fieldname in spec["fields"]:
            if fieldname in STANDARD_FIELDS or meta.get_field(fieldname):
                rows.append({"fieldname": fieldname, "enabled": 1})
        if not rows:
            continue

        try:
            frappe.get_doc(
                {
                    "doctype": "Neotec Data Source",
                    "source_doctype": doctype,
                    "parent_doctype": parent,
                    "enabled": spec.get("enabled", 1),
                    "submitted_only": spec.get("submitted_only", 1 if meta.is_submittable else 0),
                    "description": spec["description"],
                    "sample_questions": spec.get("sample_questions"),
                    "data_fields": rows,
                }
            ).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title=f"Neotec AI: could not seed data source {doctype}")
