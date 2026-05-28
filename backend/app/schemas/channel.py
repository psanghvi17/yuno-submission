from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChannelLinkCreate(BaseModel):
    agent_id: int
    channel_type: str = "telegram"
    chat_id: str
    is_active: bool = True


class ChannelLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int
    channel_type: str
    config: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ChannelLinkDetail(ChannelLinkRead):
    agent_name: str | None = None
    chat_id: str | None = None
    conversation_run_id: int | None = None


class TelegramWebhookUpdate(BaseModel):
    update_id: int | None = None
    message: dict[str, Any] | None = None
    edited_message: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")
