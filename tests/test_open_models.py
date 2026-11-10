"""Open-model catalogue matching and the tool-calling self-test scoring."""

import pytest

from neotec_ai.agents.engine import selftest as st
from neotec_ai.agents.setup import open_models as om


@pytest.mark.parametrize("model_id,key", [
    ("qwen3.6:27b", "qwen3.6-27b"),
    ("qwen3.6:27b-q4_K_M", "qwen3.6-27b"),
    ("Qwen/Qwen3.6-27B-AWQ", "qwen3.6-27b"),
    ("qwen3.6:35b-a3b", "qwen3.6-35b-a3b"),
    ("qwen3.8:27b", "qwen3.8-27b"),
    ("Qwen/Qwen3.8-27B", "qwen3.8-27b"),
    ("qwen3.5:9b", "qwen3.5-small"),
    ("gpt-oss:120b", "gpt-oss-120b"),
    ("openai/gpt-oss-20b", "gpt-oss-20b"),
    ("gemma4:26b", "gemma-4"),
    ("meta-llama/Llama-4-Scout-17B-16E-Instruct", "llama-4-scout"),
    ("mistral-small:24b", "mistral-small"),
])
def test_catalogue_recognises_served_names(model_id, key):
    m = om.match_catalogue(model_id)
    assert m and m["key"] == key


@pytest.mark.parametrize("model_id", ["", None, "llama3:8b", "my-finetune", "phi4"])
def test_unknown_models_are_not_guessed(model_id):
    assert om.match_catalogue(model_id) is None


def test_free_hosted_detection():
    assert om.is_free_hosted("https://openrouter.ai/api/v1", "qwen/qwen3.8-27b:free")
    assert not om.is_free_hosted("https://openrouter.ai/api/v1", "qwen/qwen3.8-27b")
    assert not om.is_free_hosted("https://ai.example.com.sa/v1", "qwen3.6:27b:free")


def test_ollama_root_and_sizes():
    assert om.ollama_root("http://gpu:11434/v1/") == "http://gpu:11434"
    assert om.ollama_root("https://ai.example.com.sa") == "https://ai.example.com.sa"
    assert om.human_size(17_000_000_000) == "15.8 GB"
    assert om.human_size("x") == ""


def test_every_tier_is_described():
    assert {m["tier"] for m in om.MODELS} <= set(om.TIERS)


# ---------------------------------------------------------------- self-test scoring

def call(name="lookup_invoice", **args):
    return {"text": "", "tool_calls": [{"id": "c1", "name": name, "arguments": args}]}


def test_right_tool_and_argument():
    assert st.check_call(call(invoice_no="sinv-0042 "), "SINV-0042")[0]
    assert not st.check_call(call(invoice_no="SINV-42"), "SINV-0042")[0]
    assert not st.check_call(call("search", invoice_no="SINV-0042"), "SINV-0042")[0]
    assert not st.check_call({"text": "It is 100 SAR", "tool_calls": []}, "SINV-0042")[0]
    assert not st.check_call(call(__invalid_json__="{bad"), "SINV-0042")[0]


@pytest.mark.parametrize("text,ok", [
    ("The outstanding amount is SAR 18,450.75.", True),
    ("المبلغ المستحق 18450.75 ريال", True),
    ("المبلغ المستحق 18٬450٫75 ريال", True),
    ("About 18,000 SAR.", False),
])
def test_answer_uses_tool_result(text, ok):
    assert st.check_answer({"text": text, "tool_calls": []})[0] is ok


def test_answer_must_not_call_again():
    assert not st.check_answer(call(invoice_no="SINV-0042"))[0]


def test_no_tool_when_not_needed():
    assert st.check_no_tool({"text": "READY", "tool_calls": []})[0]
    assert not st.check_no_tool(call(invoice_no="x"))[0]
    assert not st.check_no_tool({"text": "Sure!", "tool_calls": []})[0]


def test_verdict():
    ok, bad = (True, "ok"), (False, "x")
    assert st.verdict({"tool_call": ok, "use_result": ok, "arabic": ok, "no_tool": ok}) == "Passed"
    assert st.verdict({"tool_call": ok, "use_result": ok, "arabic": bad, "no_tool": ok}) == "Partial"
    assert st.verdict({"tool_call": ok, "use_result": bad, "arabic": ok, "no_tool": ok}) == "Failed"
    assert "✘ Works from an Arabic request: x" in st.summary(
        {"tool_call": ok, "use_result": ok, "arabic": bad, "no_tool": ok}, 900)
