# Changelog — Neotec AI

## 4.0.0 — 2026-11-10

**One AI app for ERPNext.** The assistant and BI builder (Neotec AI 3.1) and the governed coworkers (Neotec
Coworker 1.2.1) are now a single app, with a shared AI gateway that other apps on the site can use.

### Shared AI gateway (new)
- **Routes** (Neotec AI Route): named, ordered provider lists. A call is matched by app and feature, then app,
  then purpose (Agents, Automation, Assistant, Writing, Vision), then Default. Six standard routes are created.
- **Fallback that respects residency**: the next provider in a route is used only if it keeps data at least as
  close as the first (On-Premises < In Kingdom < External). Strict mode never uses External providers; Guarded
  mode keeps calls about sensitive DocTypes off them.
- **Quotas and cool-downs**: requests and tokens per minute and per day on each Coworker Provider. A provider
  that answers with a rate limit or server error rests (30 s, 2 min, 10 min, 30 min, 1 h) and the next one answers.
- **Reversible masking**: e-mail, Saudi mobile, national ID / iqama, IBAN and card numbers are replaced by
  placeholders before an External provider sees them and restored in the answer and in tool-call arguments.
- **Prompt compression** (Lossless default): record lists sent as column/row tables, repeated blocks pointed to,
  and (Standard) older duplicate tool results superseded. A fidelity gate discards any change that loses a
  number, document name or error line. The user's question is never altered.
- **Neotec AI Call Log**: one row per model call from every app (route, provider, tokens, latency, fallback,
  masking, characters saved). Monthly token budget per route.
- **Images**: OpenAI-compatible and Anthropic providers can read images (Reads Images flag, Vision route).
- **Public API** for other apps: `neotec_ai.platform.complete_text / complete_json / is_available`.
- **Connected apps**: apps declare a one-click switch (`neotec_ai_integrations` hook) shown in Coworker Setup.

### Coworkers
- **Chat modes**: Standard, Read Only (no changes) and Plan First (investigate and propose a numbered plan).
- **Approve, always in this chat**: remembers the user's own confirmation for one tool in one conversation.
  Approvals required by a policy rule or an approver role are never skipped (segregation of duties).
- **Tools on demand**: a coworker with more tools than the threshold (default 20) starts with core tools and
  loads the rest with `find_tools`; grants are still checked on every call.
- **Delegation** (`delegate_task`): hand a self-contained sub-task to another coworker. One level only; the
  delegate cannot wait for approvals and reports changes instead.
- **Row-aware result fitting**: long tool results keep whole rows and say how many were left out.
- **BI tools**: `list_data_sources`, `describe_data_source`, `query_data`, `save_bi_report` use the governed
  Data Dictionary, so coworkers and the assistant answer from the same definitions.
- Extension tools may set `category` and `grant_to`; grants are added once on upgrade and never re-added.

### New
- **Live Briefs** (Neotec Live Brief): an objective plus a coworker; refreshed hourly, daily, weekly, by cron
  or when a chosen document changes; read-only; records what changed since the last version.
- **Writing assistant**: ✦ on long text fields of chosen DocTypes (or all): fix spelling (Arabic and English),
  translate Arabic ↔ English, improve, formal, shorter. Preview first, glossary names protected, number check.

### Assistant (Alt+K) and BI
- Model calls go through the gateway. On upgrade the 3.x provider, model and key in Neotec Settings become a
  Coworker Provider ("Assistant (…)") linked as Assistant Provider. Gemini moves to its OpenAI-compatible
  endpoint. The direct connection remains only for sites with no provider at all.

### Moving from Neotec Coworker 1.x
- Install 4.0 alongside, migrate, then uninstall `neotec_coworker`. Its 27 DocTypes and 3 pages are moved to
  the module "Neotec AI Agents" first, so every record stays. While both are installed, 4.0's coworker jobs and
  triggers stand aside. See docs/MIGRATION.md.
- MCP endpoint is now `/api/method/neotec_ai.agents.mcp.server.handle` (updated in settings automatically;
  update external MCP clients).
- Hook names are now `neotec_ai_tools`, `neotec_ai_before_tool`, `neotec_ai_after_tool`;
  `neotec_coworker_tools` is still read.

---

## Earlier history: Neotec AI Hub 3.x

- 3.1.0 (2026-11-03): ERPNext reports for the AI, playbooks, saved chats and projects, approvals ("Needs you").
- 3.0 and earlier: BI Builder, dashboards, report schedules, Data Dictionary with field meanings, sample questions.

## Earlier history: Neotec Coworker 1.x
### 1.2.1 — 2026-11-08

- **Fix: Gemini "Function call is missing a thought_signature" (HTTP 400).** Gemini thinking models attach a
  thought signature to function calls through the OpenAI-compatible endpoint and reject the next request unless
  it is sent back. Signatures are now stored with each tool call and returned unchanged to Google endpoints
  only; older history without one gets Google's documented placeholder, so existing conversations continue.
  Other providers never receive the field. Signatures are not sent to the browser.


### 1.2.0 — 2026-11-08

Open models: run Qwen, gpt-oss, Gemma, Llama, Mistral and other open-weight models on your own GPU server.

- **Open models guide**: a catalogue of open-weight models with licence, GPU size, Arabic quality and what each
  is suitable for (coworkers, light use, data centre). Open it from any provider or the setup wizard.
- **Find models on this server**: lists the models installed on an Ollama, vLLM or other OpenAI-compatible
  server, labels the ones the catalogue knows, and fills in the model id with one click.
- **Tool-calling self-test** on every provider: four checks (right tool and argument, answers from the result,
  Arabic request, no tool when none is needed). Passed, Partial or Failed. Playbooks refuse a provider that
  failed, a failed provider is never used as fallback, and changing the model resets the result.
- **New presets**: Ollama (self-hosted), vLLM (self-hosted), and a hosted router for open models, whose free
  models are labelled and always treated as External.
- **Health checks**: providers in use that failed or never ran the self-test; providers on a free hosted tier.
- **GPU server kit** (`deploy/gpu-server/`): Docker Compose with an Ollama or vLLM profile behind Caddy with
  TLS and an API key, a check script and a setup guide.
- docs/OPEN_MODELS.md (English and Arabic).


### 1.1.0 — 2026-11-01

Automation: coworkers now do recurring work on their own, safely, and report only what is new.

- **Playbooks** (Coworker Playbook): reusable tasks with a parameter, a mode (Read Only removes every write
  tool; Draft Changes stays under policy and approvals), optional provider override, and per-playbook limits
  for steps, tool calls and tokens. Run now from the form, with a dry run that changes nothing.
- **Output contract**: every result starts with a severity (info, success, warn, critical) or is exactly
  NOTHING_TO_REPORT, in which case the run stays silent. The coworker sees its previous result and says what
  changed.
- **No repeated findings**: playbooks record what they reported (Coworker Signal) and skip it for a
  configurable number of days.
- **Run history** (Coworker Run): status, severity, output, duration, tokens, estimated cost, tool calls,
  refused calls, delivery and quality score, linked to the full conversation.
- **Chains** (Coworker Chain): playbooks in sequence, each step its own background job (no worker time-outs);
  later steps read earlier results. Stop or continue on error.
- **Triggers** (Coworker Trigger): start a playbook after insert, on update, on submit or on cancel, with a
  Python condition, a parameter template and a cooldown per document. Changes made by coworkers never fire
  triggers; a trigger error never blocks the user's save. Test on a document from the form.
- **Channels** (Coworker Channel): bell, e-mail, Slack, Microsoft Teams (Adaptive Card), Google Chat,
  Telegram or a generic webhook, each with a minimum severity and a Send test button.
- **Routines** can now run a prompt, a playbook or a chain, and deliver to channels as well.
- **Company priorities and hard limits**, and a **voice** for reports, in Coworker Settings.
- **Fallback AI provider**, used only when it keeps data at least as close as the main one.
- **Monthly automation token budget**; issues at 80% and 100%.
- **Quality scoring** of results by a small model, under the same residency rule.
- **Health** (Coworker Issue, daily): issues for repeated failures, low quality, failing providers, budget
  and about 20 configuration checks (missing tool grants, disabled users or playbooks, triggers on DocTypes
  that no longer exist, unsafe fallback, failing channels). Issues close themselves when fixed; only changes
  are sent to the health channel. Old automated runs are purged after the retention period.
- **Coworker Health page** (/app/coworker-health): headline status, what needs attention, run history per
  playbook, cost and budget.
- **New tools**: list_playbooks, run_playbook, get_run (chat and MCP; over MCP, starting a run needs approval),
  signals_check, signals_record (granted to playbook runs automatically).
- **Starter packs**: Finance (Receivables Watch, Payables Due Soon, Cash Position Brief, Sales Pulse, Priority
  Brief), Operations (Overdue Sales Orders, Expiring Quotations, Low Stock Radar, Overdue Follow-ups, Purchase
  Invoice Match), KSA Compliance (E-Invoice Readiness Sweep, Supplier Master Hygiene, Employee Document
  Expiry); the Morning Finance Brief chain; a purchase-invoice trigger (disabled); a bell channel.
- Automated run conversations no longer crowd the chat list; open them from the run.
- Upgrade patch grants the new tools to General Assistant and MCP Gateway on existing sites.
- verify_tree.py now checks starter playbooks against coworker grants and patches against files.


### 1.0.0 — 2026-10-28

First release of Coworker.

- Coworkers: seven starter coworkers (General, Finance, Sales, Procurement, HR & Labor Law, Inventory,
  Knowledge) plus an MCP Gateway service coworker. Bilingual titles and starter prompts.
- Governance gateway: grant check, data-residency guard, deny-first policy rules, approvals with
  segregation of duties, append-only audit trail written before any action runs.
- Providers: OpenAI-compatible (Gemini, OpenAI, Groq, Ollama, vLLM, NeotecAI), Anthropic, Azure OpenAI.
- 32 built-in tools: generic data, finance, stock, KSA compliance (VAT, VAT number, IBAN,
  end-of-service, e-invoice readiness), knowledge, memory, visual answers and draft-only actions.
- Visual answers: KPI tiles, tables, charts, document lists, forms and quick actions.
- Knowledge base with Arabic-aware search and citations; personal memory.
- Routines with bell, e-mail and Teams / Slack / Google Chat delivery; auto-disable after failures.
- MCP server endpoint (ERPNext as governed tools) and MCP client (external tools for coworkers).
- Setup wizard, health check, "Ask Coworker" on every form, Ctrl+Shift+K shortcut.
