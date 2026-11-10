# Moving a site from Neotec Coworker 1.x to Neotec AI 4

Neotec AI 4 contains everything Neotec Coworker 1.2.1 did. The coworker DocTypes keep their names
(AI Coworker, Coworker Provider, Coworker Conversation …), so conversations, runs, approvals, audit trail,
knowledge, memory, playbooks, triggers, routines and channels all stay exactly where they are.

## Steps (Frappe Cloud)

1. **Take a backup** of the site (Site → Backups → Schedule backup, with files).
2. Add `neotec_ai` 4.0 to the bench group and deploy. Keep `neotec_coworker` on the bench for now.
3. Install **Neotec AI** on the site (or, if 3.x is already installed, just let the deploy migrate it).
4. Open **/app/coworker-setup → Connected apps**. It should say *All coworker records now belong to Neotec AI*.
   If it lists anything still moving, run **Migrate** once more.
5. **Uninstall Neotec Coworker** from the site (Site → Apps → … → Uninstall). Neotec AI claims the records again
   just before the uninstall, so nothing is dropped.
6. Remove `neotec_coworker` from the bench group and deploy.
7. External MCP clients: change the URL to `/api/method/neotec_ai.agents.mcp.server.handle`.

## What happens during the overlap

Between steps 3 and 5 both apps are installed. Neotec AI's own routines, triggers, health job and the
"Ask Coworker" button stand aside while the old app is present, so nothing runs twice. Keep the overlap short
(the same day).

## Why nothing is lost

Uninstalling an app deletes the DocTypes of *its modules*. On every migrate, on install and just before the
old app is uninstalled, Neotec AI moves the 27 coworker DocTypes and 3 pages to its own module
"Neotec AI Agents" and re-imports their current definitions. The old module then owns nothing.

## If something goes wrong

Restore the backup from step 1. To check the move by hand, in System Console:

```python
frappe.get_all("DocType", filters={"module": "Neotec Coworker"}, pluck="name")   # must be []
from neotec_ai.agents import takeover; takeover.status()
```
