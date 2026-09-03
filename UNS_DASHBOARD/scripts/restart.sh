#!/usr/bin/env bash
# UNS_DASHBOARD/scripts/restart.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose restart "$@"
