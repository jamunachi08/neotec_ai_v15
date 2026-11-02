"""Built-in sample question library.

Scopes:
  Global    - shown everywhere
  Module    - shown on that module's workspace and on its DocTypes' list/form views
  DocType   - shown on that DocType's list and form views
  Document  - shown only when a record of that DocType is open (uses the open document as context)

Questions are loaded into the "Neotec Sample Question" DocType on install / migrate, where they
can be edited, disabled or extended. Module questions are skipped if the module is not installed;
DocType questions if the DocType does not exist.
"""

GLOBAL = [
    "Give me an executive summary of the business this month: sales, purchases, collections and payables.",
    "What is our total revenue this month compared with last month?",
    "Show revenue by month for this year as a line chart.",
    "Compare revenue this quarter with last quarter.",
    "Who are our top 10 customers by revenue this year? Show a bar chart.",
    "Which customers owe us the most right now?",
    "What is our total receivable outstanding, and how much of it is overdue?",
    "How much do we owe suppliers in total, and to which suppliers the most?",
    "Show all overdue sales invoices with customer, amount and due date.",
    "What were our total purchases this quarter by supplier?",
    "Which items sold the most this month by quantity?",
    "Which items brought in the most revenue this year?",
    "Show revenue by item group this year as a pie chart.",
    "Which territories bring the most revenue this year?",
    "Revenue by customer group this year.",
    "How many new customers did we add this month?",
    "How many leads did we get this month, and from which sources?",
    "What is the value of our open sales pipeline by stage?",
    "Which sales orders are still pending delivery?",
    "Which purchase orders have not been fully received yet?",
    "What is our current stock value by warehouse?",
    "Which items are out of stock?",
    "Which items are heading for a shortage (negative projected quantity)?",
    "How much money did we receive versus pay out this month?",
    "List payments received this week.",
    "What is our average invoice value this year?",
    "What is the total of sales returns (credit notes) this year?",
    "How many sales invoices did we create today, and for how much?",
    "Build a report of monthly sales and purchases this year.",
    "Show sales by sales partner this year.",
    "Which customers have not bought anything this year?",
    "What are our biggest expense accounts this month?",
    "Give me a weekly summary: new orders, invoices, payments and new leads.",
    "Which suppliers did we spend the most with this year?",
    "What is our quotation win rate this quarter?",
    "Show the number of open support tickets by priority.",
    "Which projects are over budget?",
    "What key numbers should I look at today?",
]

MODULES = {
    "Accounts": [
        "Total receivables by customer, largest first.",
        "Total payables by supplier, largest first.",
        "Receivables ageing: overdue amounts by customer.",
        "Bills due for payment in the next 7 days.",
        "Collections (payments received) by month this year as a chart.",
        "Payments made to suppliers by month this year.",
        "Sales invoices by status this month.",
        "Purchase invoices by status this month.",
        "Expenses by account this month.",
        "Income by account this year.",
        "Expenses by cost center this quarter.",
        "Payment entries by mode of payment this month.",
        "How many unpaid invoices are older than 60 days?",
        "Largest 10 sales invoices this month.",
        "Credit notes issued this year by customer.",
        "Debit notes issued this year by supplier.",
        "Journal entries posted this month and their totals.",
        "Net revenue (excluding tax) by month this year.",
        "Tax collected on sales this quarter.",
        "Which customers pay late most often?",
    ],
    "Selling": [
        "Sales by month this year as a bar chart.",
        "Top 10 customers by sales this quarter.",
        "Top 10 items by sales value this year.",
        "Sales by territory this year.",
        "Sales by customer group this year.",
        "Open sales orders pending delivery, with expected delivery date.",
        "Sales orders delivered but not yet billed.",
        "Order bookings (sales order value) by month this year.",
        "Quotations sent this month and how many were won.",
        "Quotations expiring this week.",
        "Lost quotations this quarter and the reasons.",
        "Average order value this year.",
        "New customers acquired by month this year.",
        "Sales by sales partner this year.",
        "Which items have not sold in the last 6 months?",
        "Delivery notes not yet invoiced.",
        "Customer-wise sales this year compared with last year.",
        "Sales returns by item this year.",
    ],
    "Buying": [
        "Purchase spend by month this year.",
        "Top 10 suppliers by spend this year.",
        "Open purchase orders not yet received.",
        "Purchase orders received but not yet billed.",
        "Purchase spend by item group this year.",
        "Material requests pending ordering.",
        "Purchase receipts this month by supplier.",
        "Items purchased the most by quantity this quarter.",
        "Average purchase price of an item over the last 6 months.",
        "Purchase orders overdue for receipt (past required-by date).",
        "Supplier bills due this week.",
        "New suppliers added this year.",
    ],
    "Stock": [
        "Stock value by warehouse.",
        "Total stock value by item group.",
        "Items out of stock (zero or negative quantity).",
        "Items with negative projected quantity (coming shortage).",
        "Top 20 items by stock value.",
        "Stock quantity of an item across all warehouses.",
        "Stock movements this week by type.",
        "Material transfers between warehouses this month.",
        "Items received this month.",
        "Items issued this month.",
        "Reserved quantity for open sales orders by item.",
        "Quantity on order from suppliers by item.",
        "Slow-moving items: no stock movement in the last 6 months.",
        "Stock entries by purpose this month.",
        "Which warehouses hold the most stock value?",
        "Daily stock movement for an item this month.",
    ],
    "CRM": [
        "Leads by source this month as a pie chart.",
        "Leads by status.",
        "New leads per week this quarter.",
        "Leads per lead owner this month.",
        "Leads by territory this year.",
        "Leads by industry.",
        "Pipeline value by sales stage.",
        "Opportunities expected to close this month.",
        "Opportunities won and lost this quarter.",
        "Opportunity value by owner.",
        "Average opportunity value this year.",
        "Lead to opportunity conversion this quarter.",
        "Open opportunities with probability above 70%.",
        "Leads with no follow-up for more than 14 days.",
    ],
    "Manufacturing": [
        "Work orders in progress and their completion.",
        "Work orders completed this month.",
        "Planned vs produced quantity by item this month.",
        "Work orders overdue against expected delivery date.",
        "Active BOMs and their cost.",
        "Top manufactured items by quantity this quarter.",
        "Stock entries of type Manufacture this month.",
        "Work orders by status.",
    ],
    "Projects": [
        "Projects by status.",
        "Projects over budget (actual cost above estimated cost).",
        "Project completion percentage for all open projects.",
        "Overdue tasks by project.",
        "Tasks by status and priority.",
        "Hours logged per employee this month.",
        "Billable vs total hours this month.",
        "Billed amount by project this year.",
        "Projects ending this month.",
    ],
    "Support": [
        "Open tickets by priority.",
        "Tickets opened per week this quarter.",
        "Tickets by issue type this month.",
        "Customers with the most tickets this year.",
        "Average resolution time this month.",
        "Tickets resolved this week.",
    ],
    "Assets": [
        "Assets by category with total value.",
        "Total book value of assets after depreciation.",
        "Assets purchased this year.",
        "Assets by location.",
        "Fully depreciated assets.",
        "Assets in maintenance or out of order.",
    ],
    "Setup": [
        "Headcount by department.",
        "Headcount by designation.",
        "Employees who joined this year.",
        "Employees who left this year.",
        "Headcount by branch and gender.",
    ],
    "HR": [
        "Headcount by department.",
        "Employees on leave today.",
        "Leave applications this month by leave type.",
        "Attendance summary for this week by status.",
        "Absent employees this month.",
        "Expense claims pending approval.",
        "Expense claims by employee this quarter.",
        "New joiners this quarter.",
    ],
    "Payroll": [
        "Total net pay by month this year.",
        "Payroll cost by department this month.",
        "Gross pay vs deductions this month.",
        "Salary slips not yet submitted this month.",
    ],
    "Quality Management": [
        "Quality inspections this month by status.",
        "Rejected quality inspections by item.",
    ],
}

# DocType -> {"list": questions about the DocType in general, "document": questions about the open record}
DOCTYPES = {
    "Sales Invoice": {
        "list": [
            "Overdue sales invoices with days overdue.",
            "Unpaid invoices by customer.",
            "Invoices created this week.",
            "Revenue by month this year.",
            "Credit notes issued this month.",
        ],
        "document": [
            "Summarize this invoice.",
            "Has this customer paid previous invoices on time?",
            "What else does this customer still owe us?",
            "How does this invoice compare with the customer's average invoice?",
            "Draft a polite payment reminder for this invoice.",
        ],
    },
    "Sales Order": {
        "list": [
            "Open sales orders pending delivery.",
            "Sales orders delivered but not billed.",
            "Sales order value by month this year.",
        ],
        "document": [
            "Summarize this sales order and its delivery and billing status.",
            "Which items on this order are still to be delivered?",
            "Show this customer's order history this year.",
        ],
    },
    "Quotation": {
        "list": [
            "Open quotations expiring this week.",
            "Win rate of quotations this quarter.",
            "Lost quotations by reason.",
        ],
        "document": [
            "Summarize this quotation.",
            "How often has this customer accepted our quotations?",
            "Draft a follow-up email for this quotation.",
        ],
    },
    "Delivery Note": {
        "list": ["Delivery notes not yet billed.", "Deliveries this week by customer."],
        "document": ["Summarize this delivery note.", "Has this delivery been invoiced?"],
    },
    "Customer": {
        "list": [
            "Top customers by revenue this year.",
            "New customers this month.",
            "Customers by group and territory.",
            "Customers who haven't ordered this year.",
        ],
        "document": [
            "Give me a 360° summary of this customer: sales, outstanding, last order.",
            "What is this customer's revenue by month this year?",
            "Which items does this customer buy most?",
            "What does this customer owe us right now?",
            "Show this customer's open orders.",
        ],
    },
    "Lead": {
        "list": [
            "Leads by source this month.",
            "Leads by status.",
            "Leads per owner this month.",
            "Leads not contacted in the last 14 days.",
        ],
        "document": [
            "Summarize this lead and suggest the next best action.",
            "Draft a follow-up email to this lead.",
            "Are there other leads from the same organization?",
        ],
    },
    "Opportunity": {
        "list": ["Pipeline value by stage.", "Opportunities closing this month.", "Won vs lost opportunities this quarter."],
        "document": ["Summarize this opportunity and its next steps.", "Draft a follow-up email for this opportunity."],
    },
    "Purchase Invoice": {
        "list": ["Bills due this week.", "Unpaid bills by supplier.", "Purchase spend by month this year."],
        "document": [
            "Summarize this bill.",
            "What else do we owe this supplier?",
            "How does this bill compare with previous bills from this supplier?",
        ],
    },
    "Purchase Order": {
        "list": ["Purchase orders not yet received.", "PO value by supplier this year.", "Overdue purchase orders."],
        "document": [
            "Summarize this purchase order and its receipt status.",
            "Which items on this PO are still pending?",
            "Draft a reminder to the supplier about pending items.",
        ],
    },
    "Purchase Receipt": {
        "list": ["Receipts this month by supplier.", "Receipts not yet billed."],
        "document": ["Summarize this purchase receipt."],
    },
    "Supplier": {
        "list": ["Top suppliers by spend this year.", "Suppliers by group.", "New suppliers this year."],
        "document": [
            "Give me a summary of this supplier: spend, open orders, payables.",
            "What do we owe this supplier?",
            "Which items do we buy from this supplier most?",
        ],
    },
    "Material Request": {
        "list": ["Material requests pending ordering.", "Material requests by type this month."],
        "document": ["Summarize this material request and what has been ordered."],
    },
    "Item": {
        "list": ["Items by item group.", "Top selling items this month.", "Items out of stock.", "Items not sold in 6 months."],
        "document": [
            "Where is this item in stock and how much?",
            "How much of this item did we sell by month this year?",
            "Who are the top customers for this item?",
            "What did we pay for this item recently?",
            "Is this item at risk of running out?",
        ],
    },
    "Warehouse": {
        "list": ["Stock value by warehouse."],
        "document": ["What is the stock value in this warehouse?", "Top items by value in this warehouse."],
    },
    "Stock Entry": {
        "list": ["Stock entries by purpose this month.", "Material transfers this week."],
        "document": ["Summarize this stock entry."],
    },
    "Payment Entry": {
        "list": ["Payments received this month by customer.", "Payments made this month by supplier.", "Payments by mode of payment."],
        "document": ["Summarize this payment.", "What does this party still owe or is owed after this payment?"],
    },
    "Journal Entry": {
        "list": ["Journal entries this month."],
        "document": ["Explain this journal entry in plain language."],
    },
    "Work Order": {
        "list": ["Work orders in progress.", "Work orders overdue."],
        "document": ["Summarize this work order and its progress."],
    },
    "BOM": {
        "list": ["Active BOMs and their cost."],
        "document": ["Summarize this BOM and its cost."],
    },
    "Project": {
        "list": ["Projects by status.", "Projects over budget."],
        "document": [
            "Summarize this project: progress, cost vs budget, billing.",
            "Which tasks in this project are overdue?",
            "Hours logged on this project by employee.",
        ],
    },
    "Task": {
        "list": ["Overdue tasks.", "Tasks by status and priority."],
        "document": ["Summarize this task."],
    },
    "Issue": {
        "list": ["Open tickets by priority.", "Tickets opened this week."],
        "document": [
            "Summarize this ticket.",
            "Has this customer raised similar tickets before?",
            "Draft a reply to this ticket.",
        ],
    },
    "Employee": {
        "list": ["Headcount by department.", "New joiners this year."],
        "document": ["Summarize this employee's leave and attendance this year."],
    },
    "Asset": {
        "list": ["Assets by category with value.", "Fully depreciated assets."],
        "document": ["Summarize this asset and its current book value."],
    },
}


def iter_questions():
    order = 0
    for q in GLOBAL:
        order += 1
        yield {"question": q, "scope": "Global", "sort_order": order}
    for module, qs in MODULES.items():
        for i, q in enumerate(qs, start=1):
            yield {"question": q, "scope": "Module", "module": module, "sort_order": i}
    for doctype, groups in DOCTYPES.items():
        for i, q in enumerate(groups.get("list", []), start=1):
            yield {"question": q, "scope": "DocType", "reference_doctype": doctype, "sort_order": i}
        for i, q in enumerate(groups.get("document", []), start=1):
            yield {"question": q, "scope": "Document", "reference_doctype": doctype, "sort_order": i}
