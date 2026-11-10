# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Writing help on long text fields across ERPNext: spell check (Arabic and English), translate Arabic <-> English,
improve, make formal, make shorter. Always a preview first; the user applies it.

Names in the company glossary (Neotec AI Glossary Term) marked Keep As Is are protected with placeholders so the
model cannot alter them; numbers are compared before and after and the user is warned when they differ.
Calls go through the shared gateway (route "Writing"), so residency, masking and the usage ledger apply.
"""

from __future__ import annotations

import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import cint

MAX_CHARS = 6000
ACTIONS = ("spell", "translate", "improve", "formal", "shorten")
FIELD_TYPES = ("Small Text", "Text", "Long Text")
ARABIC = re.compile(r"[\u0600-\u06FF]")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
REWRITE = {
    "improve": "Improve the wording: fix grammar and spelling, make it clear and natural; same meaning, length and tone.",
    "formal": "Rewrite it in a polite, formal business tone suitable for Saudi and GCC readers; same meaning and facts.",
    "shorten": "Make it about half as long and more direct while keeping every fact, number and commitment.",
    "spell": "Fix only spelling mistakes and obvious typos (Arabic: ta marbuta/ha, alif maqsura/ya, hamza forms). "
             "Do not change wording, grammar, punctuation, numbers or names.",
}


# ---------------------------------------------------------------- pure helpers (unit-tested)

def detect_language(text: str) -> str:
    letters = re.findall(r"[A-Za-z\u0600-\u06FF]", text or "")
    if not letters:
        return "English"
    ar = sum(1 for c in letters if ARABIC.match(c))
    return "Arabic" if ar >= len(letters) / 2 else "English"


def protect(text: str, keep: list[str]) -> tuple[str, dict]:
    tokens = {}
    for term in sorted({t for t in keep if t and len(t) > 1}, key=len, reverse=True):
        if term in text:
            key = f"\u27e6{len(tokens) + 1}\u27e7"
            tokens[key] = term
            text = text.replace(term, key)
    return text, tokens


def restore(text: str, tokens: dict) -> tuple[str, list[str]]:
    missing = []
    for key, term in tokens.items():
        if key in text:
            text = text.replace(key, term)
        else:
            missing.append(term)
    return text, missing


def numbers(text: str) -> list[str]:
    return sorted(re.findall(r"\d+(?:\.\d+)?", (text or "").translate(ARABIC_DIGITS).replace(",", "")))


def warnings_for(source: str, result: str, missing: list[str]) -> list[str]:
    out = []
    if missing:
        out.append(_("These names were dropped by the AI: {0}").format(", ".join(missing[:5])))
    if numbers(source) != numbers(result):
        out.append(_("The numbers in the result differ from the original. Please check them."))
    return out


# ---------------------------------------------------------------- settings and boot

def _settings():
    return frappe.get_cached_doc("Neotec Settings")


def enabled_doctypes() -> tuple[bool, list[str]]:
    s = _settings()
    if not cint(s.get("enable_writing")):
        return False, []
    if cint(s.get("writing_all_doctypes")):
        return True, ["*"]
    return True, [r.document_type for r in (s.get("writing_doctypes") or [])]


def boot_session(bootinfo):
    if frappe.session.user == "Guest":
        return
    try:
        on, doctypes = enabled_doctypes()
    except Exception:  # noqa: BLE001 - before first migrate
        return
    if on and set(frappe.get_roles()) & {"Neotec AI User", "Coworker User", "System Manager"}:
        bootinfo.neotec_ai_writing = {"doctypes": doctypes}


def _keep_terms() -> list[str]:
    if not frappe.db.table_exists("Neotec AI Glossary Term"):
        return []
    return frappe.get_all("Neotec AI Glossary Term", filters={"keep_as_is": 1}, pluck="term", limit_page_length=500)


def _glossary(target: str) -> list[str]:
    if not frappe.db.table_exists("Neotec AI Glossary Term"):
        return []
    rows = frappe.get_all("Neotec AI Glossary Term", filters={"keep_as_is": 0},
                          fields=["term", "english", "arabic"], limit_page_length=300)
    lines = []
    for r in rows:
        src, dst = (r.english or r.term, r.arabic) if target == "Arabic" else (r.arabic or r.term, r.english)
        if src and dst:
            lines.append(f"- {src} => {dst}")
    return lines[:150]


# ---------------------------------------------------------------- endpoint

@frappe.whitelist(methods=["POST"])
def transform(text, action, target_language=None, doctype=None, docname=None):
    """Preview a change. Returns {result, source_language, target_language, warnings}."""
    on, doctypes = enabled_doctypes()
    if not on:
        frappe.throw(_("The writing assistant is switched off in Neotec Settings."))
    if doctype and "*" not in doctypes and doctype not in doctypes:
        frappe.throw(_("The writing assistant is not enabled for {0}.").format(doctype))
    if doctype and docname and frappe.db.exists(doctype, docname):
        frappe.get_doc(doctype, docname).check_permission("read")
    if action not in ACTIONS:
        frappe.throw(_("Unknown writing action {0}.").format(action))
    text = (text or "").strip()
    if not text:
        frappe.throw(_("The field is empty."))
    if len(text) > MAX_CHARS:
        frappe.throw(_("Text is too long for the writing assistant ({0} characters max).").format(MAX_CHARS))

    source = detect_language(text)
    target = (target_language if target_language in ("Arabic", "English") else
              ("English" if source == "Arabic" else "Arabic")) if action == "translate" else source
    key = "neotec_ai:writing:" + hashlib.sha1(json.dumps([text, action, target], ensure_ascii=False).encode()).hexdigest()
    cache = frappe.cache() if callable(frappe.cache) and not hasattr(frappe.cache, "get_value") else frappe.cache
    cached = cache.get_value(key)
    if cached:
        return cached

    protected, tokens = protect(text, _keep_terms())
    if action == "translate":
        lang = "Modern Standard Arabic suitable for Saudi business readers" if target == "Arabic" else "clear, professional English"
        glossary = _glossary(target)
        system = (f"You are a professional business translator. Translate the user's text into {lang}. Translate "
                  "faithfully, keep the tone, add or remove nothing, keep numbers as written and keep every "
                  "placeholder like ⟦1⟧ exactly as it is." + ("\nUse this company glossary:\n" + "\n".join(glossary)
                                                               if glossary else ""))
    else:
        system = ("You are a writing assistant for a business in Saudi Arabia. " + REWRITE[action] + " Write in the "
                  "same language as the input (Arabic stays Arabic, English stays English, mixed stays mixed). Keep "
                  "every placeholder like ⟦1⟧ exactly as it is. Do not invent facts, prices or commitments.")
    system += ' Reply with JSON: {"text": "<the result>"}.'

    from neotec_ai.platform import gateway

    try:
        data = gateway.complete_json(system, protected, app="neotec_ai", feature=f"writing_{action}",
                                     purpose="Writing", reference=(doctype, docname) if doctype and docname else None,
                                     max_tokens=2500, temperature=0 if action == "spell" else 0.2)
    except gateway.PlatformError as e:
        frappe.throw(str(e), title=_("Writing assistant"))
    raw = str((data or {}).get("text") or "").strip() if isinstance(data, dict) else ""
    if not raw:
        frappe.throw(_("The AI returned an empty result. Please try again."))
    result, missing = restore(raw, tokens)
    out = {"result": result, "source_language": source, "target_language": target,
           "warnings": warnings_for(text, result, missing), "changed": result.strip() != text}
    cache.set_value(key, out, expires_in_sec=24 * 3600)
    return out
