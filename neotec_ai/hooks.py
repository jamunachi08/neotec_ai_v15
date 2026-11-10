# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
app_name = "neotec_ai"
app_title = "Neotec AI"
app_publisher = "Neotec Integrated Solutions"
app_description = ("One governed AI platform for ERPNext: assistant, BI builder, coworkers with approvals and audit, "
                   "automation, live briefs, writing help, and a shared AI gateway for other apps.")
app_email = "support@neotec.ai"
app_license = "Proprietary"
app_logo_url = "/assets/neotec_ai/images/logo.svg"

add_to_apps_screen = [
    {
        "name": "neotec_ai",
        "logo": "/assets/neotec_ai/images/logo.svg",
        "title": "Neotec AI",
        "route": "/app/coworker",
    }
]

# Desk assets
app_include_js = [
    "/assets/neotec_ai/js/neotec_bi.js",
    "/assets/neotec_ai/js/neotec_ai.js",
    "/assets/neotec_ai/js/coworker_launcher.js",
    "/assets/neotec_ai/js/coworker_models.js",
    "/assets/neotec_ai/js/neotec_writing.js",
]
app_include_css = ["/assets/neotec_ai/css/neotec_ai.css", "/assets/neotec_ai/css/coworker.css"]

# Install / migrate
before_install = "neotec_ai.install.before_install"
after_install = "neotec_ai.install.after_install"
before_migrate = "neotec_ai.install.before_migrate"
after_migrate = "neotec_ai.install.after_migrate"
# Moving from the separate Coworker app: keep its records when it is uninstalled.
before_app_uninstall = "neotec_ai.agents.takeover.before_app_uninstall"

boot_session = ["neotec_ai.agents.boot.boot_session", "neotec_ai.writing.boot_session"]

scheduler_events = {
    "cron": {
        "*/5 * * * *": ["neotec_ai.agents.routines.tick", "neotec_ai.briefs.tick"],
    },
    "hourly": [
        "neotec_ai.bi.schedule.run_due",
    ],
    "daily": [
        "neotec_ai.tasks.purge_old_logs",
        "neotec_ai.platform.gateway.purge_call_logs",
        "neotec_ai.agents.engine.gateway.expire_approvals",
        "neotec_ai.agents.engine.gateway.purge_old_logs",
        "neotec_ai.agents.automation.health.daily",
    ],
}

# Triggers and live briefs: one cached lookup per save; only DocTypes with an enabled trigger go further.
doc_events = {
    "*": {
        "after_insert": ["neotec_ai.agents.automation.triggers.on_event", "neotec_ai.briefs.on_event"],
        "on_update": ["neotec_ai.agents.automation.triggers.on_event", "neotec_ai.briefs.on_event"],
        "on_submit": ["neotec_ai.agents.automation.triggers.on_event", "neotec_ai.briefs.on_event"],
        "on_cancel": ["neotec_ai.agents.automation.triggers.on_event", "neotec_ai.briefs.on_event"],
    }
}

# ------------------------------------------------------------------ extension points (see docs/PLATFORM.md)
# Other apps call the shared gateway:   from neotec_ai.platform import complete_text, complete_json
# and may declare, in their own hooks.py:
#   neotec_ai_tools = ["my_app.ai.get_tools"]                -> list of tool dicts for coworkers
#   neotec_ai_before_tool = ["my_app.ai.before_tool"]        -> raise to refuse a tool call
#   neotec_ai_after_tool = ["my_app.ai.after_tool"]
#   neotec_ai_integrations = ["my_app.ai.integration"]       -> dict: settings switch shown in Neotec AI setup
