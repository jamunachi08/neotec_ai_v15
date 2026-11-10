# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Catalogue of open-weight models that can run on the customer's own GPU server (Ollama or vLLM) and be used by
coworkers through an OpenAI-compatible endpoint. Plain data, no Frappe import, so it is unit-tested directly.

Rules for entries
  * ``hf_id`` is filled only for repositories confirmed on the publisher's own page; otherwise ``None`` and the
    model is recognised on a server by ``match``.
  * ``tier`` is guidance, not a guarantee. The tool-calling self-test on the provider decides whether a model may
    run playbooks.
  * Hardware figures are approximate; 4-bit means a community quantised build (GGUF for Ollama, AWQ/GPTQ/FP8
    for vLLM).
"""

from __future__ import annotations

import re

TIERS = {
    "coworker": "Recommended for coworkers and playbooks",
    "light": "Summaries, drafting and simple questions; weak on multi-step playbooks",
    "datacentre": "Strong, but needs a multi-GPU data-centre server",
}

MODELS = [
    {
        "key": "qwen3.8-27b", "label": "Qwen3.8 27B", "family": "Qwen", "publisher": "Alibaba",
        "licence": "Apache 2.0", "kind": "Dense", "params": "27B",
        "gpu": "80 GB at full precision; about 20-24 GB with a 4-bit build",
        "tier": "coworker", "hf_id": "Qwen/Qwen3.8-27B", "match": [r"qwen3\.8[-_:]?27b"],
        "vllm_tool_parser": "hermes", "arabic": "Good",
        "notes": "Newest open general Qwen. Start here on a single 24-48 GB GPU.",
    },
    {
        "key": "qwen3.6-27b", "label": "Qwen3.6 27B", "family": "Qwen", "publisher": "Alibaba",
        "licence": "Apache 2.0", "kind": "Dense", "params": "27B",
        "gpu": "about 17 GB with a 4-bit build", "tier": "coworker", "hf_id": "Qwen/Qwen3.6-27B",
        "match": [r"qwen3\.6[-_:]?27b"], "vllm_tool_parser": "hermes", "arabic": "Good",
        "notes": "Proven and widely quantised; fits a single 24 GB card.",
    },
    {
        "key": "qwen3.6-35b-a3b", "label": "Qwen3.6 35B-A3B", "family": "Qwen", "publisher": "Alibaba",
        "licence": "Apache 2.0", "kind": "Mixture of experts (3B active)", "params": "35B",
        "gpu": "about 22-24 GB with a 4-bit build", "tier": "coworker", "hf_id": "Qwen/Qwen3.6-35B-A3B",
        "match": [r"qwen3\.6[-_:]?35b"], "vllm_tool_parser": "hermes", "arabic": "Good",
        "notes": "Fast answers because only 3B parameters work per token; good for many users at once.",
    },
    {
        "key": "qwen3.5-small", "label": "Qwen3.5 9B / 4B", "family": "Qwen", "publisher": "Alibaba",
        "licence": "Apache 2.0", "kind": "Dense", "params": "4-9B",
        "gpu": "8-12 GB", "tier": "light", "hf_id": "Qwen/Qwen3.5-9B",
        "match": [r"qwen3\.5[-_:]?(9b|4b|2b|0\.8b)"], "vllm_tool_parser": "hermes", "arabic": "Fair",
        "notes": "For laptops, demos and the quality-scoring provider.",
    },
    {
        "key": "qwen3.8-2.4t", "label": "Qwen3.8 2.4T-A95B", "family": "Qwen", "publisher": "Alibaba",
        "licence": "Qwen3.8 model licence (read before commercial use)", "kind": "Mixture of experts (95B active)",
        "params": "2.4T", "gpu": "multi-node data-centre cluster", "tier": "datacentre",
        "hf_id": "Qwen/Qwen3.8-2.4T-A95B", "match": [r"qwen3\.8[-_:]?2\.4t"], "vllm_tool_parser": "hermes",
        "arabic": "Good", "notes": "Text only and always reasons step by step; for national-scale hosting only.",
    },
    {
        "key": "gpt-oss-120b", "label": "gpt-oss 120B", "family": "gpt-oss", "publisher": "OpenAI",
        "licence": "Apache 2.0", "kind": "Mixture of experts (5.1B active)", "params": "117B",
        "gpu": "one 80 GB GPU", "tier": "coworker", "hf_id": "openai/gpt-oss-120b",
        "match": [r"gpt-?oss[-_:]?120b"], "vllm_tool_parser": "openai", "arabic": "Fair",
        "notes": "Strong reasoning and tool use; the best choice when one 80 GB GPU is available.",
    },
    {
        "key": "gpt-oss-20b", "label": "gpt-oss 20B", "family": "gpt-oss", "publisher": "OpenAI",
        "licence": "Apache 2.0", "kind": "Mixture of experts", "params": "21B",
        "gpu": "about 16 GB", "tier": "light", "hf_id": "openai/gpt-oss-20b",
        "match": [r"gpt-?oss[-_:]?20b"], "vllm_tool_parser": "openai", "arabic": "Fair",
        "notes": "Small and quick; run the self-test before giving it playbooks.",
    },
    {
        "key": "gemma-4", "label": "Gemma 4 (26B)", "family": "Gemma", "publisher": "Google",
        "licence": "Gemma licence", "kind": "Dense", "params": "26B",
        "gpu": "about 18-24 GB with a 4-bit build", "tier": "coworker", "hf_id": None,
        "match": [r"gemma[-_]?4"], "vllm_tool_parser": None, "arabic": "Good",
        "notes": "Good on consumer GPUs. Check the Gemma licence terms for your use.",
    },
    {
        "key": "llama-4-scout", "label": "Llama 4 Scout", "family": "Llama", "publisher": "Meta",
        "licence": "Llama 4 Community Licence", "kind": "Mixture of experts (17B active)", "params": "109B",
        "gpu": "one 80 GB GPU with a 4-bit build", "tier": "coworker",
        "hf_id": "meta-llama/Llama-4-Scout-17B-16E-Instruct", "match": [r"llama[-_]?4[-_:]?scout"],
        "vllm_tool_parser": "llama4_pythonic", "arabic": "Fair",
        "notes": "Very long context. Licence restricts the largest operators; read it first.",
    },
    {
        "key": "mistral-small", "label": "Mistral Small", "family": "Mistral", "publisher": "Mistral AI",
        "licence": "Apache 2.0 (check the exact version)", "kind": "Dense", "params": "24B",
        "gpu": "about 16-20 GB with a 4-bit build", "tier": "light", "hf_id": None,
        "match": [r"mistral[-_]?small"], "vllm_tool_parser": "mistral", "arabic": "Fair",
        "notes": "Efficient European model; good instruction following.",
    },
    {
        "key": "deepseek-v4", "label": "DeepSeek V4", "family": "DeepSeek", "publisher": "DeepSeek",
        "licence": "See the model card", "kind": "Mixture of experts", "params": "very large",
        "gpu": "multi-GPU data-centre server", "tier": "datacentre", "hf_id": None,
        "match": [r"deepseek[-_]?v4"], "vllm_tool_parser": None, "arabic": "Good",
        "notes": "Among the strongest open models; only for data-centre hosting.",
    },
]

# Hosted services that offer some open models free of charge. Always External: free tiers may log prompts.
FREE_HOSTED_HINTS = [r"openrouter\.ai"]
FREE_MODEL_SUFFIX = ":free"


def match_catalogue(model_id: str | None) -> dict | None:
    """Recognises a model name as served by Ollama or vLLM (e.g. 'qwen3.6:27b', 'Qwen/Qwen3.6-27B-AWQ')."""
    name = (model_id or "").lower().replace(" ", "")
    if not name:
        return None
    for m in MODELS:
        if m["hf_id"] and name.split(":")[0].startswith(m["hf_id"].lower()):
            return m
        if any(re.search(p, name) for p in m["match"]):
            return m
    return None


def is_free_hosted(base_url: str | None, model: str | None) -> bool:
    url = (base_url or "").lower()
    return any(re.search(p, url) for p in FREE_HOSTED_HINTS) and (model or "").lower().endswith(FREE_MODEL_SUFFIX)


def ollama_root(base_url: str | None) -> str:
    """http://host:11434/v1 -> http://host:11434 (Ollama's own API lives at the root)."""
    url = (base_url or "").rstrip("/")
    return url[:-3] if url.endswith("/v1") else url


def human_size(num_bytes) -> str:
    try:
        n = float(num_bytes)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return ""
