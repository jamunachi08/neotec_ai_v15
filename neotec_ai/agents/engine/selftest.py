# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Tool-calling self-test. Coworkers depend on the model calling tools correctly; many small open models chat
well but call tools badly. Four short checks, about four model calls:

  1. calls the right tool with the right argument            (English request)
  2. answers from the tool result instead of inventing       (figure must come back exactly)
  3. calls the tool from an Arabic request, keeping the code (bilingual use)
  4. does not call a tool when none is needed                (no runaway loops)

Passed = all four. Partial = 1 and 2 pass. Failed otherwise. Playbooks refuse providers that Failed.
The scoring functions are pure and unit-tested; ``run`` does the calls.
"""

from __future__ import annotations

import re
import time

TOOL = {
    "name": "lookup_invoice",
    "description": "Returns the outstanding amount of one sales invoice.",
    "schema": {"type": "object", "properties": {"invoice_no": {"type": "string", "description": "e.g. SINV-0042"}},
               "required": ["invoice_no"]},
}
SYSTEM = ("You are a test assistant inside an ERP. Use tools for facts about invoices. "
          "Never invent figures.")
RESULT = '{"invoice_no": "SINV-0042", "outstanding": 18450.75, "currency": "SAR"}'


def check_call(result, invoice) -> tuple[bool, str]:
    calls = result.get("tool_calls") or []
    if not calls:
        return False, "no tool call"
    c = calls[0]
    if c.get("name") != TOOL["name"]:
        return False, f"called {c.get('name')}"
    args = c.get("arguments") or {}
    if "__invalid_json__" in args:
        return False, "arguments were not valid JSON"
    got = str(args.get("invoice_no") or "").strip().upper()
    if got != invoice:
        return False, f"invoice_no was {got or 'missing'}"
    return True, "ok"


def check_answer(result) -> tuple[bool, str]:
    if result.get("tool_calls"):
        return False, "called a tool again instead of answering"
    text = (result.get("text") or "").replace("\u066c", ",").replace("\u066b", ".")
    if re.search(r"18[,\s]?450\.75", text):
        return True, "ok"
    return False, "answer did not contain 18,450.75"


def check_no_tool(result) -> tuple[bool, str]:
    if result.get("tool_calls"):
        return False, "called a tool for a plain request"
    if "READY" in (result.get("text") or "").upper():
        return True, "ok"
    return False, "did not follow the instruction"


def verdict(checks: dict) -> str:
    if all(ok for ok, _ in checks.values()):
        return "Passed"
    if checks.get("tool_call", (False,))[0] and checks.get("use_result", (False,))[0]:
        return "Partial"
    return "Failed"


def summary(checks: dict, ms: int) -> str:
    labels = {"tool_call": "Calls the right tool", "use_result": "Answers from the tool result",
              "arabic": "Works from an Arabic request", "no_tool": "No tool when none is needed"}
    lines = [f"{'✔' if ok else '✘'} {labels[k]}{'' if ok else ': ' + why}" for k, (ok, why) in checks.items()]
    return "\n".join(lines) + f"\nTotal time {ms} ms"


def run(cfg) -> tuple[str, str, int]:
    """Returns (status, detail, milliseconds)."""
    from neotec_ai.agents.engine import llm

    def call(messages, tools=(TOOL,)):
        r = llm.chat(cfg, SYSTEM, messages, list(tools), temperature=0)
        return {"text": r.text, "tool_calls": r.tool_calls}

    started = time.time()
    checks = {}
    q1 = [{"role": "user", "content": "What is the outstanding amount on invoice SINV-0042?"}]
    try:
        r1 = call(q1)
        checks["tool_call"] = check_call(r1, "SINV-0042")
        if checks["tool_call"][0]:
            c = r1["tool_calls"][0]
            follow = q1 + [{"role": "assistant", "content": r1["text"] or "", "tool_calls": [c]},
                           {"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": RESULT}]
            checks["use_result"] = check_answer(call(follow))
        else:
            checks["use_result"] = (False, "skipped: no tool call")
        checks["arabic"] = check_call(call([{"role": "user", "content": "ما المبلغ المستحق على الفاتورة SINV-0077؟"}]),
                                      "SINV-0077")
        checks["no_tool"] = check_no_tool(call([{"role": "user", "content": "Reply with the single word READY."}]))
    except llm.ProviderError as e:
        ms = int((time.time() - started) * 1000)
        return "Failed", f"The provider returned an error: {str(e)[:300]}", ms
    ms = int((time.time() - started) * 1000)
    return verdict(checks), summary(checks, ms), ms
