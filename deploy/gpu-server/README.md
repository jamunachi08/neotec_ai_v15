# GPU server kit for open models

Runs open-weight models (Qwen, gpt-oss, Gemma, Llama, Mistral…) on a GPU server you control, for example in a
Saudi data centre, and exposes them to Neotec Coworker over HTTPS with an API key.

| | Ollama profile | vLLM profile |
|---|---|---|
| Best for | Pilots, several models, quick switching | Production, many users, one model |
| Models | Ollama library names, e.g. `qwen3.6:27b` | Hugging Face ids, e.g. `Qwen/Qwen3.6-27B` |
| Tool calling | Built in for supported models | Needs the right `VLLM_TOOL_PARSER` |
| Neotec Coworker preset | Ollama (self-hosted) | vLLM (self-hosted) |

## Requirements

- Ubuntu 22.04 or 24.04 with an NVIDIA GPU. See the catalogue in `docs/OPEN_MODELS.md` for GPU sizes.
- NVIDIA driver, Docker and the NVIDIA Container Toolkit. Check with `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`.
- A DNS name pointing at the server, ports 80 and 443 open (Caddy obtains the TLS certificate).

## Install

```sh
cp .env.example .env          # set DOMAIN, API_KEY, UPSTREAM and the model
openssl rand -hex 32          # use the output as API_KEY
docker compose --profile ollama up -d     # UPSTREAM=ollama:11434
# or
docker compose --profile vllm up -d       # UPSTREAM=vllm:8000
./check.sh https://ai.example.com.sa <API_KEY>
```

The first start downloads the model (tens of gigabytes); watch it with `docker compose logs -f`.

## Connect Neotec Coworker

1. Coworker Setup → **Ollama (self-hosted)** or **vLLM (self-hosted)**.
2. Base URL `https://<DOMAIN>/v1`, API key = `API_KEY`, data location **On-Premises** (or **In Kingdom**).
3. **Find models on this server**, pick one, **Save and test connection**, then **Test tool calling**.
4. Only models that pass (or partly pass) the self-test run playbooks.

## Security

- Only Caddy is published. Ollama has no login of its own; never publish port 11434.
- Only `/v1/*` and `/api/tags` are forwarded; pulling or deleting models is not possible from outside.
- Rotate `API_KEY` by editing `.env`, `docker compose up -d`, and updating the provider in ERPNext.
- Restrict ports 80/443 to your Frappe Cloud region's egress addresses if your firewall allows it.
