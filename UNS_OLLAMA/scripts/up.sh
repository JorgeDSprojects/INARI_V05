#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d
echo "UNS Ollama is starting. Use scripts/status.sh to check container health, then pull a model:"
echo "  docker exec uns_ollama ollama pull \${OLLAMA_MODEL:-qwen2.5:14b-instruct}"
