from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class InboundMessage:
    chat_id: str
    text: str
    message_id: int | None = None
    from_user: str | None = None


class ChannelAdapter(ABC):
    channel_type: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when credentials are present."""

    @abstractmethod
    def send_message(self, chat_id: str, text: str) -> dict:
        """Deliver outbound text to the external channel."""

    @abstractmethod
    def parse_inbound(self, payload: dict) -> InboundMessage | None:
        """Extract a human message from a channel webhook payload."""
