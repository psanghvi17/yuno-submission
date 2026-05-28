import json
from copy import deepcopy

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.deps import get_agent_repository, get_current_user_web
from app.web.pagination import (
    DEFAULT_PER_PAGE,
    build_pagination,
    offset_limit,
    preserve_query,
)
from app.models.agent import DEFAULT_AGENT_CONFIG, Agent
from app.models.user import User
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import AgentUpdate
from app.services.agent_service import AgentNotFound, AgentService, AgentValidationError
from app.templating import templates

router = APIRouter(tags=["agents-web"])


def _agent_service(
    agent_repo: AgentRepository = Depends(get_agent_repository),
) -> AgentService:
    return AgentService(agent_repo)


def _form_context(
    *,
    user: User,
    agent: Agent | None = None,
    form: dict | None = None,
    errors: dict[str, str] | None = None,
    is_edit: bool = False,
) -> dict:
    default_form = {
        "name": "",
        "role": "",
        "system_prompt": "",
        "model": "gpt-4o-mini",
        "tools_raw": "",
        "is_active": True,
        **AgentService.form_fields_from_config(deepcopy(DEFAULT_AGENT_CONFIG)),
    }
    if agent:
        default_form = {
            "name": agent.name,
            "role": agent.role,
            "system_prompt": agent.system_prompt,
            "model": agent.model,
            "tools_raw": "\n".join(agent.tools or []),
            "is_active": agent.is_active,
            **AgentService.form_fields_from_config(agent.config),
        }
    if form:
        default_form.update(form)
    return {
        "user": user,
        "agent": agent,
        "form": default_form,
        "errors": errors or {},
        "is_edit": is_edit,
        "active_nav": "agents",
    }


@router.get("/agents", response_class=HTMLResponse, name="agents_list")
def agents_list(
    request: Request,
    page: int = Query(1, ge=1),
    user: User = Depends(get_current_user_web),
    agent_repo: AgentRepository = Depends(get_agent_repository),
):
    offset, limit = offset_limit(page, DEFAULT_PER_PAGE)
    pagination = build_pagination(
        agent_repo.list_paginated(offset=offset, limit=limit),
        total=agent_repo.count(),
        page=page,
        per_page=DEFAULT_PER_PAGE,
    )
    return templates.TemplateResponse(
        request,
        "agents/list.html",
        {
            "user": user,
            "agents": pagination.items,
            "pagination": pagination,
            "query_extra": preserve_query(request, exclude={"page"}),
            "flash": request.query_params.get("flash"),
            "active_nav": "agents",
        },
    )


@router.get("/agents/new", response_class=HTMLResponse, name="agents_new")
def agents_new_form(
    request: Request,
    user: User = Depends(get_current_user_web),
):
    return templates.TemplateResponse(
        request,
        "agents/form.html",
        _form_context(user=user, is_edit=False),
    )


@router.get("/agents/{agent_id}", response_class=HTMLResponse, name="agents_edit")
def agents_edit_form(
    request: Request,
    agent_id: int,
    user: User = Depends(get_current_user_web),
    service: AgentService = Depends(_agent_service),
):
    try:
        agent = service.get_agent(agent_id)
    except AgentNotFound:
        return RedirectResponse(url="/agents", status_code=status.HTTP_302_FOUND)

    ctx = _form_context(user=user, agent=agent, is_edit=True)
    ctx["flash"] = request.query_params.get("flash")
    return templates.TemplateResponse(request, "agents/form.html", ctx)


@router.post("/agents", response_class=HTMLResponse)
def agents_create(
    request: Request,
    user: User = Depends(get_current_user_web),
    service: AgentService = Depends(_agent_service),
    name: str = Form(...),
    role: str = Form(""),
    system_prompt: str = Form(""),
    model: str = Form("gpt-4o-mini"),
    tools_raw: str = Form(""),
    config_raw: str = Form(""),
    memory_context: str = Form(""),
    memory_max_turns: str = Form("10"),
    schedule_enabled: bool = Form(False),
    schedule_cron: str = Form(""),
    schedule_notes: str = Form(""),
    guardrails_max_tokens: str = Form(""),
    guardrails_topics: str = Form(""),
    is_active: bool = Form(False),
):
    form = {
        "name": name,
        "role": role,
        "system_prompt": system_prompt,
        "model": model,
        "tools_raw": tools_raw,
        "config_raw": config_raw,
        "memory_context": memory_context,
        "memory_max_turns": memory_max_turns,
        "schedule_enabled": schedule_enabled,
        "schedule_cron": schedule_cron,
        "schedule_notes": schedule_notes,
        "guardrails_max_tokens": guardrails_max_tokens,
        "guardrails_topics": guardrails_topics,
        "is_active": is_active,
    }
    try:
        payload = AgentService.build_create_from_form(
            name=name,
            role=role,
            system_prompt=system_prompt,
            model=model,
            tools_raw=tools_raw,
            config_raw=config_raw,
            memory_context=memory_context,
            memory_max_turns=memory_max_turns,
            schedule_enabled=schedule_enabled,
            schedule_cron=schedule_cron,
            schedule_notes=schedule_notes,
            guardrails_max_tokens=guardrails_max_tokens,
            guardrails_topics=guardrails_topics,
            is_active=is_active,
        )
        agent = service.create_agent(payload)
    except AgentValidationError as exc:
        return templates.TemplateResponse(
            request,
            "agents/form.html",
            _form_context(user=user, form=form, errors=exc.errors, is_edit=False),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return RedirectResponse(
        url=f"/agents/{agent.id}?flash=created",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/agents/{agent_id}", response_class=HTMLResponse)
def agents_update(
    request: Request,
    agent_id: int,
    user: User = Depends(get_current_user_web),
    service: AgentService = Depends(_agent_service),
    name: str = Form(...),
    role: str = Form(""),
    system_prompt: str = Form(""),
    model: str = Form("gpt-4o-mini"),
    tools_raw: str = Form(""),
    config_raw: str = Form(""),
    memory_context: str = Form(""),
    memory_max_turns: str = Form("10"),
    schedule_enabled: bool = Form(False),
    schedule_cron: str = Form(""),
    schedule_notes: str = Form(""),
    guardrails_max_tokens: str = Form(""),
    guardrails_topics: str = Form(""),
    is_active: bool = Form(False),
):
    form = {
        "name": name,
        "role": role,
        "system_prompt": system_prompt,
        "model": model,
        "tools_raw": tools_raw,
        "config_raw": config_raw,
        "memory_context": memory_context,
        "memory_max_turns": memory_max_turns,
        "schedule_enabled": schedule_enabled,
        "schedule_cron": schedule_cron,
        "schedule_notes": schedule_notes,
        "guardrails_max_tokens": guardrails_max_tokens,
        "guardrails_topics": guardrails_topics,
        "is_active": is_active,
    }
    try:
        payload = AgentService.build_create_from_form(
            name=name,
            role=role,
            system_prompt=system_prompt,
            model=model,
            tools_raw=tools_raw,
            config_raw=config_raw,
            memory_context=memory_context,
            memory_max_turns=memory_max_turns,
            schedule_enabled=schedule_enabled,
            schedule_cron=schedule_cron,
            schedule_notes=schedule_notes,
            guardrails_max_tokens=guardrails_max_tokens,
            guardrails_topics=guardrails_topics,
            is_active=is_active,
        )
        updates = AgentUpdate(**payload.model_dump())
        agent = service.update_agent(agent_id, updates)
    except AgentNotFound:
        return RedirectResponse(url="/agents", status_code=status.HTTP_302_FOUND)
    except AgentValidationError as exc:
        try:
            agent = service.get_agent(agent_id)
        except AgentNotFound:
            return RedirectResponse(url="/agents", status_code=status.HTTP_302_FOUND)
        return templates.TemplateResponse(
            request,
            "agents/form.html",
            _form_context(
                user=user,
                agent=agent,
                form=form,
                errors=exc.errors,
                is_edit=True,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return RedirectResponse(
        url=f"/agents/{agent.id}?flash=updated",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/agents/{agent_id}/delete")
def agents_delete(
    agent_id: int,
    _user: User = Depends(get_current_user_web),
    service: AgentService = Depends(_agent_service),
):
    try:
        service.delete_agent(agent_id)
    except AgentNotFound:
        pass
    return RedirectResponse(
        url="/agents?flash=deleted",
        status_code=status.HTTP_302_FOUND,
    )
