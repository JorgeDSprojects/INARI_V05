#!/usr/bin/env bash
# UNS_DASHBOARD/scripts/down.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down
