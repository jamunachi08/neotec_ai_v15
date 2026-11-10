# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Lists the models installed on an OpenAI-compatible server (vLLM, Ollama, LM Studio, a router) and labels
the ones the open-model catalogue knows, so an administrator picks a model instead of typing its id."""

from __future__ import annotations

from neotec_ai.agents.setup import open_models


def _get(url, headers, timeout=15):
    import requests

    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        raise ValueError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def list_models(base_url: str, api_key: str = "", provider_type: str = "OpenAI Compatible") -> dict:
    if provider_type != "OpenAI Compatible":
        return {"models": [], "server": None,
                "message": "Model listing works for OpenAI-compatible servers (vLLM, Ollama, routers)."}
    base = (base_url or "").rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    found: dict[str, dict] = {}
    errors = []
    server = None

    try:
        data = _get(base + "/models", headers)
        for row in data.get("data") or []:
            mid = row.get("id")
            if mid:
                found[mid] = {"id": mid, "size": "", "details": row.get("owned_by") or ""}
        server = "OpenAI-compatible"
    except Exception as e:  # noqa: BLE001
        errors.append(f"/models: {str(e)[:160]}")

    root = open_models.ollama_root(base)
    if root != base or not found:
        try:
            data = _get(root + "/api/tags", headers)
            for row in data.get("models") or []:
                mid = row.get("name") or row.get("model")
                if not mid:
                    continue
                det = row.get("details") or {}
                found[mid] = {"id": mid, "size": open_models.human_size(row.get("size")),
                              "details": " ".join(x for x in (det.get("parameter_size"),
                                                              det.get("quantization_level")) if x)}
            server = "Ollama"
        except Exception as e:  # noqa: BLE001
            if not found:
                errors.append(f"/api/tags: {str(e)[:160]}")

    models = []
    for m in sorted(found.values(), key=lambda r: r["id"].lower()):
        cat = open_models.match_catalogue(m["id"])
        models.append({**m, "catalogue": cat["label"] if cat else None, "tier": cat["tier"] if cat else None,
                       "licence": cat["licence"] if cat else None,
                       "free": open_models.is_free_hosted(base, m["id"])})
    models.sort(key=lambda r: ({"coworker": 0, "light": 1, "datacentre": 2}.get(r["tier"], 3), r["id"].lower()))
    msg = "" if models else ("No models found. " + "; ".join(errors))
    return {"models": models, "server": server, "message": msg}
