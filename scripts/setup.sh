#!/usr/bin/env bash
# One-command local setup: create .env if missing, set session secret, start Compose.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_FILE="$ROOT/.env"
EXAMPLE_FILE="$ROOT/.env.example"

new_session_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 32 | tr -d '/+=' | head -c 48
  else
    python -c "import secrets; print(secrets.token_urlsafe(32))"
  fi
}

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ ! -f "$EXAMPLE_FILE" ]]; then
    echo "Missing .env.example in $ROOT" >&2
    exit 1
  fi
  cp "$EXAMPLE_FILE" "$ENV_FILE"
  echo "Created .env from .env.example"
fi

if grep -qE '^SESSION_SECRET_KEY=change-me' "$ENV_FILE"; then
  secret="$(new_session_secret)"
  if sed --version >/dev/null 2>&1; then
    sed -i "s|^SESSION_SECRET_KEY=.*|SESSION_SECRET_KEY=${secret}|" "$ENV_FILE"
  else
    sed -i '' "s|^SESSION_SECRET_KEY=.*|SESSION_SECRET_KEY=${secret}|" "$ENV_FILE"
  fi
  echo "Generated SESSION_SECRET_KEY in .env"
fi

echo "Starting Docker Compose (postgres, redis, api, worker) ..."
exec docker compose up --build
