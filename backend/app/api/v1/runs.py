from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.run import WorkflowRunDetail, WorkflowRunRead
from app.services.run_service import RunExecutionError, RunNotFound, RunCannotBeCancelled, RunService
from app.services.workflow_service import WorkflowNotFound

router = APIRouter(prefix="/runs", tags=["Runs"])


def _run_service(db: Session = Depends(get_db)) -> RunService:
    return RunService(
        RunRepository(db),
        WorkflowRepository(db),
        AgentRepository(db),
    )


@router.post(
    "",
    response_model=WorkflowRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue workflow run",
)
def start_workflow_run(
    workflow_id: int,
    task: str = "Execute the workflow.",
    mock: bool | None = None,
    service: RunService = Depends(_run_service),
    _user=Depends(get_current_user),
):
    """Enqueue a workflow run; execution happens in the Celery worker."""
    try:
        return service.enqueue_run(
            workflow_id,
            task_input=task,
            triggered_by="api",
            mock_llm=mock,
        )
    except WorkflowNotFound:
        raise HTTPException(status_code=404, detail="Workflow not found") from None
    except RunExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/demo",
    response_model=WorkflowRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue hardcoded two-agent demo run",
)
def start_demo_run(
    task: str = "Research AI agent orchestration and summarize findings.",
    workflow_id: int | None = None,
    mock: bool | None = None,
    service: RunService = Depends(_run_service),
    _user=Depends(get_current_user),
):
    try:
        return service.enqueue_demo_two_agent_run(
            workflow_id=workflow_id,
            task_input=task,
            triggered_by="api",
            mock_llm=mock,
        )
    except RunExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/{run_id}",
    response_model=WorkflowRunDetail,
    summary="Get run with messages, logs, and usage",
)
def get_run(
    run_id: int,
    service: RunService = Depends(_run_service),
    _user=Depends(get_current_user),
):
    try:
        return service.get_run_detail(run_id)
    except RunNotFound:
        raise HTTPException(status_code=404, detail="Run not found") from None


@router.post(
    "/{run_id}/stop",
    response_model=WorkflowRunRead,
    summary="Stop a pending or running workflow run",
)
def stop_run(
    run_id: int,
    service: RunService = Depends(_run_service),
    _user=Depends(get_current_user),
):
    try:
        return service.cancel_run(run_id)
    except RunNotFound:
        raise HTTPException(status_code=404, detail="Run not found") from None
    except RunCannotBeCancelled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
