from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_web
from app.models.user import User
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.run_log_export import format_run_logs_export
from app.services.run_service import RunNotFound, RunCannotBeCancelled, RunService
from app.services.workflow_service import WorkflowNotFound
from app.templating import templates
from app.web.pagination import (
    DEFAULT_PER_PAGE,
    build_pagination,
    offset_limit,
    preserve_query,
)

router = APIRouter(tags=["runs-web"])


def _run_service(db: Session = Depends(get_db)) -> RunService:
    return RunService(
        RunRepository(db),
        WorkflowRepository(db),
        AgentRepository(db),
    )


def _load_run_detail(run_id: int, run_service: RunService):
    try:
        return run_service.get_run_detail(run_id)
    except RunNotFound:
        return None


@router.post("/workflows/{workflow_id}/run")
def workflow_run_enqueue(
    workflow_id: int,
    _user: User = Depends(get_current_user_web),
    service: RunService = Depends(_run_service),
    task: str = Form("Execute the workflow."),
):
    try:
        run = service.enqueue_run(
            workflow_id,
            task_input=task,
            triggered_by="ui",
        )
    except WorkflowNotFound:
        return RedirectResponse(
            url="/workflows?flash=not_found",
            status_code=status.HTTP_302_FOUND,
        )
    except Exception:
        return RedirectResponse(
            url=f"/workflows/{workflow_id}?flash=run_error",
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(
        url=f"/runs/{run.id}?flash=queued",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/runs/{run_id}/stop")
def runs_stop(
    run_id: int,
    _user: User = Depends(get_current_user_web),
    service: RunService = Depends(_run_service),
):
    try:
        service.cancel_run(run_id)
    except RunNotFound:
        return RedirectResponse(url="/runs", status_code=status.HTTP_302_FOUND)
    except RunCannotBeCancelled:
        return RedirectResponse(
            url=f"/runs/{run_id}?flash=stop_error",
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(
        url=f"/runs/{run_id}?flash=stop_requested",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/runs", response_class=HTMLResponse, name="runs_list")
def runs_list(
    request: Request,
    page: int = Query(1, ge=1),
    user: User = Depends(get_current_user_web),
    db: Session = Depends(get_db),
):
    run_repo = RunRepository(db)
    workflow_repo = WorkflowRepository(db)
    offset, limit = offset_limit(page, DEFAULT_PER_PAGE)
    pagination = build_pagination(
        run_repo.list_recent_runs_paginated(offset=offset, limit=limit),
        total=run_repo.count_runs(),
        page=page,
        per_page=DEFAULT_PER_PAGE,
    )
    rows = []
    for run in pagination.items:
        workflow = workflow_repo.get_by_id(run.workflow_id)
        rows.append(
            {
                "run": run,
                "workflow_name": workflow.name if workflow else f"Workflow #{run.workflow_id}",
            }
        )
    return templates.TemplateResponse(
        request,
        "runs/list.html",
        {
            "user": user,
            "rows": rows,
            "pagination": pagination,
            "query_extra": preserve_query(request, exclude={"page"}),
            "active_nav": "runs",
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse, name="runs_detail")
def runs_detail(
    request: Request,
    run_id: int,
    user: User = Depends(get_current_user_web),
    run_service: RunService = Depends(_run_service),
    db: Session = Depends(get_db),
):
    detail = _load_run_detail(run_id, run_service)
    if detail is None:
        return RedirectResponse(url="/workflows", status_code=status.HTTP_302_FOUND)

    workflow_repo = WorkflowRepository(db)
    workflow = workflow_repo.get_by_id(detail.workflow_id)
    workflow_name = workflow.name if workflow else f"Workflow #{detail.workflow_id}"

    return templates.TemplateResponse(
        request,
        "runs/detail.html",
        {
            "user": user,
            "run": detail,
            "workflow_name": workflow_name,
            "flash": request.query_params.get("flash"),
            "active_nav": "workflows",
        },
    )


@router.get("/runs/{run_id}/download-logs", name="runs_download_logs")
def runs_download_logs(
    run_id: int,
    _user: User = Depends(get_current_user_web),
    run_service: RunService = Depends(_run_service),
    db: Session = Depends(get_db),
):
    detail = _load_run_detail(run_id, run_service)
    if detail is None:
        return RedirectResponse(url="/workflows", status_code=status.HTTP_302_FOUND)

    workflow_repo = WorkflowRepository(db)
    workflow = workflow_repo.get_by_id(detail.workflow_id)
    workflow_name = workflow.name if workflow else f"Workflow #{detail.workflow_id}"

    body = format_run_logs_export(run=detail, workflow_name=workflow_name)
    filename = f"run-{run_id}-logs.txt"
    return Response(
        content=body,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/fragment/status", response_class=HTMLResponse)
def runs_fragment_status(
    request: Request,
    run_id: int,
    _user: User = Depends(get_current_user_web),
    run_service: RunService = Depends(_run_service),
):
    detail = _load_run_detail(run_id, run_service)
    if detail is None:
        return RedirectResponse(url="/workflows", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request,
        "runs/partials/status.html",
        {"run": detail},
    )


@router.get("/runs/{run_id}/fragment/toolbar-status", response_class=HTMLResponse)
def runs_fragment_toolbar_status(
    request: Request,
    run_id: int,
    _user: User = Depends(get_current_user_web),
    run_service: RunService = Depends(_run_service),
):
    detail = _load_run_detail(run_id, run_service)
    if detail is None:
        return RedirectResponse(url="/workflows", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request,
        "runs/partials/toolbar_status.html",
        {"run": detail},
    )


@router.get("/runs/{run_id}/fragment/logs", response_class=HTMLResponse)
def runs_fragment_logs(
    request: Request,
    run_id: int,
    _user: User = Depends(get_current_user_web),
    run_service: RunService = Depends(_run_service),
):
    detail = _load_run_detail(run_id, run_service)
    if detail is None:
        return RedirectResponse(url="/workflows", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request,
        "runs/partials/logs.html",
        {"run": detail},
    )


@router.get("/runs/{run_id}/fragment/messages", response_class=HTMLResponse)
def runs_fragment_messages(
    request: Request,
    run_id: int,
    _user: User = Depends(get_current_user_web),
    run_service: RunService = Depends(_run_service),
):
    detail = _load_run_detail(run_id, run_service)
    if detail is None:
        return RedirectResponse(url="/workflows", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request,
        "runs/partials/messages.html",
        {"run": detail},
    )


@router.get("/runs/{run_id}/fragment/usage", response_class=HTMLResponse)
def runs_fragment_usage(
    request: Request,
    run_id: int,
    _user: User = Depends(get_current_user_web),
    run_service: RunService = Depends(_run_service),
):
    detail = _load_run_detail(run_id, run_service)
    if detail is None:
        return RedirectResponse(url="/workflows", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request,
        "runs/partials/usage.html",
        {"run": detail},
    )


@router.get("/runs/{run_id}/fragment/history", response_class=HTMLResponse)
def runs_fragment_history(
    request: Request,
    run_id: int,
    _user: User = Depends(get_current_user_web),
    run_service: RunService = Depends(_run_service),
    db: Session = Depends(get_db),
):
    detail = _load_run_detail(run_id, run_service)
    if detail is None:
        return RedirectResponse(url="/workflows", status_code=status.HTTP_302_FOUND)
    agent_repo = AgentRepository(db)
    agent_names = {a.id: a.name for a in agent_repo.list_all()}
    return templates.TemplateResponse(
        request,
        "runs/partials/history_content.html",
        {"run": detail, "agent_names": agent_names},
    )
