#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d --build
echo "UNS MCP (HTTP) is starting. Use scripts/status.sh to check container health."
