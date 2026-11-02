app_name = "neotec_ai"
app_title = "Neotec AI Hub"
app_publisher = "Neotec AI Solutions"
app_description = "White-labeled AI business assistant for Frappe / ERPNext with a governed data dictionary"
app_email = "support@neotec.ai"
app_license = "mit"

# Desk assets (Frappe v15+). Bundled files are built by `bench build`.
app_include_js = "/assets/neotec_ai/js/neotec_ai.js"
app_include_css = "/assets/neotec_ai/css/neotec_ai.css"

# Install / migrate
after_install = "neotec_ai.install.after_install"
after_migrate = "neotec_ai.install.after_migrate"

# Housekeeping
scheduler_events = {
    "daily": [
        "neotec_ai.tasks.purge_old_logs",
    ],
}
