# UNS Ollama

A GPU-accelerated local LLM host for `UNS_DASHBOARD`'s chat agent (and any
future consumer). Not a dependency of any other module — purely an
inference backend reached over HTTP.

See `UNS_DASHBOARD/docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md`
for how this fits into the broader system.

## Quickstart

```bash
cp .env.example .env
./scripts/up.sh
docker exec uns_ollama ollama pull qwen2.5:14b-instruct
```

## Pointing at a remote inference host instead (e.g. a DGX Spark)

This container is optional. `UNS_DASHBOARD/backend`'s `LLM_BASE_URL` can
point at any OpenAI-compatible endpoint instead — including Ollama or
vLLM running on a remote machine — with no code change, only
configuration. Set `LLM_BASE_URL` to that machine's address and stop
(or never start) this local container.

## Operations

- `./scripts/up.sh` / `down.sh` / `restart.sh` / `logs.sh` / `status.sh`
