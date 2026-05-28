from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.channel_link import CHANNEL_TYPE_TELEGRAM, ChannelLink


class ChannelRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, link_id: int) -> ChannelLink | None:
        return self.db.get(ChannelLink, link_id)

    def _list_stmt(self):
        return (
            select(ChannelLink)
            .options(joinedload(ChannelLink.agent))
            .order_by(ChannelLink.id.desc())
        )

    def list_all(self) -> list[ChannelLink]:
        return list(self.db.scalars(self._list_stmt()).unique().all())

    def list_paginated(self, *, offset: int, limit: int) -> list[ChannelLink]:
        stmt = self._list_stmt().offset(offset).limit(limit)
        return list(self.db.scalars(stmt).unique().all())

    def count(self) -> int:
        stmt = select(func.count()).select_from(ChannelLink)
        return int(self.db.scalar(stmt) or 0)

    def list_by_agent(self, agent_id: int) -> list[ChannelLink]:
        stmt = select(ChannelLink).where(ChannelLink.agent_id == agent_id)
        return list(self.db.scalars(stmt).all())

    def get_telegram_by_chat_id(self, chat_id: str) -> ChannelLink | None:
        stmt = (
            select(ChannelLink)
            .options(joinedload(ChannelLink.agent))
            .where(
                ChannelLink.channel_type == CHANNEL_TYPE_TELEGRAM,
                ChannelLink.is_active.is_(True),
            )
        )
        for link in self.db.scalars(stmt).unique().all():
            config = link.config or {}
            if str(config.get("chat_id", "")) == str(chat_id):
                return link
        return None

    def get_active_telegram_for_agent(self, agent_id: int) -> ChannelLink | None:
        stmt = (
            select(ChannelLink)
            .where(
                ChannelLink.agent_id == agent_id,
                ChannelLink.channel_type == CHANNEL_TYPE_TELEGRAM,
                ChannelLink.is_active.is_(True),
            )
            .order_by(ChannelLink.id.desc())
        )
        return self.db.scalars(stmt).first()

    def create(
        self,
        *,
        agent_id: int,
        channel_type: str,
        config: dict[str, Any],
        is_active: bool = True,
    ) -> ChannelLink:
        link = ChannelLink(
            agent_id=agent_id,
            channel_type=channel_type,
            config=config,
            is_active=is_active,
        )
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link

    def update(self, link: ChannelLink, **fields: Any) -> ChannelLink:
        for key, value in fields.items():
            setattr(link, key, value)
        self.db.commit()
        self.db.refresh(link)
        return link

    def update_config(self, link: ChannelLink, config: dict[str, Any]) -> ChannelLink:
        link.config = config
        self.db.commit()
        self.db.refresh(link)
        return link

    def delete(self, link: ChannelLink) -> None:
        self.db.delete(link)
        self.db.commit()
