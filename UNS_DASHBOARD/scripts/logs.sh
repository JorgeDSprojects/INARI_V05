#!/usr/bin/env bash
# UNS_DASHBOARD/scripts/logs.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose logs -f "$@"
