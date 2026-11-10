"""Pure tests for playbook output contract, delivery formatting, residency-safe fallback and health counters."""

import pytest

from neotec_ai.agents.automation import common as c


@pytest.mark.parametrize("text", ["NOTHING_TO_REPORT", "  nothing_to_report.", "`NOTHING_TO_REPORT`",
                                  "**NOTHING TO REPORT**", "SEVERITY: info\nNOTHING_TO_REPORT"])
def test_nothing_to_report_variants(text):
    clean, _sev, nothing = c.parse_output(text)
    assert nothing and clean == ""


def test_severity_line_is_read_and_removed():
    clean, sev, nothing = c.parse_output("SEVERITY: critical\n\nTwo customers are 180+ days overdue.")
    assert sev == "critical" and not nothing
    assert clean == "Two customers are 180+ days overdue."


def test_severity_tolerates_markdown_and_warning_alias():
    _clean, sev, _n = c.parse_output("**Severity: Warning**\nStock is low.")
    assert sev == "warn"


def test_no_severity_uses_default_and_keeps_text():
    clean, sev, nothing = c.parse_output("Cash fell 5%.", "info")
    assert (clean, sev, nothing) == ("Cash fell 5%.", "info", False)


def test_report_mentioning_the_phrase_is_not_silent():
    long = "NOTHING_TO_REPORT for receivables, but payables have 3 overdue suppliers totalling SAR 240,000 " * 2
    assert c.parse_output(long)[2] is False


def test_empty_output_is_not_silent():
    assert c.parse_output("")[2] is False


def test_fallback_never_moves_data_further_away():
    assert c.fallback_allowed("External", "On-Premises", "Guarded")
    assert c.fallback_allowed("In Kingdom (KSA)", "In Kingdom (KSA)", "Guarded")
    assert not c.fallback_allowed("On-Premises", "External", "Open")
    assert not c.fallback_allowed("In Kingdom (KSA)", "External", "Guarded")
    assert not c.fallback_allowed("External", "External", "Strict")


def test_severity_threshold():
    assert c.passes_threshold("critical", "warn")
    assert not c.passes_threshold("info", "warn")
    assert c.passes_threshold("warn", None)


def test_substitute_leaves_json_and_unknown_keys():
    out = c.substitute('Use {parameter} days; filters {"status": "Open"}; keep {unknown}', {"parameter": 14})
    assert out == 'Use 14 days; filters {"status": "Open"}; keep {unknown}'


def test_render_parameter_from_document():
    doc = {"name": "ACC-PINV-0001", "doctype": "Purchase Invoice", "supplier": "Al Noor", "items": [1, 2],
           "is_return": False}
    assert c.render_parameter("{name} from {supplier}", doc) == "ACC-PINV-0001 from Al Noor"
    assert c.render_parameter(None, doc) == "ACC-PINV-0001"
    assert c.render_parameter("{items}", doc) == "{items}"


def test_chunking_keeps_lines_and_numbers_parts():
    text = "\n".join(f"line {i:04d} " + "x" * 50 for i in range(300))
    parts = c.chunk_text(text, 1000)
    assert len(parts) > 1 and all(len(p) <= 1000 + 12 for p in parts)
    assert parts[0].startswith("[1/") and parts[-1].startswith(f"[{len(parts)}/")
    assert c.chunk_text("short") == ["short"]


def test_chunking_splits_very_long_lines():
    parts = c.chunk_text("y" * 2500, 1000)
    assert len(parts) == 3


def test_chat_markdown():
    out = c.to_chat_markdown("## Overdue\n**SAR 84,000** at [CUST-1](https://x.example/app/customer/CUST-1)")
    assert out == "*Overdue*\n*SAR 84,000* at <https://x.example/app/customer/CUST-1|CUST-1>"


def test_teams_card_shape():
    p = c.teams_payload("Low stock", "3 items", "critical")
    card = p["attachments"][0]["content"]
    assert p["type"] == "message" and card["type"] == "AdaptiveCard"
    assert card["body"][0]["color"] == "Attention"


def test_tools_normalised():
    assert c.normalise_tools("Search_Documents, render_ui;render_ui\nlow_stock") == \
        ["search_documents", "render_ui", "low_stock"]


def test_cost():
    assert c.cost_usd(1_000_000, 500_000, 0.3, 2.5) == 1.55
    assert c.cost_usd(1000, 1000, None, None) == 0


def test_consecutive_failures_newest_first():
    assert c.consecutive_failures(["Failed", "Budget Exceeded", "Succeeded", "Failed"]) == 2
    assert c.consecutive_failures(["Nothing to Report", "Failed"]) == 0


@pytest.mark.parametrize("text,expected", [
    ('{"score": 4, "note": "specific"}', (4, "specific")),
    ('```json\n{"score": "5", "note": "x"}\n```', (5, "x")),
    ('Here you go: {"score": 9}', (None, "")),
    ("no json", (None, "")),
])
def test_parse_score(text, expected):
    assert c.parse_score(text) == expected
