"""Sample "Meaning for AI" texts.

suggest_meaning() returns, in order of preference:
  1. a DocType-specific meaning      (DOCTYPE_FIELD_MEANINGS["Sales Invoice"]["status"])
  2. a standard ERPNext field meaning (FIELD_MEANINGS["base_grand_total"])
  3. a generated meaning from the field's type, label and options (lists Select values,
     names the linked DocType, explains Check fields, etc.)

These are starting points; edit them to match how your business uses each field.
"""

FIELD_MEANINGS = {
    # identity & audit
    "name": "Unique document ID. Use to identify or count records.",
    "naming_series": "Numbering prefix of the document ID. Rarely needed for analysis.",
    "title": "Display title of the record.",
    "owner": "User who created the record.",
    "creation": "Date and time the record was created.",
    "modified": "Date and time the record was last changed.",
    "docstatus": "0 = Draft, 1 = Submitted, 2 = Cancelled. Only submitted (1) records count in business figures.",
    "parent": "ID of the parent document this line belongs to.",
    "idx": "Row number within the parent document.",
    "disabled": "1 = disabled/inactive, 0 = active. Filter disabled = 0 for active records.",
    "enabled": "1 = enabled/active, 0 = inactive.",
    "is_group": "1 = group (folder) node in a tree, 0 = leaf record. Usually filter is_group = 0.",
    "remarks": "Free-text remarks entered by the user.",
    "description": "Free-text description.",

    # organisation
    "company": "Legal company (entity) the document belongs to. Filter by company when the user names one.",
    "cost_center": "Cost center (department/branch) for cost and profit tracking.",
    "project": "Project this document or line is linked to.",
    "territory": "Sales region / territory used for regional analysis.",
    "department": "Department within the company.",

    # dates
    "posting_date": "Accounting date of the document. Use this date for period-wise financial reports.",
    "posting_time": "Time of posting.",
    "transaction_date": "Order / quotation date. Use for period-wise order analysis.",
    "due_date": "Date payment is due. Past due_date with outstanding_amount > 0 means overdue.",
    "delivery_date": "Promised delivery date to the customer.",
    "schedule_date": "Required-by / expected date for receiving the goods.",
    "valid_till": "Last date the quotation is valid.",
    "expected_start_date": "Planned start date.",
    "expected_end_date": "Planned end date.",
    "from_date": "Start date of the period.",
    "to_date": "End date of the period.",

    # parties
    "customer": "Customer ID (link to Customer). Use customer_name for display.",
    "customer_name": "Customer's display name.",
    "customer_group": "Customer category (e.g. Commercial, Retail) used for segmentation.",
    "customer_type": "Company or Individual.",
    "supplier": "Supplier ID (link to Supplier). Use supplier_name for display.",
    "supplier_name": "Supplier's display name.",
    "supplier_group": "Supplier category used for segmentation.",
    "party_type": "Type of party: Customer, Supplier, Employee, Shareholder.",
    "party": "ID of the customer / supplier / employee, depending on party_type.",
    "party_name": "Display name of the party.",
    "sales_partner": "Sales partner / agent credited for the sale.",
    "contact_email": "Contact e-mail address.",
    "email_id": "E-mail address.",
    "mobile_no": "Mobile phone number.",

    # money
    "currency": "Transaction currency of the document.",
    "conversion_rate": "Exchange rate from transaction currency to company currency.",
    "total": "Total before taxes and discounts, in transaction currency.",
    "net_total": "Total after discount, before taxes, in transaction currency.",
    "base_net_total": "Net total (after discount, before tax) in company currency. Good measure of net sales/purchases.",
    "total_taxes_and_charges": "Total tax amount in transaction currency.",
    "base_total_taxes_and_charges": "Total tax amount in company currency.",
    "discount_amount": "Additional discount given on the whole document.",
    "grand_total": "Final total including taxes, in the document's transaction currency. Do not add up across currencies; use base_grand_total.",
    "base_grand_total": "Final total including taxes, in company currency. Use this to sum revenue/purchases across documents.",
    "rounded_total": "Grand total after rounding, transaction currency.",
    "base_rounded_total": "Grand total after rounding, company currency.",
    "outstanding_amount": "Amount still unpaid. > 0 means money is still owed.",
    "paid_amount": "Amount paid, in the paid-from account currency.",
    "base_paid_amount": "Amount paid in company currency.",
    "received_amount": "Amount received, in the paid-to account currency.",
    "debit": "Debit amount in company currency.",
    "credit": "Credit amount in company currency.",
    "account": "General ledger account.",
    "mode_of_payment": "Payment method (Cash, Bank Transfer, Card, ...).",
    "payment_type": "Receive = money in from customers, Pay = money out to suppliers, Internal Transfer = between own accounts.",
    "is_return": "1 = return / credit note / debit note (negative amounts), 0 = normal document.",
    "is_paid": "1 = paid at the time of invoicing.",
    "total_amount": "Total amount.",

    # progress
    "status": "Current workflow status of the document.",
    "per_billed": "Percentage of the order already invoiced (0-100).",
    "per_delivered": "Percentage of the order already delivered (0-100).",
    "per_received": "Percentage of the order already received (0-100).",
    "per_ordered": "Percentage of the request already ordered (0-100).",
    "percent_complete": "Completion percentage (0-100).",
    "priority": "Priority level.",

    # items & stock
    "item_code": "Item ID (link to Item). Use item_name for display.",
    "item_name": "Item's display name.",
    "item_group": "Item category used for product analysis.",
    "brand": "Item brand.",
    "qty": "Quantity in the transaction unit of measure (uom).",
    "stock_qty": "Quantity converted to the item's stock unit. Use this to add up quantities across units.",
    "uom": "Unit of measure used on this line.",
    "stock_uom": "Base unit the item's stock is tracked in.",
    "rate": "Unit price in transaction currency.",
    "base_rate": "Unit price in company currency.",
    "amount": "Line amount (qty x rate) in transaction currency.",
    "base_amount": "Line amount in company currency. Use to sum item-wise sales/purchases.",
    "net_amount": "Line amount after discount, transaction currency.",
    "base_net_amount": "Line amount after discount, company currency.",
    "warehouse": "Warehouse (stock location).",
    "set_warehouse": "Default warehouse for all lines.",
    "s_warehouse": "Source warehouse (stock goes out of here).",
    "t_warehouse": "Target warehouse (stock goes into here).",
    "actual_qty": "Quantity physically in stock now.",
    "projected_qty": "Expected stock = actual + ordered + planned - reserved. Negative means a shortage is coming.",
    "reserved_qty": "Quantity reserved for open sales orders.",
    "ordered_qty": "Quantity ordered from suppliers, not yet received.",
    "planned_qty": "Quantity planned in work orders.",
    "stock_value": "Value of stock on hand in company currency.",
    "valuation_rate": "Cost per unit used for stock valuation.",
    "is_stock_item": "1 = inventory is tracked, 0 = service / non-stock item.",
    "is_fixed_asset": "1 = item is a fixed asset.",
    "batch_no": "Batch number.",
    "serial_no": "Serial number(s).",
    "stock_entry_type": "Purpose of the stock movement (Material Receipt, Material Issue, Material Transfer, Manufacture, ...).",
    "purpose": "Purpose of the movement or request.",
    "voucher_type": "Type of the source document (Sales Invoice, Payment Entry, ...).",
    "voucher_no": "ID of the source document.",
    "is_cancelled": "1 = entry belongs to a cancelled document; filter is_cancelled = 0.",

    # CRM
    "lead_owner": "User responsible for following up the lead.",
    "lead_name": "Person's full name on the lead.",
    "company_name": "Organisation the lead works for.",
    "source": "Where the lead came from (Website, Campaign, Referral, ...). Use for lead-source analysis.",
    "opportunity_from": "Whether the opportunity is for a Lead or a Customer.",
    "opportunity_amount": "Expected deal value.",
    "probability": "Estimated chance of winning, in percent.",
    "expected_closing": "Expected date the deal will close.",
    "sales_stage": "Stage of the deal in the sales pipeline.",
    "industry": "Industry of the organisation.",

    # HR
    "employee": "Employee ID (link to Employee).",
    "employee_name": "Employee's full name.",
    "designation": "Job title.",
    "date_of_joining": "Date the employee joined.",
    "relieving_date": "Date the employee left.",
    "gender": "Gender.",
    "branch": "Branch / office location.",
    "leave_type": "Type of leave (Annual, Sick, ...).",
    "total_leave_days": "Number of leave days requested.",
    "attendance_date": "Date of the attendance record.",
    "gross_pay": "Gross salary before deductions.",
    "net_pay": "Salary paid after deductions.",
    "total_deduction": "Total salary deductions.",

    # projects / support
    "subject": "Short summary / title.",
    "estimated_costing": "Planned cost.",
    "total_costing_amount": "Actual cost booked so far.",
    "total_billed_amount": "Amount billed to the customer so far.",
    "exp_start_date": "Planned start date.",
    "exp_end_date": "Planned end date.",
    "opening_date": "Date the ticket was opened.",
    "resolution_date": "Date the ticket was resolved.",
    "raised_by": "E-mail of the person who raised the ticket.",
    "issue_type": "Category of the support ticket.",
    "hours": "Hours worked.",
    "billing_hours": "Billable hours.",

    # manufacturing
    "production_item": "Item being manufactured.",
    "bom_no": "Bill of materials used.",
    "produced_qty": "Quantity manufactured so far.",
    "is_active": "1 = active.",
    "is_default": "1 = default record.",
    "total_cost": "Total cost.",

    # assets
    "asset_name": "Asset's display name.",
    "asset_category": "Category of the asset.",
    "gross_purchase_amount": "Purchase cost of the asset.",
    "value_after_depreciation": "Current book value after depreciation.",
    "location": "Physical location.",
    "purchase_date": "Date the asset was purchased.",
    "available_for_use_date": "Date the asset was put to use.",
}

DOCTYPE_FIELD_MEANINGS = {
    "Sales Invoice": {
        "status": "Draft, Unpaid, Overdue, Partly Paid, Paid, Return, Credit Note Issued, Cancelled. 'Overdue' = past due date and not fully paid.",
        "base_grand_total": "Invoice total incl. tax in company currency. Sum this for revenue (gross). Use base_net_total for revenue excluding tax.",
        "outstanding_amount": "Amount the customer still owes on this invoice (receivable).",
        "is_return": "1 = credit note (sales return, negative amounts). Exclude with is_return = 0 for gross sales.",
    },
    "Purchase Invoice": {
        "status": "Draft, Unpaid, Overdue, Partly Paid, Paid, Return, Debit Note Issued, Cancelled.",
        "outstanding_amount": "Amount we still owe the supplier on this bill (payable).",
        "base_grand_total": "Bill total incl. tax in company currency. Sum this for purchase spend.",
        "bill_no": "Supplier's own invoice number.",
        "is_return": "1 = debit note (purchase return).",
    },
    "Sales Order": {
        "status": "Draft, On Hold, To Deliver and Bill, To Bill, To Deliver, Completed, Cancelled, Closed. Open orders = not Completed/Closed/Cancelled.",
        "base_grand_total": "Order value incl. tax in company currency. Sum for order booking value.",
    },
    "Purchase Order": {
        "status": "Draft, On Hold, To Receive and Bill, To Bill, To Receive, Completed, Cancelled, Closed.",
        "base_grand_total": "Order value incl. tax in company currency.",
    },
    "Quotation": {
        "status": "Draft, Open, Replied, Partially Ordered, Ordered, Lost, Cancelled, Expired. Ordered = converted to a sales order (won).",
        "quotation_to": "Customer or Lead.",
        "party_name": "ID of the Customer or Lead the quotation is for.",
    },
    "Lead": {
        "status": "Lead stage: Lead, Open, Replied, Opportunity, Quotation, Lost Quotation, Interested, Converted, Do Not Contact.",
        "name": "Lead ID. Count this to get number of leads.",
    },
    "Opportunity": {
        "status": "Open, Quotation, Converted, Lost, Replied, Closed.",
        "opportunity_amount": "Expected deal value; sum for pipeline value.",
    },
    "Payment Entry": {
        "paid_amount": "Amount of the payment in the paid-from account currency.",
        "base_paid_amount": "Payment amount in company currency. Sum with payment_type = Receive for collections, Pay for payouts.",
    },
    "Bin": {
        "item_code": "Item ID. One Bin row per item per warehouse.",
        "actual_qty": "On-hand quantity in this warehouse. Sum across warehouses for total stock of an item. <= 0 means out of stock.",
    },
    "GL Entry": {
        "debit": "Debit amount in company currency. Income accounts: credit - debit = income; expense accounts: debit - credit = expense.",
        "credit": "Credit amount in company currency.",
        "is_cancelled": "1 = reversed by cancellation. Always filter is_cancelled = 0.",
    },
    "Stock Ledger Entry": {
        "actual_qty": "Quantity change from this transaction (+ in, - out).",
        "qty_after_transaction": "Stock balance after this transaction.",
        "stock_value_difference": "Change in stock value from this transaction.",
    },
    "Delivery Note": {
        "status": "Draft, To Bill, Completed, Return Issued, Cancelled, Closed.",
    },
    "Purchase Receipt": {
        "status": "Draft, To Bill, Completed, Return Issued, Cancelled, Closed.",
    },
    "Material Request": {
        "material_request_type": "Purchase, Material Transfer, Material Issue, Manufacture, Customer Provided.",
        "status": "Draft, Submitted, Stopped, Cancelled, Pending, Partially Ordered, Ordered, Issued, Transferred, Received.",
    },
    "Work Order": {
        "status": "Draft, Not Started, In Process, Completed, Stopped, Closed, Cancelled.",
        "qty": "Quantity planned to manufacture.",
    },
    "Project": {
        "status": "Open, Completed, Cancelled.",
    },
    "Task": {
        "status": "Open, Working, Pending Review, Overdue, Template, Completed, Cancelled.",
    },
    "Issue": {
        "status": "Open, Replied, On Hold, Resolved, Closed.",
    },
    "Employee": {
        "status": "Active, Inactive, Suspended, Left. Count status = Active for headcount.",
    },
    "Asset": {
        "status": "Draft, Submitted, Partially Depreciated, Fully Depreciated, Sold, Scrapped, In Maintenance, Out of Order, Issue, Receipt, Capitalized, Decapitalized.",
    },
}

# Shown on the Data Source form as guidance.
MEANING_EXAMPLES = [
    ("base_grand_total", "Invoice total incl. tax in company currency. Sum this for revenue."),
    ("outstanding_amount", "Amount the customer still owes. > 0 means unpaid."),
    ("status", "Overdue = past due date and not fully paid. Open orders = not Completed/Closed/Cancelled."),
    ("custom_region", "Our internal sales region: North, South, East, West. Use for regional reports."),
    ("alphax_lead_score", "Lead quality score 0-100. 70+ = hot lead, below 30 = cold."),
    ("alphax_idle_days", "Days since last contact with the lead. Over 14 = needs follow-up."),
    ("is_return", "1 = credit note. Exclude with is_return = 0 for gross sales."),
]


def suggest_meaning(doctype, df, standard=None):
    """Return a sample meaning for a field. `df` is a DocField (or None for standard fields)."""
    fieldname = df.fieldname if df else standard
    specific = DOCTYPE_FIELD_MEANINGS.get(doctype, {}).get(fieldname)
    if specific:
        return specific
    if fieldname in FIELD_MEANINGS:
        meaning = FIELD_MEANINGS[fieldname]
        if df and df.fieldtype == "Select" and fieldname == "status":
            opts = _select_options(df)
            if opts:
                meaning = f"Current status. Values: {opts}."
        return meaning
    if not df:
        return ""
    return _generated(df)


def _select_options(df, limit=15):
    opts = [o.strip() for o in (df.options or "").split("\n") if o.strip()]
    if not opts:
        return ""
    shown = ", ".join(opts[:limit])
    return shown + (", ..." if len(opts) > limit else "")


def _generated(df):
    label = (df.label or df.fieldname.replace("_", " ")).strip()
    ft = df.fieldtype
    fn = df.fieldname
    base = fn.startswith("base_")

    if ft == "Link":
        return f"{label}: ID of the linked {df.options} record."
    if ft == "Dynamic Link":
        return f"{label}: ID of a record whose type is given by the '{df.options}' field."
    if ft == "Select":
        opts = _select_options(df)
        return f"{label}. Allowed values: {opts}." if opts else f"{label} (choice field)."
    if ft == "Check":
        return f"{label}: 1 = Yes, 0 = No."
    if ft == "Currency":
        return f"{label} in {'company' if base else 'the document'} currency."
    if ft == "Percent":
        return f"{label}, in percent (0-100)."
    if ft in ("Int", "Float"):
        return f"{label} (number)."
    if ft == "Date":
        return f"{label} (date). Use for date filters and period grouping."
    if ft == "Datetime":
        return f"{label} (date and time)."
    if ft == "Duration":
        return f"{label}, duration in seconds."
    if ft == "Rating":
        return f"{label}, rating from 0 to 1."
    return f"{label}."
