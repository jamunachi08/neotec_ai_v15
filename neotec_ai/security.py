"""Hard limits on what Neotec AI may ever send to an AI provider.

These apply on top of the Data Dictionary and Frappe permissions, and cannot be switched off by
configuration: an administrator can only *add* to them (Neotec Settings > Extra Sensitive Fields).
"""

import re

import frappe

# Exact field names that are never exposed, on any DocType.
SENSITIVE_FIELDNAMES = frozenset({
    "password", "new_password", "old_password", "pwd", "passwd",
    "api_key", "api_secret", "secret", "secret_key", "client_secret", "private_key", "encryption_key",
    "access_token", "refresh_token", "auth_token", "token", "otp", "otp_secret", "totp_secret",
    "reset_password_key", "unsubscribe_key", "login_after", "login_before", "restrict_ip",
    "bank_account_no", "bank_ac_no", "account_number", "iban", "swift_number", "routing_number",
    "card_number", "credit_card_number", "cvv", "cvc",
    "passport_number", "national_id", "social_security_number", "ssn",
    "smtp_password", "app_access_token", "webhook_secret",
})

# Patterns matched against the field name (lower case). Kept narrow to avoid hiding business data.
SENSITIVE_PATTERNS = tuple(re.compile(p) for p in (
    r"(^|_)password($|_)",
    r"(^|_)passwd($|_)",
    r"(^|_)secret($|_)",
    r"(^|_)api_?key($|_)",
    r"(^|_)(access|refresh|auth|bearer)_token($|_)",
    r"(^|_)private_key($|_)",
    r"(^|_)iban($|_)",
    r"bank_(account|ac)_(no|number)",
    r"(^|_)card_number($|_)",
))

# DocTypes that can never be AI data sources or ERP-report bases: credentials, security,
# code and audit data, plus Neotec AI's own records.
BLOCKED_DOCTYPES = frozenset({
    "User", "User Permission", "Role", "Role Profile", "Has Role", "DocPerm", "Custom DocPerm",
    "Access Log", "Activity Log", "Version", "Error Log", "Scheduled Job Log", "Request Log",
    "Session Default Settings", "Sessions", "OAuth Bearer Token", "OAuth Authorization Code",
    "OAuth Client", "Connected App", "Token Cache", "Social Login Key", "LDAP Settings",
    "Email Account", "Email Queue", "Email Queue Recipient", "Communication",
    "Integration Request", "Webhook", "Webhook Request Log",
    "Server Script", "Client Script", "System Console", "Data Import", "Data Export",
    "Prepared Report", "File", "Document Share Key", "Personal Data Download Request",
    "Personal Data Deletion Request", "Contact Phone", "Contact Email",
})


def _extra_fieldnames():
    cached = getattr(frappe.local, "neotec_extra_sensitive", None)
    if cached is not None:
        return cached
    raw = ""
    try:
        raw = frappe.db.get_single_value("Neotec Settings", "extra_sensitive_fields") or ""
    except Exception:
        raw = ""
    names = {n.strip().lower() for n in re.split(r"[,\n]", raw) if n.strip()}
    frappe.local.neotec_extra_sensitive = names
    return names


def is_sensitive_field(fieldname, doctype=None):
    """True when a field may never be exposed. Accepts 'field' or 'DocType.field'."""
    if not fieldname:
        return False
    name = str(fieldname).rpartition(".")[2].strip().lower()
    if name in SENSITIVE_FIELDNAMES:
        return True
    if any(p.search(name) for p in SENSITIVE_PATTERNS):
        return True
    extra = _extra_fieldnames()
    if name in extra or (doctype and f"{doctype.lower()}.{name}" in extra):
        return True
    return False


def is_blocked_doctype(doctype):
    return not doctype or doctype in BLOCKED_DOCTYPES or str(doctype).startswith("Neotec ")


def filter_sensitive_columns(columns, rows):
    """Drop sensitive columns from a tabular result. columns: [{fieldname,...}], rows: list of lists."""
    def bad(c):
        label = re.sub(r"[^a-z0-9]+", "_", str(c.get("label") or "").lower()).strip("_")
        return is_sensitive_field(c.get("fieldname")) or (label and is_sensitive_field(label))

    keep = [i for i, c in enumerate(columns) if not bad(c)]
    if len(keep) == len(columns):
        return columns, rows
    return [columns[i] for i in keep], [[r[i] for i in keep] for r in rows]
