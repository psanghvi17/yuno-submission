from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.workflow_run import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PENDING,
    RUN_STATUS_RUNNING,
    RunMessage,
    WorkflowRun,
)
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository


@dataclass
class DashboardStats:
    agent_count: int
    workflow_count: int
    template_count: int
    active_runs: int
    failed_runs: int
    completed_runs: int
    total_cost_usd: Decimal


@dataclass
class DashboardRunRow:
    id: int
    workflow_id: int
    workflow_name: str
    status: str
    triggered_by: str
    started_at: datetime | None
    error: str | None


@dataclass
class DashboardMessageRow:
    id: int
    run_id: int
    role: str
    channel: str
    content_preview: str
    created_at: datetime


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.agent_repo = AgentRepository(db)
        self.workflow_repo = WorkflowRepository(db)
        self.run_repo = RunRepository(db)

    def get_stats(self) -> DashboardStats:
        status_counts = self.run_repo.count_by_status()
        workflows = self.workflow_repo.list_all()
        template_count = sum(1 for w in workflows if w.is_template)
        workflow_count = sum(1 for w in workflows if not w.is_template)

        total_cost = Decimal("0")
        for run in self.run_repo.list_recent_runs(limit=200):
            total_cost += self.run_repo.total_cost(run.id)

        return DashboardStats(
            agent_count=self.agent_repo.count(),
            workflow_count=workflow_count,
            template_count=template_count,
            active_runs=status_counts.get(RUN_STATUS_PENDING, 0)
            + status_counts.get(RUN_STATUS_RUNNING, 0),
            failed_runs=status_counts.get(RUN_STATUS_FAILED, 0),
            completed_runs=status_counts.get(RUN_STATUS_COMPLETED, 0),
            total_cost_usd=total_cost,
        )

    def get_active_runs(self, *, limit: int = 8) -> list[DashboardRunRow]:
        runs = self.run_repo.list_recent_runs(limit=limit * 3)
        active = [
            r
            for r in runs
            if r.status in (RUN_STATUS_PENDING, RUN_STATUS_RUNNING)
        ][:limit]
        return self._run_rows(active)

    def get_recent_runs(self, *, limit: int = 10) -> list[DashboardRunRow]:
        return self._run_rows(self.run_repo.list_recent_runs(limit=limit))

    def get_failed_runs(self, *, limit: int = 5) -> list[DashboardRunRow]:
        runs = self.run_repo.list_recent_runs(limit=50)
        failed = [r for r in runs if r.status == RUN_STATUS_FAILED][:limit]
        return self._run_rows(failed)

    def get_recent_messages(self, *, limit: int = 12) -> list[DashboardMessageRow]:
        messages = self.run_repo.list_recent_messages(limit=limit)
        return [self._message_row(m) for m in messages]

    def _run_rows(self, runs: list[WorkflowRun]) -> list[DashboardRunRow]:
        rows: list[DashboardRunRow] = []
        for run in runs:
            workflow = self.workflow_repo.get_by_id(run.workflow_id)
            rows.append(
                DashboardRunRow(
                    id=run.id,
                    workflow_id=run.workflow_id,
                    workflow_name=workflow.name if workflow else f"Workflow #{run.workflow_id}",
                    status=run.status,
                    triggered_by=run.triggered_by,
                    started_at=run.started_at,
                    error=run.error,
                )
            )
        return rows

    @staticmethod
    def _message_row(message: RunMessage) -> DashboardMessageRow:
        content = message.content or ""
        preview = content[:120] + ("…" if len(content) > 120 else "")
        return DashboardMessageRow(
            id=message.id,
            run_id=message.run_id,
            role=message.role,
            channel=message.channel,
            content_preview=preview,
            created_at=message.created_at,
        )
