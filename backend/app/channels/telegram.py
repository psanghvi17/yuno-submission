from __future__ import annotations

import logging
from typing import Any

import httpx

from app.channels.base import ChannelAdapter, InboundMessage
from app.config import get_settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramPollingConflictError(Exception):
    """Raised when another client is already polling or a webhook is active."""


class TelegramChannel(ChannelAdapter):
    channel_type = "telegram"

    def __init__(self, bot_token: str | None = None) -> None:
        settings = get_settings()
        self._token = (bot_token or settings.telegram_bot_token).strip()

    def is_configured(self) -> bool:
        return bool(self._token)

    @property
    def _api_url(self) -> str:
        return f"{TELEGRAM_API_BASE}/bot{self._token}"

    def send_message(self, chat_id: str, text: str) -> dict:
        if not self.is_configured():
            return {
                "ok": False,
                "skipped": True,
                "reason": "TELEGRAM_BOT_TOKEN not configured",
            }
        payload = {
            "chat_id": chat_id,
            "text": text[:4096],
            "disable_web_page_preview": True,
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{self._api_url}/sendMessage", json=payload)
            response.raise_for_status()
            return response.json()

    def parse_inbound(self, payload: dict) -> InboundMessage | None:
        message = payload.get("message") or payload.get("edited_message")
        if not isinstance(message, dict):
            return None
        text = message.get("text") or message.get("caption")
        if not text or not str(text).strip():
            return None
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return None
        from_user = None
        sender = message.get("from")
        if isinstance(sender, dict):
            from_user = sender.get("username") or sender.get("first_name")
        return InboundMessage(
            chat_id=str(chat_id),
            text=str(text).strip(),
            message_id=message.get("message_id"),
            from_user=from_user,
        )

    def delete_webhook(self, drop_pending_updates: bool = False) -> dict:
        """Remove webhook so long-polling can be used (webhook + polling conflict)."""
        if not self.is_configured():
            return {"ok": True, "skipped": True}
        payload = {"drop_pending_updates": drop_pending_updates}
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{self._api_url}/deleteWebhook", json=payload)
            response.raise_for_status()
            return response.json()

    def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[dict]:
        if not self.is_configured():
            return []
        params: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        with httpx.Client(timeout=float(timeout + 10)) as client:
            response = client.get(f"{self._api_url}/getUpdates", params=params)
            if response.status_code == 409:
                raise TelegramPollingConflictError(
                    "Another getUpdates client or webhook is active for this bot"
                )
            response.raise_for_status()
            body = response.json()
        if not body.get("ok"):
            return []
        result = body.get("result")
        return result if isinstance(result, list) else []

    def set_webhook(self, url: str, secret_token: str | None = None) -> dict:
        payload: dict[str, Any] = {"url": url}
        if secret_token:
            payload["secret_token"] = secret_token
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{self._api_url}/setWebhook", json=payload)
            response.raise_for_status()
            return response.json()
