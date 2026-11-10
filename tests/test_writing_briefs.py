from tests.frappe_stub import install

install()

from neotec_ai import briefs, writing  # noqa: E402


def test_language_and_protection():
    assert writing.detect_language("السلام عليكم ورحمة الله") == "Arabic"
    assert writing.detect_language("Please send the quotation") == "English"
    text, tokens = writing.protect("Neotec AI and ERPNext quote", ["ERPNext", "Neotec AI"])
    assert "ERPNext" not in text and "Neotec AI" not in text
    back, missing = writing.restore(text, tokens)
    assert back == "Neotec AI and ERPNext quote" and not missing


def test_number_warning_with_arabic_digits():
    assert writing.numbers("المبلغ ١٢٥٠ ريال") == writing.numbers("amount 1,250 SAR")
    assert writing.warnings_for("pay 100", "pay 1000", []) != []


def test_brief_answer_split():
    s, body = briefs.split_answer("CHANGES: two new overdue invoices\n# Receivables\n| a | b |")
    assert s == "two new overdue invoices" and body.startswith("# Receivables")
    s, body = briefs.split_answer("# Only a body")
    assert s == "" and body == "# Only a body"
    assert "first version" in briefs.build_prompt("x", None, "2026-11-10 07:00")
