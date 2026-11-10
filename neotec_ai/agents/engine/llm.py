# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Provider-agnostic chat client with tool calling.

Internal message format (provider neutral):
  {"role": "user", "content": str}
  {"role": "assistant", "content": str, "tool_calls": [{"id", "name", "arguments": dict}]}
      (a call may also carry "extra": provider data that must be sent back unchanged, e.g. Gemini's
       thought signature)
  {"role": "tool", "tool_call_id": str, "name": str, "content": str}

API styles:
  OpenAI Compatible  -> OpenAI, Google Gemini (OpenAI endpoint), Groq, Ollama, vLLM, NeotecAI, LM Studio…
  Anthropic          -> Anthropic Messages API
  Azure OpenAI       -> Azure deployments (api-key header + api-version)
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field


class ProviderError(Exception):
    """``status`` is the HTTP status (0 when the provider could not be reached)."""

    def __init__(self, message="", status: int = 0):
        super().__init__(message)
        self.status = status

    @property
    def transient(self) -> bool:
        return self.status in (0, 408, 409, 425, 429, 500, 502, 503, 504, 529)


@dataclass
class LLMResult:
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    stop_reason: str = ""


@dataclass
class ProviderConfig:
    provider_type: str
    base_url: str
    model: str
    api_key: str = ""
    api_version: str = ""
    temperature: float = 0.2
    max_output_tokens: int = 2048
    timeout: int = 120
    name: str = ""


# ---------------------------------------------------------------- pure converters

def parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {"value": val}
    except (TypeError, ValueError):
        return {"__invalid_json__": str(raw)[:500]}


GOOGLE_HOSTS = ("generativelanguage.googleapis.com", "aiplatform.googleapis.com")
# Documented by Google for function calls that have no signature of their own (history from before signatures
# were kept, or from another model).
GEMINI_SKIP_SIGNATURE = "skip_thought_signature_validator"


def is_gemini(cfg) -> bool:
    return any(h in (cfg.base_url or "") for h in GOOGLE_HOSTS)


def _openai_call(c: dict, gemini: bool, first: bool) -> dict:
    out = {"id": c["id"], "type": "function",
           "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments") or {}, ensure_ascii=False)}}
    if gemini:
        # Gemini (thinking models) issues a thought signature with function calls and rejects the next request
        # unless it comes back unchanged. Only the first call of a parallel batch carries one.
        if c.get("extra"):
            out["extra_content"] = c["extra"]
        elif first:
            out["extra_content"] = {"google": {"thought_signature": GEMINI_SKIP_SIGNATURE}}
    return out


def to_openai(system: str, messages: list[dict], gemini: bool = False) -> list[dict]:
    out = [{"role": "system", "content": system}]
    for m in messages:
        if m["role"] == "assistant":
            msg = {"role": "assistant", "content": m.get("content") or ""}
            if m.get("tool_calls"):
                msg["tool_calls"] = [_openai_call(c, gemini, i == 0) for i, c in enumerate(m["tool_calls"])]
                if not msg["content"]:
                    msg["content"] = None
            out.append(msg)
        elif m["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m.get("content") or ""})
        else:
            out.append({"role": "user", "content": _openai_user_content(m)})
    return out


def _openai_user_content(m: dict):
    images = m.get("images") or []
    if not images:
        return m.get("content") or ""
    parts = [{"type": "text", "text": m.get("content") or ""}]
    for img in images:
        parts.append({"type": "image_url", "image_url": {
            "url": f"data:{img.get('media_type') or 'image/png'};base64,{img['data']}"}})
    return parts


def openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"][:1000],
                                               "parameters": t["schema"]}} for t in tools]


def from_openai(data: dict) -> LLMResult:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    calls = []
    for c in msg.get("tool_calls") or []:
        fn = c.get("function") or {}
        call = {"id": c.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                "name": fn.get("name"), "arguments": parse_args(fn.get("arguments"))}
        if isinstance(c.get("extra_content"), dict):
            call["extra"] = c["extra_content"]  # kept with the message and sent back unchanged
        calls.append(call)
    content = msg.get("content")
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    usage = data.get("usage") or {}
    return LLMResult(text=content or "", tool_calls=calls,
                     tokens_in=int(usage.get("prompt_tokens") or 0),
                     tokens_out=int(usage.get("completion_tokens") or 0),
                     stop_reason=choice.get("finish_reason") or "")


def to_anthropic(messages: list[dict]) -> list[dict]:
    out: list[dict] = []

    def push(role, blocks):
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for m in messages:
        if m["role"] == "assistant":
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for c in m.get("tool_calls") or []:
                blocks.append({"type": "tool_use", "id": c["id"], "name": c["name"],
                               "input": c.get("arguments") or {}})
            if blocks:
                push("assistant", blocks)
        elif m["role"] == "tool":
            push("user", [{"type": "tool_result", "tool_use_id": m["tool_call_id"],
                           "content": m.get("content") or ""}])
        else:
            blocks = [{"type": "image", "source": {"type": "base64", "media_type": img.get("media_type") or "image/png",
                                                    "data": img["data"]}} for img in (m.get("images") or [])]
            push("user", blocks + [{"type": "text", "text": m.get("content") or " "}])
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": [{"type": "text", "text": "(continuing)"}]})
    return out


def anthropic_tools(tools: list[dict]) -> list[dict]:
    return [{"name": t["name"], "description": t["description"][:1000], "input_schema": t["schema"]}
            for t in tools]


def from_anthropic(data: dict) -> LLMResult:
    text, calls = [], []
    for b in data.get("content") or []:
        if b.get("type") == "text":
            text.append(b.get("text") or "")
        elif b.get("type") == "tool_use":
            calls.append({"id": b.get("id"), "name": b.get("name"), "arguments": b.get("input") or {}})
    usage = data.get("usage") or {}
    return LLMResult(text="".join(text), tool_calls=calls,
                     tokens_in=int(usage.get("input_tokens") or 0),
                     tokens_out=int(usage.get("output_tokens") or 0),
                     stop_reason=data.get("stop_reason") or "")


# ---------------------------------------------------------------- HTTP

def _post(url, headers, body, timeout, retries=3):
    import requests

    last, status = None, 0
    retries = max(1, int(retries or 1))
    for attempt in range(retries):
        try:
            resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=timeout)
        except requests.RequestException as e:
            last, status = f"Could not reach the provider: {e}", 0
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            last, status = f"Provider returned {resp.status_code}", resp.status_code
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code >= 400:
            detail = resp.text[:600]
            raise ProviderError(f"Provider returned HTTP {resp.status_code}: {detail}", resp.status_code)
        try:
            return resp.json()
        except ValueError as e:
            raise ProviderError(f"Provider sent a response that is not JSON: {resp.text[:300]}", 502) from e
    raise ProviderError(last or "Provider did not answer", status)


JSON_INSTRUCTION = "\n\nReply with one valid JSON object only: no prose, no code fences."


def chat(cfg: ProviderConfig, system: str, messages: list[dict], tools: list[dict],
         temperature: float | None = None, json_mode: bool = False, schema: dict | None = None,
         retries: int = 3) -> LLMResult:
    temp = cfg.temperature if temperature is None else temperature
    base = (cfg.base_url or "").rstrip("/")
    if json_mode or schema:
        system = (system or "") + JSON_INSTRUCTION
    if cfg.provider_type == "Anthropic":
        url = base + ("/messages" if base.endswith("/v1") else "/v1/messages")
        headers = {"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        body = {"model": cfg.model, "system": system, "messages": to_anthropic(messages),
                "max_tokens": cfg.max_output_tokens or 2048, "temperature": temp}
        if tools:
            body["tools"] = anthropic_tools(tools)
        return from_anthropic(_post(url, headers, body, cfg.timeout or 120, retries))

    if cfg.provider_type == "Azure OpenAI":
        url = f"{base}/chat/completions?api-version={cfg.api_version or '2024-10-21'}"
        headers = {"api-key": cfg.api_key, "Content-Type": "application/json"}
    else:
        url = base + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"
    body = {"model": cfg.model, "messages": to_openai(system, messages, gemini=is_gemini(cfg)), "temperature": temp,
            "max_tokens": cfg.max_output_tokens or 2048}
    if tools:
        body["tools"] = openai_tools(tools)
        body["tool_choice"] = "auto"
    if schema and not tools:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "result", "schema": schema}}
    elif json_mode and not tools:
        body["response_format"] = {"type": "json_object"}
    try:
        return from_openai(_post(url, headers, body, cfg.timeout or 120, retries))
    except ProviderError as e:
        # Older servers reject structured-output options: once more without them (the instruction stays).
        if "response_format" in body and e.status in (400, 422):
            body.pop("response_format")
            return from_openai(_post(url, headers, body, cfg.timeout or 120, retries))
        raise


# ---------------------------------------------------------------- Frappe glue

def config_from_doc(doc) -> ProviderConfig:
    api_key = ""
    if doc.get("api_key"):
        api_key = doc.get_password("api_key", raise_exception=False) or ""
    return ProviderConfig(
        provider_type=doc.provider_type, base_url=doc.base_url, model=doc.model, api_key=api_key,
        api_version=doc.get("api_version") or "", temperature=float(doc.get("temperature") or 0.2),
        max_output_tokens=int(doc.get("max_output_tokens") or 2048), timeout=int(doc.get("timeout") or 120),
        name=doc.name,
    )


def test_connection(doc) -> str:
    cfg = config_from_doc(doc)
    started = time.time()
    res = chat(cfg, "You are a connectivity check. Reply with the single word OK.",
               [{"role": "user", "content": "Reply with OK."}], [])
    ms = int((time.time() - started) * 1000)
    return f"Connected in {ms} ms. Model replied: {res.text.strip()[:60] or '(empty)'}"
