from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.run_service import RunService
from app.workers.celery_app import celery_app


def _open_worker_db() -> Session:
    return SessionLocal()


@celery_app.task(name="execute_workflow_run", bind=True, max_retries=0)
def execute_workflow_run(
    self,
    run_id: int,
    *,
    task_input: str = "Execute the workflow.",
    mock_llm: bool | None = None,
    demo: bool = False,
) -> dict:
    """Worker entrypoint: load run from DB and execute LangGraph."""
    db = _open_worker_db()
    try:
        service = RunService(
            RunRepository(db),
            WorkflowRepository(db),
            AgentRepository(db),
        )
        run = service.execute_run(
            run_id,
            task_input=task_input,
            mock_llm=mock_llm,
            demo=demo,
        )
        return {"run_id": run.id, "status": run.status}
    finally:
        db.close()


@celery_app.task(name="process_telegram_update", bind=True, max_retries=0)
def process_telegram_update(self, payload: dict) -> dict:
    """Handle inbound Telegram message and reply via linked agent."""
    from app.services.channel_service import build_channel_service

    db = _open_worker_db()
    try:
        service = build_channel_service(db)
        return service.handle_telegram_update(payload)
    finally:
        db.close()
