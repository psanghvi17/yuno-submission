#!/usr/bin/env bash
# Reset Telegram getUpdates / webhook state for local dev (fixes 409 Conflict).
# Run from repo root:  bash scripts/reset_telegram.sh
# (chmod +x may fail on /mnt/c — use bash explicitly)

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "Missing .env" >&2
  exit 1
fi

# Strip CRLF from .env lines (common when edited on Windows / opened in WSL on /mnt/c)
load_env_token() {
  grep -E '^[[:space:]]*TELEGRAM_BOT_TOKEN[[:space:]]*=' .env | head -1 \
    | cut -d= -f2- \
    | tr -d '\r' \
    | tr -d '"' \
    | tr -d "'" \
    | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

TOKEN="$(load_env_token)"
if [[ -z "${TOKEN}" ]]; then
  echo "TELEGRAM_BOT_TOKEN not set in .env" >&2
  exit 1
fi

if [[ ! "${TOKEN}" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
  echo "TELEGRAM_BOT_TOKEN looks invalid (hidden chars or bad format)." >&2
  echo "Fix Windows line endings:  sed -i 's/\\r$//' .env" >&2
  printf 'Token length: %s (expect digits:secret with no spaces)\\n' "${#TOKEN}"
  exit 1
fi

BASE="https://api.telegram.org/bot${TOKEN}"

echo "==> Stopping Docker stack..."
docker compose down

echo "==> Waiting 30s for Telegram to release getUpdates..."
sleep 30

echo "==> deleteWebhook..."
curl -sS -X POST "${BASE}/deleteWebhook?drop_pending_updates=true" || true
echo ""

echo "==> getWebhookInfo..."
curl -sS "${BASE}/getWebhookInfo" || true
echo ""

echo "==> Probing getUpdates..."
PROBE_FILE="${TMPDIR:-/tmp}/tg_probe_$$.json"
HTTP_CODE="$(curl -sS -o "$PROBE_FILE" -w '%{http_code}' "${BASE}/getUpdates?timeout=0" || true)"
if [[ "$HTTP_CODE" == "409" ]]; then
  echo ""
  echo "STILL 409: Another machine or app is using this bot token."
  echo "  - Revoke in @BotFather, set NEW token in .env"
  echo "  - Run: sed -i 's/\\r$//' .env  then run this script again"
  cat "$PROBE_FILE" 2>/dev/null || true
  echo ""
elif [[ "$HTTP_CODE" == "200" ]]; then
  echo "OK: getUpdates slot is free"
  cat "$PROBE_FILE"
  echo ""
else
  echo "Probe HTTP ${HTTP_CODE:-000} (000 = curl could not reach Telegram or bad URL)"
  cat "$PROBE_FILE" 2>/dev/null || true
  echo ""
fi
rm -f "$PROBE_FILE"

echo "==> Starting stack..."
docker compose up -d

echo ""
echo "Done. Logs: docker compose logs api -f"
echo "Then message your bot in Telegram."
