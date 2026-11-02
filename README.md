# Neotec AI Hub (`neotec_ai`)

A white-labeled AI assistant for **Frappe / ERPNext v15 and later**. Users ask business questions in plain language from any desk page; the AI looks up live data through a governed **Data Dictionary** and answers with only the data that user is allowed to see.

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
| **Neotec AI Log** | Audit trail: who asked what, which queries ran, tokens, latency, errors |
| **Neotec AI User** role | Who may use the assistant and build/save reports, dashboards and schedules (System Managers always can) |
| Desk chat | Navbar button + **Alt+K**, multi-turn chat, context-aware suggestions, attaches the open document as context |
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

1. The system prompt lists the Data Dictionary entries the current user can read (plus your Business Context text).
2. When the model needs data it replies with a JSON *query plan* (DocType, fields, aggregates, filters, group-by, order, limit) — never SQL.
3. Each plan is validated against the dictionary: only listed DocTypes and enabled fields, a fixed set of operators, aggregate and date functions; row and size caps.
4. The query runs through `frappe.get_list` **as the current user**, so role permissions, User Permissions (company, territory, etc.) and field-level permissions apply.
5. Results go back to the model (up to *Max Query Rounds* times), and it answers. The chat shows which data sources were consulted.

Submittable DocTypes default to submitted records only. Child tables (e.g. Sales Invoice Item) use the parent's permissions.

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

**Upgrading from 2.x:** copy the new files over the app and run `bench --site <your-site> migrate`, then `bench build --app neotec_ai` and `bench restart`. Migration adds the BI pages, dashboards, schedules and workspace, gives the Neotec AI User role access to them, adds new data sources, fills empty field meanings (your own text is kept) and loads the sample questions. Reports saved in 2.x keep working and open in the BI Builder. Make sure the scheduler is enabled (`bench --site <your-site> enable-scheduler`) for scheduled e-mails.

## Set up

1. **Neotec Settings** → choose the provider, confirm the **Model ID** against your provider's current model list, paste the API key, Save, then **Test Connection**.
2. Fill in **Business Context & Glossary**: what the company does, base currency, fiscal year, what "revenue" or "active customer" means to you, internal abbreviations. This noticeably improves answers.
3. Review **Neotec Data Source** entries. For each: write what the data means, untick fields you don't want exposed, add field meanings ("base_grand_total = invoice total in company currency"). Add new DocTypes (including custom ones) with **Load Fields**.
4. Give the **Neotec AI User** role to the people who should use it.

## Data and privacy notes

- Question text, the readable fields of the open document, and query results are sent to the AI provider you configure. For data that must not leave your network, use an OpenAI-compatible local server (e.g. Ollama).
- Only expose fields you're comfortable sending to that provider. Password, attachment, signature and code fields cannot be exposed.
- Logs store the queries that ran; turning on *Store Query Results in Logs* stores the returned rows too. Logs are purged after *Keep Logs for (days)*.

## Compatibility

Written for Frappe v15 (Python 3.10+). `pyproject.toml` allows v15–v16; v16 has not been tested yet.

Support: support@neotec.ai
