#!/usr/bin/env sh
# Quick smoke check after docker compose up.
set -e
BASE_URL="${BASE_URL:-http://localhost:3000}"

echo "Checking ${BASE_URL}/health ..."
curl -sf "${BASE_URL}/health" | grep -q '"status":"ok"' && echo "OK: health" || {
  echo "FAIL: health endpoint"
  exit 1
}

echo "Checking login page ..."
curl -sf -o /dev/null -w "%{http_code}" "${BASE_URL}/auth/login" | grep -q 200 && echo "OK: login page" || {
  echo "FAIL: login page"
  exit 1
}

echo "All checks passed."
