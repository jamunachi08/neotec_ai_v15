"""Starter list of ERPNext reports the AI may run. Only reports that exist on the site are added.

Purposes and questions are Neotec's own wording. HR/payroll reports are added disabled.
"""

SEED_REPORTS = [
    # ---- Accounts: financial statements
    ("Profit and Loss Statement", "Income, expenses and net profit by period (monthly/quarterly/yearly) for a company. Use for profit, margin and expense questions.",
     "Profit this year by month\nNet profit last quarter\nWhat were our total expenses this year?"),
    ("Balance Sheet", "Assets, liabilities and equity as of period ends. Use for financial position, cash, debt and equity questions.",
     "Balance sheet as of today\nTotal liabilities this year"),
    ("Cash Flow", "Cash generated and used by operating, investing and financing activities per period.",
     "Cash flow this year by quarter"),
    ("Trial Balance", "Opening balance, debits, credits and closing balance for every account in a period.",
     "Trial balance this month"),
    ("General Ledger", "Individual accounting entries for an account, party or voucher in a date range. Use for 'show the entries behind' questions.",
     "General ledger for Cash account this month"),
    ("Consolidated Financial Statement", "Combined P&L / balance sheet across companies in a group.", ""),
    # ---- Receivables / payables
    ("Accounts Receivable", "Every unpaid customer invoice with outstanding amount and ageing buckets (0-30, 31-60...). Use for who owes us and how overdue.",
     "Who owes us money?\nOverdue receivables older than 60 days"),
    ("Accounts Receivable Summary", "Outstanding amount per customer split into ageing buckets.",
     "Receivables ageing by customer"),
    ("Accounts Payable", "Every unpaid supplier bill with outstanding amount and ageing.",
     "Which supplier bills are overdue?"),
    ("Accounts Payable Summary", "Outstanding amount per supplier split into ageing buckets.",
     "Payables ageing by supplier"),
    ("Customer Ledger Summary", "Per customer: opening balance, invoiced, paid, credit notes and closing balance for a period.",
     "Customer balances this year"),
    ("Supplier Ledger Summary", "Per supplier: opening balance, billed, paid and closing balance for a period.", ""),
    # ---- Sales
    ("Sales Analytics", "Sales value or quantity over time (weekly/monthly/quarterly) by customer, customer group, territory, item or item group.",
     "Monthly sales by territory this year\nSales by item group per quarter"),
    ("Sales Register", "Every sales invoice in a period with net total, taxes and grand total.",
     "Sales register for last month"),
    ("Gross Profit", "Selling amount, buying cost and gross profit by invoice, item, customer or other grouping.",
     "Gross profit by item this year\nWhich customers are most profitable?"),
    ("Item-wise Sales History", "Which items were sold to which customers, with quantity, rate and amount.", ""),
    ("Sales Order Analysis", "Sales orders with ordered, delivered and billed quantities and amounts; shows what is pending or delayed.",
     "Sales orders pending delivery"),
    ("Sales Person-wise Transaction Summary", "Sales credited to each sales person, by document and item.", "Sales by sales person this quarter"),
    ("Territory-wise Sales", "Opportunities, quotations, orders and invoices per territory.", ""),
    ("Customer Acquisition and Loyalty", "New versus repeat customers and their revenue per month.", "How many new customers did we get each month?"),
    ("Inactive Customers", "Customers with no orders in the given number of days.", "Customers who haven't ordered in 90 days"),
    # ---- Buying
    ("Purchase Analytics", "Purchase value or quantity over time by supplier, supplier group, item or item group.", "Monthly purchases by supplier this year"),
    ("Purchase Register", "Every purchase invoice in a period with net total, taxes and grand total.", ""),
    ("Purchase Order Analysis", "Purchase orders with ordered, received and billed quantities; shows what is pending.", "Purchase orders not yet received"),
    ("Supplier-Wise Sales Analytics", "Consumption and delivery of items received from each supplier.", ""),
    # ---- Stock
    ("Stock Balance", "Opening, in, out and closing quantity and value per item and warehouse for a period.",
     "Stock value by warehouse\nClosing stock of an item"),
    ("Stock Projected Qty", "Actual, ordered, reserved and projected quantity per item and warehouse, with reorder level.", "Which items need reordering?"),
    ("Stock Ageing", "How long stock has been held, in age buckets, per item.", "Which stock is older than 90 days?"),
    ("Warehouse wise Item Balance Age and Value", "Item balance, age and value for each warehouse.", ""),
    ("Stock Ledger", "Every stock movement (in/out) with balance after each transaction. Heavy: use a short date range.", ""),
    ("Batch-Wise Balance History", "Stock balance per batch with expiry information.", ""),
    # ---- Projects / CRM / Manufacturing
    ("Project Summary", "Projects with progress, tasks and cost/billing totals.", ""),
    ("Lead Details", "Leads with owner, source, status and contact details.", ""),
    ("Opportunity Summary by Sales Stage", "Number and value of opportunities in each sales stage.", "Pipeline by sales stage"),
    ("Production Analytics", "Work orders planned, in progress and completed over time.", ""),
    ("BOM Stock Report", "Whether there is enough stock to build an item from its BOM.", ""),
    # ---- HR (personal data: seeded disabled)
    ("Monthly Attendance Sheet", "Attendance per employee per day for a month.", "", 0),
    ("Employee Leave Balance", "Leave allocated, taken and remaining per employee and leave type.", "", 0),
    ("Salary Register", "Salary components per employee for a period. Highly sensitive.", "", 0),
]
