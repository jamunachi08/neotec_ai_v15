# Neotec AI — Coworkers Administrator Guide

## How a request flows

1. A user writes in the chat (or a routine fires, or an MCP client calls).
2. A background job builds the context: the coworker's role and instructions, company instructions,
   the user's roles, remembered facts, the document the chat was opened from, and the recent messages.
3. The model answers or asks for tools.
4. Each tool call passes the **gateway**:

   | Check | Outcome when it fails |
   |---|---|
   | Coworker is granted the tool (and the tool is enabled) | Refused |
   | Residency: sensitive DocType with an external provider in Guarded mode | Refused |
   | Policy rules (Deny → Require Approval → Allow) | Refused or waits for approval |
   | Grant mode (Default / Auto / Ask) | Waits for approval |
   | Audit row written and committed | Nothing runs |

5. The tool runs **as the user**, with ERPNext permissions, inside a savepoint (rolled back on error).
6. The result is recorded and returned to the model; the loop continues until it answers.

## Grant modes

| Mode | Reading tools | Tools that change data |
|---|---|---|
| Default | Run | Ask the user first |
| Auto | Run | Run (policies still apply) |
| Ask | Ask first | Ask first |
| Off | Not available | Not available |

## Policy rules

Fields: Effect, Tool Pattern (glob; comma-separated allowed), Only for DocType, Only for Coworker,
Only when started by (Chat, Form, Routine, MCP), Only for users with Role, Condition, Approver Role.

Deny beats Require Approval, which beats Allow. A condition that raises an error counts as matched for
Deny and Require Approval rules, so a broken rule refuses rather than opens.

Names available in a condition: `tool`, `args`, `doctype`, `is_write`, `risk`, `user`, `roles`,
`coworker`, `initiator`, `flt`, `cint`, `getdate`, `nowdate`.

Examples:

```python
# Rule "Sales orders need a Sales Manager": effect Require Approval, approver Sales Manager
doctype == "Sales Order"
# Rule that applies only on Saudi working days (Sunday to Thursday)
getdate(nowdate()).weekday() in (6, 0, 1, 2, 3)
# Keep one coworker away from item masters
coworker == "Sales Assistant" and doctype == "Item"
```

### Starter KSA policy pack

| Rule | Effect |
|---|---|
| Never submit documents | Deny `submit_document` |
| Routines cannot change data | Deny writes (except notifications) when started by Routine |
| No changes to sensitive HR records | Deny drafts on Employee, Salary Slip, Payroll… |
| External e-mail needs an approver | Require approval by Coworker Approver |
| Payments and journals need finance approval | Require approval by Accounts Manager |
| MCP clients ask before any change | Require approval for writes from MCP |
| Notifications run without asking | Allow `notify_user` |

## Data residency (PDPL)

* **Provider data location**: External, In Kingdom (KSA) or On-Premises, set per provider.
* **Residency mode** (Coworker Settings):
  * *Guarded* (default): DocTypes listed under *Sensitive DocTypes* are never read for an External
    provider, and document context from them is withheld.
  * *Strict*: External providers cannot be used at all.
  * *Open*: no residency checks.
* **Masking**: with an External provider, national ID / Iqama numbers, Saudi IBANs, card numbers
  (Luhn-checked), Saudi mobile numbers and e-mail addresses are masked in everything sent to the model.
  Secrets are always masked in the audit trail.

## Open models and the self-test

Open-weight models run on your own GPU server and connect through the *Ollama (self-hosted)* or *vLLM
(self-hosted)* presets. On the provider: **Find models on this server** lists what is installed, **Open models
guide** shows the catalogue, and **Test tool calling** runs the self-test. Playbooks refuse a provider whose
model failed it. Details in [OPEN_MODELS.md](OPEN_MODELS.md); the server kit is in `deploy/gpu-server/`.

## Audit trail

`Coworker Action Log` is append-only: written by the gateway, never editable or deletable from the UI.
Retention is set in days (0 keeps everything, recommended for NCA ECC evidence). Approvals are kept too.

## Coworkers

Edit under **AI Coworker**: job title (EN/AR), description, instructions, starter prompts, provider
override, temperature, granted tools, allowed roles, knowledge and memory switches, max steps.
**Grant all read-only tools** adds every built-in reading tool in one click.

## Built-in tools

| Category | Tools |
|---|---|
| Data | describe_doctype, search_documents, get_document, count_documents, aggregate, list_reports, run_report, global_search, current_user |
| Finance | receivables_aging, payables_due, sales_summary, sales_by_item, cash_position |
| Stock | stock_levels, low_stock |
| KSA Compliance | ksa_vat, ksa_validate_vat_number, ksa_validate_iban, ksa_end_of_service, ksa_invoice_check |
| Knowledge / Memory | search_knowledge, remember_fact |
| Interface | render_ui |
| Actions (change data) | create_draft_document, update_draft_document, add_comment, create_todo, notify_user, send_email, submit_document |
| Actions (read) | approval_status |
| Automation | list_playbooks, run_playbook, get_run, signals_check, signals_record |

## Knowledge base

Add a **Coworker Knowledge** record per policy or manual: paste text, or attach .txt, .md, .csv or .pdf.
Text is split into passages and indexed with Arabic normalisation (diacritics, alef/ya/ta-marbuta forms,
the definite article, Arabic-Indic digits). Limit a document to one coworker with *Only for Coworker*.

## Routines

Fields: coworker, run as, frequency (15 minutes floor, hourly, daily, weekly, monthly, cron), instruction,
delivery (bell, e-mail, chat webhook). A user may only create routines that run as themselves. After the
configured number of consecutive failures the routine switches itself off and tells its owner.

**Runs** selects what the routine does: *Prompt* (an instruction, as in 1.0), *Playbook* or *Chain*, with an
optional parameter. **Also deliver to** adds channels.

## Automation

### Playbooks

A playbook is a named task for one coworker. It never gets more than that coworker's grants.

| Field | Meaning |
|---|---|
| Mode | *Read Only* removes every tool that changes data. *Draft Changes* keeps them, under policy and approvals. |
| Parameter label / default | One value passed at run time, e.g. a warehouse or a number of days. |
| Instructions | The task. `{parameter}` and `{today}` are replaced at run time. |
| Required tools | Checked daily against the coworker's grants. |
| Stay silent when nothing is new | A run that answers NOTHING_TO_REPORT delivers nothing. |
| Do not repeat findings for (days) | Findings already reported in this window are left out. |
| Show the coworker its previous result | It compares and says what changed. |
| Max steps / tool calls / tokens | Per-run limits. Raise tool calls for sweeps over many documents. |

Every result starts with a severity: *info*, *success*, *warn* (act this week) or *critical* (act today).
Channels use it to decide who is told.

**Who can change data.** Runs started by a person (Run now, chat, MCP) use the initiator *Chat* or *MCP*, so
writes go through approvals. Runs started by routines, triggers and chains use the initiator *Routine*: the
starter rule *Routines cannot change data* refuses writes and nothing waits for approval. To let an automated
playbook create drafts, narrow that rule's condition deliberately.

**Dry run** executes reads and refuses every write, telling the coworker to describe exactly what it would do.

### Chains

Steps run one after another, each as its own run and background job. *Use earlier results* passes the outputs
of previous steps; intermediate steps deliver only if *Deliver this step* is ticked; the last step always
delivers. *When a step fails*: Stop or Continue. Schedule a chain with a routine whose Runs is *Chain*.

### Triggers

| Field | Meaning |
|---|---|
| Document type / When | After Insert, On Update, On Submit, On Cancel. |
| Condition | Python expression on `doc`, e.g. `doc.grand_total > 100000`. Empty = always. |
| Parameter | `{name}`, `{doctype}` or any field, e.g. `{supplier}`. |
| Run as | Document Owner, Last Modified By or a fixed user. The run has that user's permissions. |
| Cooldown | The same document does not start the trigger again within this many minutes. |

The run opens with the document as context. Changes made by a coworker never fire triggers, and a trigger
error is logged without blocking the save. **Test on a document** shows whether the condition matches and can
start the playbook. The starter trigger *Match purchase invoices on submit* ships disabled.

### Channels

Bell (users, or the person the run worked for), E-mail, Slack, Microsoft Teams (workflow webhook, Adaptive
Card), Google Chat, Telegram (bot token and chat ID) or Generic Webhook (JSON with subject, body, severity,
link). *Minimum severity* filters what each channel receives. **Send test** checks the address.

Where a result goes: a routine's own delivery settings and channels; otherwise the chain's channels; otherwise
the playbook's; with nothing configured, the bell of the person the run worked for. Failures of automated runs
are not broadcast; the health check turns repeated failures into an issue.

### Priorities, voice and providers

In Coworker Settings, *Company priorities and hard limits* is read by every coworker and playbook; keep it to a
few lines. *Voice* shapes the wording of reports. Real enforcement stays with policy rules.

*Fallback AI provider* is used when the main provider fails, and only if its location is the same or closer
(On-Premises, then In Kingdom, then External). Strict residency never falls back to an external provider.
Enter token prices on each provider (USD per million) to see estimated cost per run.

### Health

Daily, and on demand from **/app/coworker-health** (Run checks now), Neotec AI opens a *Coworker Issue*
when:

- a playbook's last N runs failed (N = *Failed runs before an issue is opened*);
- the average quality score of recent runs is below the threshold (needs *Score playbook results* and a scoring
  provider; the scoring provider must not be further away than the run's provider);
- one provider failed three runs in a day; a routine switched itself off; the monthly budget reached 80% or 100%;
- a configuration check fails: missing or disabled tool grants, disabled coworkers, users, playbooks or chains,
  triggers on DocTypes that no longer exist or with invalid conditions, a fallback that would move data
  further away, a channel whose last delivery failed, an external MCP server with no tools.

An issue is one record per problem; it closes itself when the problem is gone. Mark it *Ignored* to silence it.
Set *Send health changes to* to receive only opened and resolved issues. Automated runs and their conversations
older than *Keep run history* are removed; manual runs are kept.

### Starter packs

| Pack | Playbooks |
|---|---|
| Finance | Receivables Watch, Payables Due Soon, Cash Position Brief, Sales Pulse, Priority Brief |
| Operations | Overdue Sales Orders, Expiring Quotations, Low Stock Radar, Overdue Follow-ups, Purchase Invoice Match |
| KSA Compliance | E-Invoice Readiness Sweep, Supplier Master Hygiene, Employee Document Expiry |

Chain *Morning Finance Brief*: the four finance checks, then Priority Brief ranks the three things to act on.
Disable a whole pack under Coworker Pack. Starter records are created once and never overwritten, so edit
them freely. *Employee Document Expiry* reads Employee, a sensitive DocType: in Guarded residency it needs an
in-Kingdom or on-premises provider (set it as the playbook's provider override).

## MCP

**ERPNext as an MCP server.** Enable it in Coworker Settings and choose the coworker whose grants define
the exposed tools (default: *MCP Gateway*). Clients connect over Streamable HTTP:

```json
{
  "mcpServers": {
    "erpnext": {
      "type": "http",
      "url": "https://<site>/api/method/neotec_ai.agents.mcp.server.handle",
      "headers": { "Authorization": "token <api_key>:<api_secret>" }
    }
  }
}
```

Generate the key on the user's own User record (API Access). Calls run as that user, are treated as
coming from an external provider for residency purposes, and writes wait for approval in ERPNext.

**Playbooks over MCP.** The MCP Gateway is granted list_playbooks and get_run, and run_playbook in *Ask*
mode: an external client can start a playbook once a person approves it in ERPNext.

**External MCP servers for coworkers.** Add a *Coworker MCP Server* (https URL and auth header), press
**Discover tools**, list the read-only tools, then grant `mcp_<name>__<tool>` on an AI Coworker.

## Extending from another app

```python
# hooks.py of your app
neotec_ai_tools = ["my_app.coworker.get_tools"]
neotec_ai_before_tool = ["my_app.coworker.before_tool"]   # raise to refuse
neotec_ai_after_tool = ["my_app.coworker.after_tool"]

# my_app/coworker.py
def get_tools():
    return [{
        "name": "project_margin",
        "label": "Project margin",
        "description": "Margin of a project from its costing.",
        "parameters": {"project": {"type": "string"}, "__required__": ["project"]},
        "is_write": False, "risk": "Low",
        "fn": "my_app.coworker.project_margin",
    }]
```

Run `bench migrate` (or press nothing: tools sync on every migrate), then grant the tool on a coworker.

## Limits and costs

Coworker Settings: max steps per turn, max tool calls per turn, messages kept in context (older ones are
summarised automatically), tool result size, daily token allowance per user, approval expiry.
Playbook runs use their own limits and the monthly automation budget instead of the daily allowance.

## New in 4.0

**Routes and the call log.** *Neotec AI Route* decides which providers answer which calls (see
[PLATFORM.md](PLATFORM.md)). A coworker's own provider is always tried first, then the legacy fallback provider,
then the **Agents** route (or **Automation** for playbooks, routines and briefs). *Neotec AI Call Log* lists every
model call from every app. Set limits per provider (requests and tokens per minute and per day) under
*Coworker Provider → Limits and capabilities*.

**Chat modes.** Users switch a chat between *Standard*, *Read Only* and *Plan First* from the chat header.
Read Only and Plan First refuse every write tool; Plan First also asks the coworker for a numbered plan.

**Approve, always in this chat.** Shown only for the requester's own confirmations (no policy rule, no approver
role). It adds the tool to the chat's *Always Allowed* list; the user can clear the list from the header.
Policy rules with an approver role are never skipped.

**Tools on demand.** *Coworker Settings → Load Tools On Demand Above* (default 20). Above it a coworker starts with
the core tools and `find_tools`; matches stay loaded for the rest of the chat. Grants and policy apply as before.

**Delegation.** Grant `delegate_task` to let a coworker hand a sub-task to another coworker. One level; the delegate
runs as the same user, cannot wait for approvals and reports changes instead. Switch off with *Coworkers May
Delegate*.

**BI tools.** `list_data_sources`, `describe_data_source`, `query_data` and `save_bi_report` read the governed Data
Dictionary (Neotec Data Source). Only enabled DocTypes and fields are reachable.

**Live Briefs.** *Neotec Live Brief*: an objective, a coworker and a schedule (or a document event). Briefs always
run Read Only as their owner and record what changed. *Refresh now* on the form.

**Writing assistant.** *Neotec Settings → Writing Assistant*: choose DocTypes (or all). Add brand and product names
to *Neotec AI Glossary Term* with *Keep As Is* so they are never changed.

**Connected apps.** *Coworker Setup → Connected apps* lists apps on the site that can use this gateway and switches
them. Their tools appear under *Coworker Tool* (source Extension) and are granted once to the matching coworker.
