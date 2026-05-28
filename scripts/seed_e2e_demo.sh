#!/usr/bin/env bash
# Seed 5-agent Product Launch pipeline and optionally start a run.
# From repo root:  bash scripts/seed_e2e_demo.sh [--run] [--mock]

set -euo pipefail
cd "$(dirname "$0")/.."

ARGS=()
for arg in "$@"; do
  ARGS+=("$arg")
done

docker compose exec -T api python scripts/seed_e2e_demo.py "${ARGS[@]}"
