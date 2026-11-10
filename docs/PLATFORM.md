# The Neotec AI gateway (for app developers and administrators)

Every model call can go through one gateway: the assistant, the BI builder, coworkers, automation, live briefs,
writing help and any connected app. One set of providers, one residency policy, one usage ledger.

## Calling it from another app

```python
def ai_available():
    try:
        from neotec_ai.platform import is_available
        return is_available()
    except ImportError:
        return False

from neotec_ai.platform import complete_text, complete_json, PlatformError

text = complete_text("You are a precise analyst.", "Summarise: ...",
                     app="my_app", feature="summary", reference=("Sales Invoice", name))
data = complete_json(system, user, app="my_app", feature="classify", schema={...})
```

`complete()` returns a `Completion` (text, tool_calls, tokens_in, tokens_out, provider, model, fell_back,
attempts, saved_chars, route). Useful keyword arguments:

| Argument | Meaning |
|---|---|
| `app`, `feature`, `purpose` | Pick the route: "app:feature" → "app" → purpose → Default |
| `reference` | (doctype, name). A sensitive DocType keeps the call off External providers in Guarded mode |
| `sensitive` | Force the sensitive treatment |
| `images` | `[{"data": base64, "media_type": "image/png"}]`; only providers marked Reads Images are used |
| `json_mode`, `schema` | Structured output where the provider supports it, plus a JSON instruction |
| `provider`, `fallbacks` | Try these first, then the route |
| `max_tokens`, `temperature`, `timeout` | Per call |
| `mask`, `compress_mode` | Override the governance defaults |

Errors: `PlatformBlocked` (switched off, no provider, budget used, residency) and `PlatformError` (every
provider failed). Both carry a message that is safe to show.

## Offering tools to coworkers

```python
# hooks.py
neotec_ai_tools = ["my_app.ai.coworker_tools"]

# my_app/ai.py
def coworker_tools():
    return [{
        "name": "my_app_pipeline", "label": "Pipeline value",
        "description": "Open pipeline value by stage.", "category": "Finance",
        "parameters": {"company": {"type": "string"}, "__required__": []},
        "fn": "my_app.ai.pipeline", "is_write": False, "risk": "Low",
        "grant_to": {"Sales Assistant": "Default"},   # granted once on migrate
    }]
```

Tools run as the user, inside a savepoint, through policy, residency and the audit trail.

## A switch in Coworker Setup

```python
neotec_ai_integrations = ["my_app.ai.neotec_integration"]

def neotec_integration():
    return {"app": "my_app", "label": "My App", "description": "Send My App's AI calls through Neotec AI.",
            "settings_doctype": "My App Settings", "field": "ai_engine",
            "on_value": "Neotec AI", "off_value": "Built-in"}
```

## Routes

| Route | Used by |
|---|---|
| Default | anything without a more specific route |
| Agents | coworker chats, after the coworker's own provider |
| Automation | playbooks, routines, chains, live briefs |
| Assistant | the Alt+K assistant and the BI builder (also matches "BI") |
| Writing | writing help |
| Vision | image reading; add providers marked Reads Images |

Add a route named after an app (`my_app`) or `my_app:feature` to give that app its own providers or budget.
An empty route falls back to the default chain.

## Order, fallback and residency

The first eligible provider sets the floor: a later provider is used only if it keeps data at least as close.
Strict: never External. Guarded: External providers do not see calls about sensitive DocTypes (Coworker
Settings → Sensitive DocTypes). Providers resting after an error go to the end of the chain.
