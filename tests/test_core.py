"""Pure-logic tests (no Frappe site needed): python -m pytest tests -q"""

from datetime import date

import pytest

from neotec_ai.agents.engine import arabic, blocks, llm, policy, redact
from neotec_ai.agents.tools import ksa


# ---------------------------------------------------------------- policy

def ev(expr, ctx):
    return eval(expr, {}, {"tool": ctx["tool"], "args": ctx["args"], "doctype": ctx.get("doctype"),
                           "is_write": ctx["is_write"], "initiator": ctx.get("initiator")})


def ctx(tool="search_documents", is_write=False, doctype=None, initiator="Chat", roles=()):
    return {"tool": tool, "args": {"doctype": doctype}, "doctype": doctype, "is_write": is_write,
            "initiator": initiator, "roles": set(roles), "coworker": "General Assistant", "user": "u@x"}


def test_read_allowed_by_default():
    assert policy.decide([], ctx(), "Default", ev)["effect"] == policy.ALLOW


def test_write_needs_approval_by_default():
    assert policy.decide([], ctx("create_draft_document", True), "Default", ev)["effect"] == policy.APPROVE


def test_auto_grant_runs_write():
    assert policy.decide([], ctx("create_draft_document", True), "Auto", ev)["effect"] == policy.ALLOW


def test_ask_grant_asks_even_for_reads():
    assert policy.decide([], ctx(), "Ask", ev)["effect"] == policy.APPROVE


def test_deny_beats_allow():
    rules = [{"name": "a", "effect": "Allow", "tool_pattern": "*"},
             {"name": "d", "effect": "Deny", "tool_pattern": "search_*"}]
    d = policy.decide(rules, ctx(), "Auto", ev)
    assert d["effect"] == policy.DENY and d["rule"] == "d"


def test_approval_rule_carries_role():
    rules = [{"name": "r", "effect": "Require Approval", "tool_pattern": "*_draft_document",
              "approver_role": "Accounts Manager", "condition": "doctype == 'Payment Entry'"}]
    d = policy.decide(rules, ctx("create_draft_document", True, "Payment Entry"), "Auto", ev)
    assert d["effect"] == policy.APPROVE and d["approver_role"] == "Accounts Manager"
    d2 = policy.decide(rules, ctx("create_draft_document", True, "Quotation"), "Auto", ev)
    assert d2["effect"] == policy.ALLOW


def test_broken_condition_fails_closed():
    deny = [{"name": "x", "effect": "Deny", "tool_pattern": "*", "condition": "undefined_name > 1"}]
    assert policy.decide(deny, ctx(), "Auto", ev)["effect"] == policy.DENY
    allow = [{"name": "y", "effect": "Allow", "tool_pattern": "*", "condition": "undefined_name > 1"}]
    assert policy.decide(allow, ctx("send_email", True), "Default", ev)["effect"] == policy.APPROVE


def test_initiator_and_role_scope():
    rules = [{"name": "routine", "effect": "Deny", "tool_pattern": "*", "initiator": "Routine",
              "condition": "is_write"}]
    assert policy.decide(rules, ctx("add_comment", True, initiator="Routine"), "Auto", ev)["effect"] == policy.DENY
    assert policy.decide(rules, ctx("add_comment", True, initiator="Chat"), "Auto", ev)["effect"] == policy.ALLOW
    scoped = [{"name": "s", "effect": "Deny", "tool_pattern": "*", "applies_to_role": "Intern"}]
    assert policy.decide(scoped, ctx(roles=["Intern"]), "Default", ev)["effect"] == policy.DENY
    assert policy.decide(scoped, ctx(roles=["Accounts User"]), "Default", ev)["effect"] == policy.ALLOW


def test_disabled_rule_ignored():
    rules = [{"name": "off", "enabled": 0, "effect": "Deny", "tool_pattern": "*"}]
    assert policy.decide(rules, ctx(), "Default", ev)["effect"] == policy.ALLOW


# ---------------------------------------------------------------- masking

def test_mask_personal_ksa_formats():
    text = "ID 1012345678, Iqama 2123456789, IBAN SA03 8000 0000 6080 1016 7519, mobile 0551234567, a@b.sa"
    out = redact.mask_personal(text)
    for leaked in ("1012345678", "2123456789", "8000 0000", "0551234567", "a@b.sa"):
        assert leaked not in out
    assert "[iban]" in out and "[mobile]" in out and "[email]" in out


def test_card_needs_luhn():
    assert "[card]" in redact.mask_personal("card 4111 1111 1111 1111")
    assert "4111 1111 1111 1112" in redact.mask_personal("ref 4111 1111 1111 1112")


def test_amounts_and_vat_numbers_untouched():
    text = "Total 1,250,000.50 SAR; VAT no 310123456700003; invoice ACC-SINV-2026-00012"
    assert redact.mask_personal(text) == text


def test_secrets_masked_and_keys():
    out = redact.mask_obj({"api_key": "abc123456", "note": "Bearer abcdefghijklmnopqrstu"})
    assert out["api_key"] == "[secret]" and "abcdefghijklmnop" not in out["note"]


def test_to_json_truncates():
    s = redact.to_json({"x": "a" * 500}, 100)
    assert "truncated" in s and len(s) < 200


# ---------------------------------------------------------------- arabic

def test_arabic_normalisation_and_article():
    assert arabic.normalize("إجازةٌ") == "اجازه"
    assert "اجازه" in arabic.tokens("الإجازة السنوية")
    assert arabic.tokens("ما هي سياسة السفر؟") == ["سياسه", "سفر"]
    assert arabic.normalize("٢٠٢٦") == "2026"


# ---------------------------------------------------------------- blocks

def test_blocks_clean_and_cap():
    clean, problems = blocks.clean_blocks([
        {"type": "kpis", "items": [{"label": "Overdue", "value": "1,200 SAR", "trend": "down"}]},
        {"type": "table", "columns": ["A", "B"], "rows": [[1, 2, 3], {"A": "x", "B": "y"}]},
        {"type": "chart", "chart": "pie", "labels": ["a", "b"],
         "datasets": [{"name": "s", "values": ["1,000", 2]}, {"name": "t", "values": [1, 2]}]},
        {"type": "script", "text": "<script>"},
        {"type": "doclist", "items": [{"doctype": "Customer", "name": "<b>x</b>"}, {"doctype": "Customer", "name": "ACME"}]},
    ])
    types = [b["type"] for b in clean]
    assert types == ["kpis", "table", "chart", "doclist"]
    assert clean[1]["rows"] == [["1", "2"], ["x", "y"]]
    assert clean[2]["datasets"] == [{"name": "s", "values": [1000, 2]}]
    assert clean[3]["items"] == [{"doctype": "Customer", "name": "ACME"}]
    assert problems


def test_form_block_fieldnames_sanitised():
    clean, _ = blocks.clean_blocks([{"type": "form", "fields": [
        {"fieldname": "Qty", "fieldtype": "Int"}, {"fieldname": "bad name", "fieldtype": "Data"},
        {"fieldname": "kind", "fieldtype": "Select", "options": ["A", "B"]}]}])
    assert [f["fieldname"] for f in clean[0]["fields"]] == ["qty", "kind"]
    assert clean[0]["fields"][1]["options"] == "A\nB"


# ---------------------------------------------------------------- KSA

def test_vat_split():
    assert ksa.vat_split(100) == {"net": 100.0, "vat": 15.0, "gross": 115.0, "rate_pct": 15.0}
    assert ksa.vat_split(115, inclusive=True)["net"] == 100.0


def test_vat_number():
    assert ksa.vat_number_problems("310123456700003") == []
    assert ksa.vat_number_problems("21012345670000") != []


def test_iban():
    problems, bank = ksa.iban_problems("SA03 8000 0000 6080 1016 7519")
    assert problems == [] and bank == "Al Rajhi Bank"
    problems, _ = ksa.iban_problems("SA03 8000 0000 6080 1016 7518")
    assert problems


@pytest.mark.parametrize("years,reason,factor", [
    (1.5, "resignation", 0), (3, "resignation", 1 / 3), (7, "resignation", 2 / 3), (12, "resignation", 1),
    (3, "termination", 1), (3, "dismissal_art80", 0), (1, "marriage_or_childbirth", 1),
])
def test_end_of_service_factors(years, reason, factor):
    start = date(2010, 1, 1)
    end = date.fromordinal(start.toordinal() + int(years * 365) - 1)
    r = ksa.end_of_service(10000, start, end, reason)
    assert r["entitlement_factor"] == round(factor, 4)


def test_end_of_service_amounts():
    start = date(2016, 1, 1)
    r = ksa.end_of_service(12000, start, date.fromordinal(start.toordinal() + 3649), "termination")  # 3650 days
    assert r["award_first_5_years"] == 30000.0
    assert r["award_after_5_years"] == 60000.0
    assert r["payable"] == 90000.0


# ---------------------------------------------------------------- provider adapters

def test_openai_roundtrip():
    msgs = [{"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "t", "arguments": {"a": 1}}]},
            {"role": "tool", "tool_call_id": "c1", "name": "t", "content": "{}"}]
    out = llm.to_openai("sys", msgs)
    assert out[0]["role"] == "system" and out[2]["content"] is None
    assert out[2]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'
    res = llm.from_openai({"choices": [{"message": {"content": None, "tool_calls": [
        {"id": "x", "function": {"name": "t", "arguments": '{"b": 2}'}}]}, "finish_reason": "tool_calls"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3}})
    assert res.tool_calls == [{"id": "x", "name": "t", "arguments": {"b": 2}}] and res.tokens_in == 5


def test_anthropic_merges_tool_results():
    msgs = [{"role": "user", "content": "hi"},
            {"role": "assistant", "content": "checking", "tool_calls": [
                {"id": "a", "name": "t", "arguments": {}}, {"id": "b", "name": "u", "arguments": {}}]},
            {"role": "tool", "tool_call_id": "a", "content": "1"},
            {"role": "tool", "tool_call_id": "b", "content": "2"}]
    out = llm.to_anthropic(msgs)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert [b["tool_use_id"] for b in out[2]["content"]] == ["a", "b"]
    res = llm.from_anthropic({"content": [{"type": "text", "text": "ok"},
                                          {"type": "tool_use", "id": "z", "name": "t", "input": {"q": 1}}],
                              "usage": {"input_tokens": 9, "output_tokens": 4}})
    assert res.text == "ok" and res.tool_calls[0]["arguments"] == {"q": 1}


def test_invalid_tool_arguments_flagged():
    assert "__invalid_json__" in llm.parse_args("{not json")
