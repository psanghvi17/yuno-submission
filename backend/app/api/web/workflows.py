from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.deps import (
    get_agent_repository,
    get_current_user_web,
    get_workflow_repository,
)
from app.web.pagination import (
    DEFAULT_PER_PAGE,
    build_pagination,
    offset_limit,
    paginate_slice,
    preserve_query,
)
from app.models.user import User
from app.models.workflow import Workflow
from app.core.database import get_db
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from sqlalchemy.orm import Session
from app.schemas.workflow import WorkflowUpdate
from app.services.workflow_service import (
    WorkflowNotFound,
    WorkflowService,
    WorkflowValidationError,
)
from app.templating import templates

router = APIRouter(tags=["workflows-web"])


def _workflow_service(
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
    agent_repo: AgentRepository = Depends(get_agent_repository),
) -> WorkflowService:
    return WorkflowService(workflow_repo, agent_repo)


def _list_context(
    *,
    user: User,
    workflows: list[Workflow],
    page_title: str,
    active_nav: str,
    is_templates_page: bool,
    flash: str | None = None,
    pagination=None,
    query_extra: str = "",
) -> dict:
    return {
        "user": user,
        "workflows": workflows,
        "page_title": page_title,
        "active_nav": active_nav,
        "is_templates_page": is_templates_page,
        "flash": flash,
        "pagination": pagination,
        "query_extra": query_extra,
    }


def _detail_context(
    *,
    user: User,
    workflow: Workflow,
    service: WorkflowService,
    flash: str | None = None,
    errors: dict[str, str] | None = None,
    form: dict | None = None,
    recent_runs: list | None = None,
    runs_pagination=None,
    agent_links_pagination=None,
    runs_query_extra: str = "",
    links_query_extra: str = "",
) -> dict:
    default_form = {
        "name": workflow.name,
        "description": workflow.description,
    }
    if form:
        default_form.update(form)
    return {
        "user": user,
        "workflow": workflow,
        "node_count": service.node_count(workflow),
        "form": default_form,
        "errors": errors or {},
        "flash": flash,
        "active_nav": "workflows",
        "recent_runs": recent_runs or [],
        "runs_pagination": runs_pagination,
        "agent_links_pagination": agent_links_pagination,
        "runs_query_extra": runs_query_extra,
        "links_query_extra": links_query_extra,
        "default_run_task": "Explain what Docker is in two short sentences.",
    }


@router.get("/workflows", response_class=HTMLResponse, name="workflows_list")
def workflows_list(
    request: Request,
    page: int = Query(1, ge=1),
    user: User = Depends(get_current_user_web),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
):
    offset, limit = offset_limit(page, DEFAULT_PER_PAGE)
    pagination = build_pagination(
        workflow_repo.list_paginated(
            offset=offset,
            limit=limit,
            templates_only=False,
        ),
        total=workflow_repo.count(templates_only=False),
        page=page,
        per_page=DEFAULT_PER_PAGE,
    )
    return templates.TemplateResponse(
        request,
        "workflows/list.html",
        _list_context(
            user=user,
            workflows=pagination.items,
            page_title="Workflows",
            active_nav="workflows",
            is_templates_page=False,
            flash=request.query_params.get("flash"),
            pagination=pagination,
            query_extra=preserve_query(request, exclude={"page"}),
        ),
    )


@router.get("/workflows/templates", response_class=HTMLResponse, name="workflows_templates")
def workflows_templates(
    request: Request,
    page: int = Query(1, ge=1),
    user: User = Depends(get_current_user_web),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
):
    offset, limit = offset_limit(page, DEFAULT_PER_PAGE)
    pagination = build_pagination(
        workflow_repo.list_paginated(
            offset=offset,
            limit=limit,
            templates_only=True,
        ),
        total=workflow_repo.count(templates_only=True),
        page=page,
        per_page=DEFAULT_PER_PAGE,
    )
    return templates.TemplateResponse(
        request,
        "workflows/templates.html",
        _list_context(
            user=user,
            workflows=pagination.items,
            page_title="Workflow Templates",
            active_nav="workflows_templates",
            is_templates_page=True,
            flash=request.query_params.get("flash"),
            pagination=pagination,
            query_extra=preserve_query(request, exclude={"page"}),
        ),
    )


@router.get("/workflows/new", response_class=HTMLResponse, name="workflows_new")
def workflows_new_form(
    request: Request,
    user: User = Depends(get_current_user_web),
):
    return templates.TemplateResponse(
        request,
        "workflows/form.html",
        {
            "user": user,
            "form": {"name": "", "description": ""},
            "errors": {},
            "active_nav": "workflows",
        },
    )


@router.get("/workflows/{workflow_id}", response_class=HTMLResponse, name="workflows_detail")
def workflows_detail(
    request: Request,
    workflow_id: int,
    runs_page: int = Query(1, ge=1, alias="runs_page"),
    links_page: int = Query(1, ge=1, alias="links_page"),
    user: User = Depends(get_current_user_web),
    service: WorkflowService = Depends(_workflow_service),
    db: Session = Depends(get_db),
):
    try:
        workflow = service.get_workflow(workflow_id)
    except WorkflowNotFound:
        return RedirectResponse(url="/workflows", status_code=status.HTTP_302_FOUND)

    if workflow.is_template:
        return RedirectResponse(
            url=f"/workflows/{workflow_id}/edit",
            status_code=status.HTTP_302_FOUND,
        )

    run_repo = RunRepository(db)
    runs_offset, runs_limit = offset_limit(runs_page, DEFAULT_PER_PAGE)
    runs_pagination = build_pagination(
        run_repo.list_runs_for_workflow_paginated(
            workflow_id,
            offset=runs_offset,
            limit=runs_limit,
        ),
        total=run_repo.count_runs_for_workflow(workflow_id),
        page=runs_page,
        per_page=DEFAULT_PER_PAGE,
    )
    agent_links_pagination = paginate_slice(
        list(workflow.agent_links),
        page=links_page,
        per_page=DEFAULT_PER_PAGE,
    )
    ctx = _detail_context(
        user=user,
        workflow=workflow,
        service=service,
        flash=request.query_params.get("flash"),
        recent_runs=runs_pagination.items,
        runs_pagination=runs_pagination,
        agent_links_pagination=agent_links_pagination,
        runs_query_extra=preserve_query(request, exclude={"runs_page"}),
        links_query_extra=preserve_query(request, exclude={"links_page"}),
    )
    return templates.TemplateResponse(request, "workflows/detail.html", ctx)


@router.get(
    "/workflows/{workflow_id}/edit",
    response_class=HTMLResponse,
    name="workflows_builder",
)
def workflows_builder(
    request: Request,
    workflow_id: int,
    user: User = Depends(get_current_user_web),
    service: WorkflowService = Depends(_workflow_service),
    agent_repo: AgentRepository = Depends(get_agent_repository),
):
    try:
        workflow = service.get_workflow(workflow_id)
    except WorkflowNotFound:
        if request.query_params.get("from") == "templates":
            return RedirectResponse(
                url="/workflows/templates?flash=not_found",
                status_code=status.HTTP_302_FOUND,
            )
        return RedirectResponse(url="/workflows", status_code=status.HTTP_302_FOUND)

    agents = agent_repo.list_all()
    agents_payload = [{"id": a.id, "name": a.name, "role": a.role} for a in agents]
    graph_json = workflow.graph_json or {"nodes": [], "edges": []}

    back_url = "/workflows/templates" if workflow.is_template else f"/workflows/{workflow.id}"
    active_nav = "workflows_templates" if workflow.is_template else "workflows"

    return templates.TemplateResponse(
        request,
        "workflows/builder.html",
        {
            "user": user,
            "workflow": workflow,
            "agents": agents_payload,
            "graph_json": graph_json,
            "back_url": back_url,
            "active_nav": active_nav,
            "flash": request.query_params.get("flash"),
        },
    )


@router.post("/workflows", response_class=HTMLResponse)
def workflows_create(
    request: Request,
    user: User = Depends(get_current_user_web),
    service: WorkflowService = Depends(_workflow_service),
    name: str = Form(...),
    description: str = Form(""),
):
    form = {"name": name, "description": description}
    try:
        payload = service.build_create_from_form(name=name, description=description)
        workflow = service.create_workflow(payload)
    except WorkflowValidationError as exc:
        return templates.TemplateResponse(
            request,
            "workflows/form.html",
            {
                "user": user,
                "form": form,
                "errors": exc.errors,
                "active_nav": "workflows",
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return RedirectResponse(
        url=f"/workflows/{workflow.id}?flash=created",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/workflows/{workflow_id}", response_class=HTMLResponse)
def workflows_update(
    request: Request,
    workflow_id: int,
    user: User = Depends(get_current_user_web),
    service: WorkflowService = Depends(_workflow_service),
    name: str = Form(...),
    description: str = Form(""),
):
    form = {"name": name, "description": description}
    try:
        workflow = service.update_workflow(
            workflow_id,
            WorkflowUpdate(name=name, description=description),
        )
    except WorkflowNotFound:
        return RedirectResponse(url="/workflows", status_code=status.HTTP_302_FOUND)
    except WorkflowValidationError as exc:
        try:
            workflow = service.get_workflow(workflow_id)
        except WorkflowNotFound:
            return RedirectResponse(url="/workflows", status_code=status.HTTP_302_FOUND)
        ctx = _detail_context(
            user=user,
            workflow=workflow,
            service=service,
            errors=exc.errors,
            form=form,
        )
        return templates.TemplateResponse(
            request,
            "workflows/detail.html",
            ctx,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return RedirectResponse(
        url=f"/workflows/{workflow.id}?flash=updated",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/workflows/templates/{template_id}/use")
def workflows_use_template(
    template_id: int,
    _user: User = Depends(get_current_user_web),
    service: WorkflowService = Depends(_workflow_service),
):
    try:
        workflow = service.duplicate_from_template(template_id)
    except WorkflowNotFound:
        return RedirectResponse(
            url="/workflows/templates?flash=not_found",
            status_code=status.HTTP_302_FOUND,
        )
    except WorkflowValidationError:
        return RedirectResponse(
            url="/workflows/templates?flash=error",
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(
        url=f"/workflows/{workflow.id}?flash=from_template",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/workflows/{workflow_id}/delete")
def workflows_delete(
    workflow_id: int,
    _user: User = Depends(get_current_user_web),
    service: WorkflowService = Depends(_workflow_service),
):
    try:
        service.delete_workflow(workflow_id)
    except WorkflowNotFound:
        pass
    return RedirectResponse(
        url="/workflows?flash=deleted",
        status_code=status.HTTP_302_FOUND,
    )
