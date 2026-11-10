# Installing Neotec AI 4

Frappe / ERPNext v15 and v16. Runs entirely inside the site, so it installs on Frappe Cloud with no extra
servers. Requires ERPNext.

## Frappe Cloud

1. Push this repository to GitHub (private is fine), e.g. `jamunachi08/neotec_ai`.
2. **Bench group → Apps → Add App → From GitHub**, choose the repository and the branch.
3. **Deploy** the bench group.
4. **Sites → your site → Apps → Install App → Neotec AI**. Installing creates the roles, the starter coworkers,
   policies, playbooks, routes and the Data Dictionary. System Managers get Coworker Admin, User and Approver.
5. Open **/app/coworker-setup**: connect a provider, choose coworkers, set residency, switch on connected apps.

Upgrading a site that runs Neotec AI 3.x: deploy and migrate. The assistant's provider settings become a
Coworker Provider automatically. Sites that run Neotec Coworker 1.x: see [MIGRATION.md](MIGRATION.md).

## Bench

```sh
bench get-app https://github.com/<you>/neotec_ai
bench --site <site> install-app neotec_ai
bench --site <site> migrate
bench build --app neotec_ai
```

## After installing

| Where | What |
|---|---|
| /app/coworker-setup | Provider, coworkers, governance, connected apps, health |
| /app/coworker | Chat with coworkers (also **Ask Coworker** on every form, Ctrl+Shift+K) |
| Alt+K | The assistant drawer (Data Dictionary questions, reports and charts) |
| /app/neotec-bi, /app/neotec-dashboard | BI Builder and dashboards |
| Neotec AI Route | Which providers answer which calls, in what order |
| Neotec AI Call Log | Every model call from every app |
| Neotec Live Brief | Self-updating briefs |
| Neotec Settings → Writing Assistant | ✦ writing help on text fields |

## Roles

| Role | Can |
|---|---|
| Neotec AI User | Use the assistant, BI Builder, dashboards, schedules, writing help |
| Coworker User | Chat with the coworkers their roles allow; create live briefs |
| Coworker Approver | Approve actions coworkers request |
| Coworker Admin | Providers, routes, coworkers, policies, audit trail |

Data access always follows the user's own ERPNext permissions.

## Checks before a push

```sh
python verify_tree.py
python -m pytest tests -q
```
