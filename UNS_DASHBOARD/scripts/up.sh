#!/usr/bin/env bash
# UNS_DASHBOARD/scripts/up.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d --build
echo "UNS Dashboard is starting. Use scripts/status.sh to check container health."
