from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.agent import Agent


class AgentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self) -> list[Agent]:
        stmt = select(Agent).order_by(Agent.name.asc())
        return list(self.db.scalars(stmt).all())

    def list_paginated(self, *, offset: int, limit: int) -> list[Agent]:
        stmt = (
            select(Agent)
            .order_by(Agent.name.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def count(self) -> int:
        stmt = select(func.count()).select_from(Agent)
        return int(self.db.scalar(stmt) or 0)

    def get_by_id(self, agent_id: int) -> Agent | None:
        return self.db.get(Agent, agent_id)

    def get_by_name(self, name: str) -> Agent | None:
        normalized = name.strip()
        stmt = select(Agent).where(Agent.name == normalized)
        return self.db.scalars(stmt).first()

    def create(self, **fields) -> Agent:
        agent = Agent(**fields)
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def update(self, agent: Agent, **fields) -> Agent:
        for key, value in fields.items():
            setattr(agent, key, value)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def delete(self, agent: Agent) -> None:
        self.db.delete(agent)
        self.db.commit()
