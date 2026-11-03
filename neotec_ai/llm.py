"""Provider adapters. One entry point: complete(settings, system, messages) -> (text, tokens).

`messages` is a list of {"role": "user" | "assistant", "content": str}.
"""

import requests

DEFAULT_BASE_URLS = {
    "Google Gemini": "https://generativelanguage.googleapis.com/v1beta",
    "Anthropic Claude": "https://api.anthropic.com/v1",
    "OpenAI": "https://api.openai.com/v1",
    "OpenAI-Compatible / Ollama": "http://localhost:11434/v1",
}


class LLMError(Exception):
    pass


def complete(settings, api_key, system, messages):
    provider = settings.provider
    base = (settings.api_endpoint or DEFAULT_BASE_URLS.get(provider) or "").rstrip("/")
    opts = {
        "model": settings.model,
        "api_key": api_key,
        "base": base,
        "max_tokens": settings.max_tokens or 2048,
        "temperature": settings.temperature if settings.temperature is not None else 0.2,
        "timeout": settings.request_timeout or 60,
    }

    if provider == "Google Gemini":
        return _gemini(system, messages, **opts)
    if provider == "Anthropic Claude":
        return _anthropic(system, messages, **opts)
    if provider in ("OpenAI", "OpenAI-Compatible / Ollama"):
        return _openai(system, messages, native_openai=(provider == "OpenAI"), **opts)
    raise LLMError(f"Unsupported provider: {provider}")


def _post(url, payload, headers, timeout):
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise LLMError(f"Could not reach the AI provider: {e.__class__.__name__}") from e
    if res.status_code >= 400:
        detail = res.text[:500]
        try:
            body = res.json()
            err = body.get("error")
            detail = (err.get("message") if isinstance(err, dict) else err) or detail
        except ValueError:
            pass
        raise LLMError(f"Provider returned HTTP {res.status_code}: {detail}")
    try:
        return res.json()
    except ValueError as e:
        raise LLMError("Provider returned a non-JSON response.") from e


def _gemini(system, messages, model, api_key, base, max_tokens, temperature, timeout):
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in messages
    ]
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-goog-api-key"] = api_key  # header, never the URL
    data = _post(f"{base}/models/{model}:generateContent", payload, headers, timeout)

    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates returned")
        raise LLMError(f"Gemini returned no answer ({reason}).")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    tokens = (data.get("usageMetadata") or {}).get("totalTokenCount", 0)
    return text, tokens


def _anthropic(system, messages, model, api_key, base, max_tokens, temperature, timeout):
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": _merge_same_role(messages),
    }
    headers = {
        "x-api-key": api_key or "",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    data = _post(f"{base}/messages", payload, headers, timeout)
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    usage = data.get("usage") or {}
    return text, usage.get("input_tokens", 0) + usage.get("output_tokens", 0)


def _openai(system, messages, model, api_key, base, max_tokens, temperature, timeout, native_openai):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": temperature,
    }
    # OpenAI's current models use max_completion_tokens; most compatible servers still use max_tokens.
    payload["max_completion_tokens" if native_openai else "max_tokens"] = max_tokens

    url = f"{base}/chat/completions"
    try:
        data = _post(url, payload, headers, timeout)
    except LLMError as e:
        # Some reasoning models reject a non-default temperature; retry once without it.
        if "temperature" not in str(e).lower():
            raise
        payload.pop("temperature", None)
        data = _post(url, payload, headers, timeout)

    choices = data.get("choices") or []
    if not choices:
        raise LLMError("Provider returned no choices.")
    text = (choices[0].get("message") or {}).get("content") or ""
    return text, (data.get("usage") or {}).get("total_tokens", 0)


def _merge_same_role(messages):
    """Anthropic requires alternating roles starting with user; merge any consecutive duplicates."""
    merged = []
    for m in messages:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1] = {"role": m["role"], "content": merged[-1]["content"] + "\n\n" + m["content"]}
        else:
            merged.append(dict(m))
    if merged and merged[0]["role"] != "user":
        merged.insert(0, {"role": "user", "content": "(conversation continues)"})
    return merged
