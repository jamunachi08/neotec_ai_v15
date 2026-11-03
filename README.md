# Neotec AI Hub (`neotec_ai`)

A white-labeled AI assistant for **Frappe / ERPNext v15 and later**. Users ask business questions in plain language from any desk page; the AI looks up live data through a governed **Data Dictionary** and answers with only the data that user is allowed to see.

Current version: **3.1.0** (3 November 2026).

## Documentation

| Document | For | Covers |
|---|---|---|
| **End User Guide** | Business users | Asking questions, reports and charts, BI Builder, dashboards, scheduled e-mails, approvals, chat history and projects, privacy, FAQ, what's new |
| **Implementor Guide** | Administrators and implementation partners | Architecture, installation and upgrades, every setting, Data Dictionary, ERPNext reports, playbooks, roles and permissions, security and privacy, operations, troubleshooting, change log, API reference |
| This README | Developers and installers | Quick overview, install and upgrade commands, version history |

The two guides are kept as separate shareable documents (Word/PDF export available) alongside this package.

## What's in it

| Piece | Purpose |
|---|---|
| **Neotec Settings** | Provider (Gemini, Claude, OpenAI, OpenAI-compatible / Ollama), model, key, limits, business context, rate limit, log retention |
| **Neotec Data Source** | The Data Dictionary: one entry per DocType the AI may query, with a plain-language description and the exact fields it may use |
| **Neotec AI Report** | Reports the AI built and users saved. Opened anytime, they re-run live with the viewer's permissions |
| **Neotec Sample Question** | ~280 ready-made questions (general, per module, per DocType, per open document) shown as clickable suggestions |
| **BI Builder** (`/app/neotec-bi`) | No-code report builder with joins, aggregates, formulas, pivots and charts, plus an AI bar that builds or edits the report from a sentence |
| **Neotec Dashboard** (`/app/neotec-dashboard`) | Dashboards of charts, KPI cards, tables and text with shared period/company filters and drag-to-arrange |
| **Neotec Report Schedule** | E-mails a report or dashboard daily/weekly/monthly as Excel, PDF (with charts) or CSV |
| **Neotec ERP Report** | ERPNext reports the AI may run (P&L, Balance Sheet, Accounts Receivable, Stock Balance…), each with a one-line purpose and optional house default filters |
| **Neotec Playbook** | Company-specific instructions ("how we calculate commission") the AI loads when a question matches; optional role restriction or "always include" |
| **Saved chats & projects** | Every chat is saved per user with its reports; projects give a group of chats shared instructions |
| **Neotec AI Log** | Audit trail: who asked what, which queries ran, tokens, latency, errors |
| **Neotec AI User** role | Who may use the assistant and build/save reports, dashboards and schedules (System Managers always can) |
| Desk chat | Navbar button + **Alt+K**, multi-turn chat with history, projects, "Needs you" prompts (approvals, overdue to-dos), context-aware suggestions, attaches the open document as context |
| **Neotec AI** workspace | Shortcuts to the builder, dashboards, saved reports, schedules and setup |

## BI: build reports like Frappe Insights, with AI

Open **Neotec AI → BI Builder**.

1. **Describe it or build it.** Type a request in the AI bar ("Monthly revenue by item group this year as a stacked bar") and press *Build with AI*, or pick a data source and add columns yourself. Once a report exists, the same bar edits it ("only top 10", "split by territory", "make it a pivot by month").
2. **Data**: choose the data source; **Join related data** follows real relationships (invoice → its items → item master, invoice → customer, line item → parent). Columns can be plain values, *Sum / Count / Count distinct / Average / Min / Max*, date parts (*Year, Quarter, Month, Week, Day, Year-Month…*), or **formulas** on other columns (`revenue / orders`). Add **filters** (including periods like *this quarter*, *last 12 months*), **summary filters** (`revenue > 10,000`), sorting and a row limit. Results refresh automatically.
3. **Visualize**: Table, Bar, Line, Area, Pie, Donut, Percentage, Number (KPI card) or **Pivot** (rows × columns cross-tab with totals). Charts support a second label column, *Split by* (one line/bar per category) and stacking.
4. **Save / Save As**, **Add to Dashboard**, **Schedule E-mail**, **Export** (Excel, CSV, PDF). Saved reports keep the query, not a snapshot, so they always show current data.

Chat answers that include a report have an **Edit** button that opens it in the builder.

### Dashboards
Create a dashboard, then **Add Saved Report**, **Add Chart with AI** ("Total receivables as a number") or **Add Text**. **Edit Layout** lets you drag cards to reorder and set width (quarter to full) and height. The **Period** filter (and optional **Company** filter) applies to every card: by default to the date the report already filters on, or the main date of its data source; set *Date Field for Dashboard Filter* on an item to override. Export the whole dashboard to PDF or Excel (one sheet per card), or schedule it by e-mail. Share a dashboard with Frappe's normal **Share** (Dashboard Settings / Share).

### Permissions (who sees what)
- Every **Neotec AI User** can build reports and dashboards. They see their own and those shared with them; they can edit only their own (or ones shared with edit rights), and get a clear message otherwise.
- **Data always follows the viewer's own role permissions**: each table needs *read* permission, Frappe User Permissions (company, territory…), "only if creator" rules and permission-query hooks are applied to every table, child tables inherit their parent's permissions, and field-level (permlevel) restrictions are respected. If a report or dashboard card uses data the viewer can't access, that card shows *"You don't have permission to read …"* instead of data.
- Only DocTypes and fields enabled in the **Data Dictionary** can be used. Data sources the user can't read are hidden in the builder (with a note that some are hidden).
- **Scheduled e-mails run as the schedule's creator** and, by default, can only be sent to enabled users of the system (*Allow External E-mail Recipients* in Settings changes this).
- Queries are capped (*Max Rows per Report*) and time-limited (60 s); every value is a bound SQL parameter and identifiers come only from the Data Dictionary.

Database: the BI engine generates MariaDB SQL (the default for ERPNext). PostgreSQL sites can use the chat assistant, but the BI date functions are not yet Postgres-compatible.

## Writing field meanings ("Meaning for AI")

Each Data Source field has a *Meaning for AI*. The **Fields** menu on the Data Source form has:

- **Load Fields** – adds fields from the DocType, with sample meanings already filled in.
- **Fill Sample Meanings** – built-in meanings for ~200 standard ERPNext fields (e.g. `base_grand_total`, `outstanding_amount`, `status` per DocType), plus generated meanings for custom fields: Select fields list their allowed values, Link fields name the linked DocType, Check fields explain 1/0.
- **Suggest Meanings (AI)** – asks your configured model to draft meanings using the field metadata and your Business Context. Best for custom fields such as `alphax_lead_score`.

Open the "How to write a good Meaning for AI" panel on the form for examples. Good meanings say what the field means in your business, its unit/currency, its values, and how to use it in reports, e.g. *"Lead quality score 0-100. 70+ = hot lead, below 30 = cold."*

## Sample questions

The chat shows suggested questions for where the user is: the open record ("Summarize this invoice", "What else does this customer owe?"), the DocType list, the module workspace (Accounts, Selling, Buying, Stock, CRM, Manufacturing, Projects, Support, Assets, HR, Payroll, ...), and general business questions. Click one to ask it. Edit, disable or add your own under **Neotec Sample Question** (scope: Global, Module, DocType or Document).

## Reports (table and chart)

Ask for a report, chart, trend or breakdown ("Revenue by month this year as a line chart", "Top 10 customers by sales as a bar chart"). The answer includes an interactive report card:

- **View**: switch Chart / Table, change chart type (bar, line, pie, donut, percentage), open full view.
- **Export**: Excel (.xlsx), CSV, chart image (SVG), Print / PDF. Exports re-run the query on the server with the user's permissions.
- **Save**: stores the report as a **Neotec AI Report**. Saved reports keep the query (not a data snapshot), so they always show current data; relative periods like "this month" roll forward. Users see their own saved reports and can share them with Frappe's Share; each viewer only sees data their permissions allow.

## How the AI answers questions about your data

1. The prompt carries your Business Context, any project instructions and "always include" playbooks, plus **what the AI can use**: data sources the user can read, ERPNext reports they can run, and the playbook list.
2. To keep the prompt small, *Data Dictionary in Prompt = Auto* sends full field details only for the few sources most relevant to the question (and the open document's DocType) and a one-line index of the rest. Report filter details are sent for the best-matching reports only.
3. The AI then uses tools, one step at a time (up to *Max AI Steps per Question*):
   - **describe**: field details of a data source, filters of a report, or a playbook's content;
   - **query**: a structured query plan (never SQL), validated against the Data Dictionary and run with the user's permissions;
   - **run_report**: an ERPNext report, run exactly as the user could run it in Desk;
   - **approvals**: the user's open workflow approvals.
4. It answers in text, optionally with interactive reports. The chat shows what was looked up.

Submittable DocTypes default to submitted records only. Child tables (e.g. Sales Invoice Item) use the parent's permissions.

## ERPNext reports

Financial statements and ageing are best taken from ERPNext's own reports, so the AI can run them: "Profit and loss this year by quarter", "Who owes us money and how overdue?", "Stock value by warehouse".

- **Which reports:** by default only those listed and enabled in **Neotec ERP Report** (about 35 standard reports are added on install; HR/payroll ones disabled). *Neotec Settings → Which Reports* can widen this to any Script/Query report the user can run. Reports on security/system data are never offered.
- **Permissions:** a report runs as the user, with the same checks as opening it in Desk (the report's roles and *report* permission on its DocType). The figures are what the user would see running the report themselves.
- **Filters:** read from each report's own definition. Company, fiscal year and dates are filled automatically when the user doesn't say; select values are checked; customer/item/etc. names are matched case-insensitively, with "Did you mean…" suggestions when ambiguous. Set *House Default Filters* on a report for your usual choices (e.g. periodicity Monthly). The Neotec ERP Report form shows the filters it detected.
- **Everywhere reports go:** an ERPNext report can be shown in chat, built in the **BI Builder** (pick it under *ERPNext reports* in the data source list and fill its filters), saved, exported, put on a **dashboard** (the dashboard's period and company filters are applied to the report's own date/company filters) and **scheduled** by e-mail.
- Heavy reports (e.g. Stock Ledger) run with a 90-second limit; give them a short date range.

## Playbooks

A playbook teaches the AI how *your* company does something: commission rules, month-end, what counts as an "active customer", which report to use for a KPI.

- Only the title and the *When should the AI use this?* line are in the prompt; the AI opens the full content when a question matches, so you can have many without slowing every answer. Write that line as the situations it covers.
- *Always Include* sends a short playbook with every question; use it for universal rules only (under 3,000 characters).
- *Only for Roles* restricts a playbook to certain roles.
- Two disabled examples are added on install to show the format.

## Approvals and "Needs you"

"What needs my approval?" lists the documents waiting on the user's workflow action, only for documents they can read and only where they have an action available, with links. The chat home shows a **Needs you** strip with the number of approvals waiting and overdue to-dos. Turn it off with *Answer "What Needs My Approval"* in Settings. The AI never approves anything itself.

## Saved chats and projects

- Every chat is saved for its user (☰ **History** in the chat): reopen, rename, pin, search or delete. Follow-up questions use the saved history on the server.
- Reports in an old chat are kept as definitions, not data; **Show (live data)** re-runs them with today's data and the user's current permissions.
- **Projects** group chats and add shared instructions ("focus on the Riyadh branch, amounts in SAR thousands").
- Users only see their own chats and projects. Chat history is purged after *Keep Chat History for (days)* (default 180; pinned chats are kept).

## Install

The app has to be in a git repository or copied into `apps/`.

**From a git repository (recommended)**

```sh
# push this folder to your own repo first
bench get-app https://github.com/<you>/neotec_ai.git
bench --site <your-site> install-app neotec_ai
bench build --app neotec_ai
bench restart
```

**From this folder directly**

```sh
cp -r neotec_ai ~/frappe-bench/apps/
cd ~/frappe-bench
./env/bin/pip install -e apps/neotec_ai
echo "neotec_ai" >> sites/apps.txt      # skip if already listed
bench --site <your-site> install-app neotec_ai
bench build --app neotec_ai
bench restart
```

Installing creates the **Neotec AI User** role, loads the sample questions, and seeds Data Dictionary entries (with sample meanings) for ~35 common DocTypes that exist on the site across Selling, CRM, Buying, Stock, Accounts, Manufacturing, Projects, Support and Assets. HR DocTypes (Employee, Leave, Attendance, Expense Claim, Salary Slip) are seeded **disabled** because they hold personal data.

**Upgrading from 3.0:** copy the new files over the app, then run `bench --site <your-site> migrate`, `bench build --app neotec_ai` and `bench restart`. Migration switches on ERPNext reports (listed reports only), approvals and Auto prompt sizing, raises *Max AI Steps* from 3 to 6, adds the starter report list, two example playbooks and new sample questions, and disables any Data Dictionary field that the new sensitive-field rules block.

**Upgrading from 2.x:** copy the new files over the app and run `bench --site <your-site> migrate`, then `bench build --app neotec_ai` and `bench restart`. Migration adds the BI pages, dashboards, schedules and workspace, gives the Neotec AI User role access to them, adds new data sources, fills empty field meanings (your own text is kept) and loads the sample questions. Reports saved in 2.x keep working and open in the BI Builder. Make sure the scheduler is enabled (`bench --site <your-site> enable-scheduler`) for scheduled e-mails.

## Set up

1. **Neotec Settings** → choose the provider, confirm the **Model ID** against your provider's current model list, paste the API key, Save, then **Test Connection**.
2. Fill in **Business Context & Glossary**: what the company does, base currency, fiscal year, what "revenue" or "active customer" means to you, internal abbreviations. This noticeably improves answers.
3. Review **Neotec Data Source** entries. For each: write what the data means, untick fields you don't want exposed, add field meanings ("base_grand_total = invoice total in company currency"). Add new DocTypes (including custom ones) with **Load Fields**.
4. Give the **Neotec AI User** role to the people who should use it.

## Data and privacy notes

- Question text, the readable fields of the open document, and query results are sent to the AI provider you configure. For data that must not leave your network, use an OpenAI-compatible local server (e.g. Ollama).
- Only expose fields you're comfortable sending to that provider. Password, attachment, signature and code fields cannot be exposed.
- **Sensitive fields are always blocked**, whatever is configured: passwords, API keys/secrets, tokens, bank account/IBAN/card numbers and similar names never reach the AI from the Data Dictionary, the open document or report columns. Add your own under *Neotec Settings → Extra Sensitive Fields* (e.g. `custom_tax_id` or `Employee.cell_number`). Security and system DocTypes (users, roles, logs, e-mail accounts, scripts, files…) can never be data sources.
- Logs store the queries that ran; turning on *Store Query Results in Logs* stores the returned rows too. Logs are purged after *Keep Logs for (days)*.

## Version history

Newest first. Every version since 2.0 upgrades in place with `bench migrate`; see the Implementor Guide for migration details.

| Version | Date | Highlights |
|---|---|---|
| **3.1.0** | 2026-11-03 | ERPNext reports for the AI (Neotec ERP Report, filter detection, smart defaults, validation; also in BI Builder, dashboards, exports, schedules). Relevance-based prompt sizing with a `describe` tool (~11% of the previous dictionary prompt on a 33-source test). Business playbooks. Hard sensitive-field and blocked-DocType rules. Approvals and "Needs you". Saved chats and projects with retention. Security-review fixes (Link values must be readable, undeclared filter keys dropped, statement-timeout restore, report run limit). Fixed: BI Builder ignored the first data-source pick. |
| **3.0.0** | 2026-11-02 | BI engine with permission-aware joins, aggregates, date parts, formulas, having and pivots. BI Builder with AI build/edit. Dashboards with shared period/company filters and drag layout. Scheduled e-mails (Excel/PDF/CSV), PDF export with charts, Neotec AI workspace. Security-review fixes (parent/child permission tying, join-key field permissions, formula hardening, recipient rules). |
| **2.1.0** | 2026-11-02 | Sample field meanings (library, generated, AI-suggested). About 280 scoped sample questions. Reports in chat with chart/table switching, Excel/CSV/image/print export and saving. |
| **2.0.0** | 2026-11-02 | Rebuilt for Frappe v15: correct module layout and packaging, Data Dictionary with permission-checked queries, field-safe document context, HTML sanitising, Neotec AI User role, rate limit, multi-turn chat, log retention, Test Connection, provider-specific model defaults. |
| **1.0** | before 2026-11 | Original single-file package: single-turn chat with keyword look-ups. Superseded by 2.0 (fresh install required). |

## Compatibility

Written for Frappe v15 (Python 3.10+). `pyproject.toml` allows v15–v16; v16 has not been tested yet.

Support: support@neotec.ai
