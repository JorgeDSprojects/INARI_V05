#!/usr/bin/env bash
# UNS_DASHBOARD/scripts/status.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose ps
