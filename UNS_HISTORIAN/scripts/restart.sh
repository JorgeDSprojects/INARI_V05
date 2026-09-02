#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
service="${1:-}"
if [ -n "$service" ]; then
  docker compose restart "$service"
else
  docker compose down
  docker compose up -d --build
fi
