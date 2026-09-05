#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
service="${1:-}"
if [ -n "$service" ]; then
  docker compose logs -f "$service"
else
  docker compose logs -f
fi
