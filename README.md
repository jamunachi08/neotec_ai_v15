# Neotec AI

One governed AI platform for ERPNext: an assistant, a BI builder, AI coworkers with approvals and an audit
trail, automation, live briefs and writing help, all behind one gateway that other apps on the site can use.
Built for Saudi Arabia: Arabic and English, PDPL residency controls, KSA compliance calculators.

| | |
|---|---|
| Version | 4.0.0 |
| Frappe / ERPNext | v15 and v16 |
| Publisher | Neotec Integrated Solutions |
| Licence | Proprietary (see license.txt) |

Neotec AI 4 merges Neotec AI Hub 3.1 and Neotec Coworker 1.2.1. Sites running either upgrade in place;
see [docs/MIGRATION.md](docs/MIGRATION.md) for Coworker sites.

## What users get

- **Coworkers** at `/app/coworker`: General Assistant, Finance Analyst, Sales Assistant, Procurement Checker,
  HR & Labor Law Advisor, Inventory Watch and Knowledge Desk. KPI tiles, tables, charts and document lists in the
  answer; **Ask Coworker** on every form. Chat modes: Standard, Read Only, Plan First.
- **Approvals in the chat**: a coworker that wants to change data waits for *Approve and run* (or
  *Approve, always in this chat* for the user's own confirmations).
- **Assistant** (Alt+K) answering from the governed Data Dictionary, with report cards that can be exported,
  saved, scheduled and added to dashboards.
- **BI Builder and dashboards** with an AI bar.
- **Live Briefs** that keep themselves current on a schedule or when a document changes.
- **Writing help** (✦) on long text fields: spelling, Arabic ↔ English translation, improve, formal, shorter.
- **Automation**: playbooks, chains, triggers and routines delivered to the bell, e-mail, Teams, Slack, Google Chat.

## What administrators control

- **Providers** (Gemini, OpenAI, Claude, Azure OpenAI, self-hosted open models via Ollama or vLLM, NeotecAI)
  with data location, limits, tool-calling self-test and image support.
- **Routes**: which providers answer which app or feature, in what order, with monthly budgets.
- **Residency**: Guarded keeps sensitive DocTypes off External providers; Strict blocks them; personal data is
  masked (reversibly) before leaving.
- **Policies**: deny-first rules by tool, DocType, coworker, role, channel or condition; approver roles with
  segregation of duties.
- **Audit**: every tool call (Coworker Action Log) and every model call from every app (Neotec AI Call Log).
- **Connected apps**: other Neotec apps switch to this gateway with one click in Coworker Setup.
- **MCP**: expose ERPNext to external AI clients through the same rules, or plug external MCP tools in.

## Documentation

- [Installation](docs/INSTALL.md) · [Moving from Coworker 1.x](docs/MIGRATION.md)
- [Gateway and extension points](docs/PLATFORM.md) · [Coworkers administrator guide](docs/ADMIN_GUIDE.md)
- [Open models](docs/OPEN_MODELS.md) and the GPU server kit in `deploy/gpu-server/` · [دليل البدء السريع](docs/QUICK_START_AR.md)

## Development checks

```sh
python verify_tree.py        # structure, links, hooks, grants, names, version
python -m pytest tests -q    # gateway, masking, compression, routing, policy, KSA calculators, tools
```
