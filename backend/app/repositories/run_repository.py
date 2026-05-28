from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.workflow_run import (
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PENDING,
    RUN_STATUS_RUNNING,
    RunLog,
    RunMessage,
    RunUsage,
    WorkflowRun,
)


class RunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_run(self, run_id: int) -> WorkflowRun | None:
        return self.db.get(WorkflowRun, run_id)

    def list_recent_runs(self, *, limit: int = 10) -> list[WorkflowRun]:
        stmt = (
            select(WorkflowRun)
            .order_by(WorkflowRun.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def count_runs(self) -> int:
        stmt = select(func.count()).select_from(WorkflowRun)
        return int(self.db.scalar(stmt) or 0)

    def list_recent_runs_paginated(self, *, offset: int, limit: int) -> list[WorkflowRun]:
        stmt = (
            select(WorkflowRun)
            .order_by(WorkflowRun.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def count_by_status(self) -> dict[str, int]:
        stmt = select(WorkflowRun.status, func.count()).group_by(WorkflowRun.status)
        rows = self.db.execute(stmt).all()
        return {str(status): int(count) for status, count in rows}

    def list_recent_messages(self, *, limit: int = 15) -> list[RunMessage]:
        stmt = (
            select(RunMessage)
            .order_by(RunMessage.created_at.desc(), RunMessage.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def list_runs_for_workflow(self, workflow_id: int) -> list[WorkflowRun]:
        stmt = (
            select(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id)
            .order_by(WorkflowRun.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def count_runs_for_workflow(self, workflow_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id)
        )
        return int(self.db.scalar(stmt) or 0)

    def list_runs_for_workflow_paginated(
        self,
        workflow_id: int,
        *,
        offset: int,
        limit: int,
    ) -> list[WorkflowRun]:
        stmt = (
            select(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id)
            .order_by(WorkflowRun.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def create_run(self, *, workflow_id: int, triggered_by: str = "manual") -> WorkflowRun:
        run = WorkflowRun(
            workflow_id=workflow_id,
            status=RUN_STATUS_PENDING,
            triggered_by=triggered_by,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def mark_running(self, run: WorkflowRun) -> WorkflowRun:
        run.status = RUN_STATUS_RUNNING
        run.started_at = datetime.now(timezone.utc)
        run.error = None
        self.db.commit()
        self.db.refresh(run)
        return run

    def mark_completed(self, run: WorkflowRun) -> WorkflowRun:
        run.status = RUN_STATUS_COMPLETED
        run.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(run)
        return run

    def mark_failed(self, run: WorkflowRun, error: str) -> WorkflowRun:
        run.status = RUN_STATUS_FAILED
        run.finished_at = datetime.now(timezone.utc)
        run.error = error[:4000]
        self.db.commit()
        self.db.refresh(run)
        return run

    def mark_cancelled(self, run: WorkflowRun, *, reason: str = "Stopped by user") -> WorkflowRun:
        run.status = RUN_STATUS_CANCELLED
        run.cancel_requested = True
        run.finished_at = datetime.now(timezone.utc)
        run.error = reason[:4000]
        self.db.commit()
        self.db.refresh(run)
        return run

    def request_cancel(self, run: WorkflowRun) -> WorkflowRun:
        run.cancel_requested = True
        self.db.commit()
        self.db.refresh(run)
        return run

    def is_cancel_requested(self, run_id: int) -> bool:
        stmt = select(WorkflowRun.cancel_requested).where(WorkflowRun.id == run_id)
        return bool(self.db.scalar(stmt))

    def add_message(
        self,
        *,
        run_id: int,
        content: str,
        role: str = "assistant",
        from_agent_id: int | None = None,
        to_agent_id: int | None = None,
        channel: str = "internal",
    ) -> RunMessage:
        message = RunMessage(
            run_id=run_id,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            role=role,
            content=content,
            channel=channel,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def add_log(
        self,
        *,
        run_id: int,
        message: str,
        level: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> RunLog:
        log = RunLog(
            run_id=run_id,
            level=level,
            message=message,
            log_metadata=metadata or {},
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def add_usage(
        self,
        *,
        run_id: int,
        agent_id: int | None,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: Decimal | float,
    ) -> RunUsage:
        usage = RunUsage(
            run_id=run_id,
            agent_id=agent_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=Decimal(str(cost_usd)),
        )
        self.db.add(usage)
        self.db.commit()
        self.db.refresh(usage)
        return usage

    def list_messages(self, run_id: int) -> list[RunMessage]:
        stmt = (
            select(RunMessage)
            .where(RunMessage.run_id == run_id)
            .order_by(RunMessage.created_at.asc(), RunMessage.id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def list_logs(self, run_id: int) -> list[RunLog]:
        stmt = (
            select(RunLog)
            .where(RunLog.run_id == run_id)
            .order_by(RunLog.created_at.asc(), RunLog.id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def list_usage(self, run_id: int) -> list[RunUsage]:
        stmt = (
            select(RunUsage)
            .where(RunUsage.run_id == run_id)
            .order_by(RunUsage.created_at.asc(), RunUsage.id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def total_cost(self, run_id: int) -> Decimal:
        stmt = select(func.coalesce(func.sum(RunUsage.cost_usd), 0)).where(
            RunUsage.run_id == run_id
        )
        return Decimal(str(self.db.scalar(stmt) or 0))
