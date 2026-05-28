from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.models.workflow import Workflow, WorkflowAgent


class WorkflowRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _list_stmt(self, *, templates_only: bool | None = None):
        stmt = select(Workflow).options(selectinload(Workflow.agent_links))
        if templates_only is True:
            stmt = stmt.where(Workflow.is_template.is_(True))
        elif templates_only is False:
            stmt = stmt.where(Workflow.is_template.is_(False))
        return stmt.order_by(Workflow.name.asc())

    def list_all(self, *, templates_only: bool | None = None) -> list[Workflow]:
        return list(self.db.scalars(self._list_stmt(templates_only=templates_only)).all())

    def list_paginated(
        self,
        *,
        offset: int,
        limit: int,
        templates_only: bool | None = None,
    ) -> list[Workflow]:
        stmt = self._list_stmt(templates_only=templates_only).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def count(self, *, templates_only: bool | None = None) -> int:
        stmt = select(func.count()).select_from(Workflow)
        if templates_only is True:
            stmt = stmt.where(Workflow.is_template.is_(True))
        elif templates_only is False:
            stmt = stmt.where(Workflow.is_template.is_(False))
        return int(self.db.scalar(stmt) or 0)

    def count_templates(self) -> int:
        return self.count(templates_only=True)

    def get_by_id(self, workflow_id: int) -> Workflow | None:
        stmt = (
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .options(selectinload(Workflow.agent_links))
        )
        return self.db.scalars(stmt).first()

    def get_by_name(self, name: str, *, is_template: bool | None = None) -> Workflow | None:
        normalized = name.strip()
        stmt = select(Workflow).where(Workflow.name == normalized)
        if is_template is not None:
            stmt = stmt.where(Workflow.is_template.is_(is_template))
        return self.db.scalars(stmt).first()

    def create(self, *, agent_links: list[dict] | None = None, **fields) -> Workflow:
        workflow = Workflow(**fields)
        self.db.add(workflow)
        self.db.flush()
        if agent_links:
            for link in agent_links:
                self.db.add(
                    WorkflowAgent(
                        workflow_id=workflow.id,
                        agent_id=link["agent_id"],
                        node_id=link["node_id"],
                    )
                )
        self.db.commit()
        self.db.refresh(workflow)
        return self.get_by_id(workflow.id) or workflow

    def update(self, workflow: Workflow, *, agent_links: list[dict] | None = None, **fields) -> Workflow:
        for key, value in fields.items():
            setattr(workflow, key, value)
            if key == "graph_json":
                flag_modified(workflow, "graph_json")
        if agent_links is not None:
            for existing in list(workflow.agent_links):
                self.db.delete(existing)
            self.db.flush()
            for link in agent_links:
                self.db.add(
                    WorkflowAgent(
                        workflow_id=workflow.id,
                        agent_id=link["agent_id"],
                        node_id=link["node_id"],
                    )
                )
        self.db.commit()
        return self.get_by_id(workflow.id) or workflow

    def delete(self, workflow: Workflow) -> None:
        self.db.delete(workflow)
        self.db.commit()
