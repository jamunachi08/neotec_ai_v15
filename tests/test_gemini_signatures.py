"""Gemini thinking models reject a request whose earlier function calls lost their thought signature."""

from neotec_ai.agents.engine import llm

SIG = {"google": {"thought_signature": "CvcQAdHtim-abc=="}}


def gemini_reply(*calls):
    return {"choices": [{"message": {"content": None, "tool_calls": list(calls)}, "finish_reason": "tool_calls"}]}


def call(cid, name, args="{}", extra=None):
    c = {"id": cid, "type": "function", "function": {"name": name, "arguments": args}}
    if extra:
        c["extra_content"] = extra
    return c


def test_signature_is_kept_from_the_response():
    res = llm.from_openai(gemini_reply(call("a", "cash_position", extra=SIG), call("b", "low_stock")))
    assert res.tool_calls[0]["extra"] == SIG
    assert "extra" not in res.tool_calls[1]


def test_signature_goes_back_unchanged_to_gemini():
    res = llm.from_openai(gemini_reply(call("a", "cash_position", extra=SIG), call("b", "low_stock")))
    history = [{"role": "user", "content": "cash?"},
               {"role": "assistant", "content": "", "tool_calls": res.tool_calls},
               {"role": "tool", "tool_call_id": "a", "content": "{}"},
               {"role": "tool", "tool_call_id": "b", "content": "{}"}]
    out = llm.to_openai("sys", history, gemini=True)
    sent = out[2]["tool_calls"]
    assert sent[0]["extra_content"] == SIG
    assert "extra_content" not in sent[1]  # only the first parallel call carries one


def test_old_history_without_signature_gets_the_documented_placeholder():
    history = [{"role": "user", "content": "x"},
               {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "name": "t", "arguments": {}},
                                                                  {"id": "b", "name": "u", "arguments": {}}]}]
    sent = llm.to_openai("sys", history, gemini=True)[2]["tool_calls"]
    assert sent[0]["extra_content"]["google"]["thought_signature"] == llm.GEMINI_SKIP_SIGNATURE
    assert "extra_content" not in sent[1]


def test_other_providers_never_receive_the_field():
    history = [{"role": "user", "content": "x"},
               {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "name": "t", "arguments": {},
                                                                  "extra": SIG}]}]
    sent = llm.to_openai("sys", history)[2]["tool_calls"][0]
    assert "extra_content" not in sent and "extra" not in sent


def test_gemini_detection():
    mk = lambda url: llm.ProviderConfig("OpenAI Compatible", url, "m")  # noqa: E731
    assert llm.is_gemini(mk("https://generativelanguage.googleapis.com/v1beta/openai"))
    assert not llm.is_gemini(mk("https://api.openai.com/v1"))
    assert not llm.is_gemini(mk("https://ai.example.com.sa/v1"))
