import frappe
from frappe import _
from frappe.model.document import Document

# Suggested starting models. Provider catalogs change often - verify against the provider.
SUGGESTED_MODELS = {
    "Google Gemini": "gemini-flash-latest",
    "Anthropic Claude": "claude-sonnet-5-5",
    "OpenAI": "gpt-5-mini",
    "OpenAI-Compatible / Ollama": "llama3.1",
}


class NeotecSettings(Document):
    def validate(self):
        if not self.model:
            self.model = SUGGESTED_MODELS.get(self.provider)

        self.max_tokens = max(256, min(self.max_tokens or 2048, 32000))
        self.max_records_fetch = max(1, min(self.max_records_fetch or 50, 500))
        self.max_report_rows = max(10, min(self.max_report_rows or 500, 5000))
        self.max_query_rounds = max(1, min(self.max_query_rounds or 3, 6))
        self.max_context_chars = max(2000, min(self.max_context_chars or 20000, 200000))
        self.request_timeout = max(10, min(self.request_timeout or 60, 300))
        if self.temperature is not None and not (0 <= self.temperature <= 2):
            frappe.throw(_("Temperature must be between 0 and 2."))

        if self.api_endpoint and not self.api_endpoint.startswith(("http://", "https://")):
            frappe.throw(_("API Base URL must start with http:// or https://"))

        if self.enable_ai and self.provider != "OpenAI-Compatible / Ollama" and not self.api_key:
            frappe.msgprint(_("API Key is empty. This provider needs a key."), indicator="orange", alert=True)


@frappe.whitelist()
def get_suggested_model(provider):
    frappe.only_for("System Manager")
    return SUGGESTED_MODELS.get(provider)
