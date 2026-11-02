# Neotec AI Hub (`neotec_ai`)

A white-labeled AI assistant for **Frappe / ERPNext v15 and later**. Users ask business questions in plain language from any desk page; the AI looks up live data through a governed **Data Dictionary** and answers with only the data that user is allowed to see.

## What's in it

| Piece | Purpose |
|---|---|
| **Neotec Settings** | Provider (Gemini, Claude, OpenAI, OpenAI-compatible / Ollama), model, key, limits, business context, rate limit, log retention |
| **Neotec Data Source** | The Data Dictionary: one entry per DocType the AI may query, with a plain-language description and the exact fields it may use |
| **Neotec AI Report** | Reports the AI built and users saved. Opened anytime, they re-run live with the viewer's permissions |
| **Neotec Sample Question** | ~280 ready-made questions (general, per module, per DocType, per open document) shown as clickable suggestions |
| **Neotec AI Log** | Audit trail: who asked what, which queries ran, tokens, latency, errors |
| **Neotec AI User** role | Who may use the assistant and create/save reports (System Managers always can) |
| Desk chat | Navbar button + **Alt+K**, multi-turn chat, context-aware suggestions, attaches the open document as context |

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

**Upgrading from 2.0:** copy the new files over the app and run `bench --site <your-site> migrate` then `bench build --app neotec_ai`. The migration adds the new data sources, fills empty field meanings (your own text is kept) and loads the sample questions.

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
