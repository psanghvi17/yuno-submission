from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_web
from app.models.user import User
from app.repositories.agent_repository import AgentRepository
from app.repositories.channel_repository import ChannelRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.channel_service import (
    ChannelNotFound,
    ChannelService,
    ChannelValidationError,
    build_channel_service,
)
from app.templating import templates
from app.web.pagination import (
    DEFAULT_PER_PAGE,
    build_pagination,
    offset_limit,
    preserve_query,
)

router = APIRouter(tags=["channels-web"])


def _channel_service(db: Session = Depends(get_db)) -> ChannelService:
    return build_channel_service(db)


@router.get("/channels", response_class=HTMLResponse, name="channels_list")
def channels_list(
    request: Request,
    page: int = Query(1, ge=1),
    user: User = Depends(get_current_user_web),
    service: ChannelService = Depends(_channel_service),
    db: Session = Depends(get_db),
):
    from urllib.parse import urlparse

    from app.config import get_settings

    settings = get_settings()
    parsed_db = urlparse(settings.database_url)
    db_label = parsed_db.hostname or "unknown"
    if parsed_db.port:
        db_label = f"{db_label}:{parsed_db.port}"
    if parsed_db.path and parsed_db.path != "/":
        db_label = f"{db_label}{parsed_db.path}"

    channel_repo = ChannelRepository(db)
    offset, limit = offset_limit(page, DEFAULT_PER_PAGE)
    link_rows = channel_repo.list_paginated(offset=offset, limit=limit)
    pagination = build_pagination(
        [service.link_detail(link) for link in link_rows],
        total=channel_repo.count(),
        page=page,
        per_page=DEFAULT_PER_PAGE,
    )

    return templates.TemplateResponse(
        request,
        "channels/list.html",
        {
            "user": user,
            "links": pagination.items,
            "pagination": pagination,
            "query_extra": preserve_query(request, exclude={"page"}),
            "telegram_configured": bool(settings.telegram_bot_token.strip()),
            "telegram_polling": settings.telegram_use_polling,
            "database_label": db_label,
            "flash": request.query_params.get("flash"),
            "active_nav": "channels",
        },
    )


@router.get("/channels/new", response_class=HTMLResponse, name="channels_new")
def channels_new(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: Session = Depends(get_db),
):
    agents = AgentRepository(db).list_all()
    return templates.TemplateResponse(
        request,
        "channels/form.html",
        {
            "user": user,
            "agents": agents,
            "form": {"agent_id": "", "chat_id": "", "is_active": True},
            "errors": {},
            "active_nav": "channels",
        },
    )


@router.post("/channels")
def channels_create(
    request: Request,
    user: User = Depends(get_current_user_web),
    service: ChannelService = Depends(_channel_service),
    db: Session = Depends(get_db),
    agent_id: int = Form(...),
    chat_id: str = Form(...),
    is_active: str | None = Form(None),
):
    agents = AgentRepository(db).list_all()
    try:
        link = service.link_agent(
            agent_id=agent_id,
            channel_type="telegram",
            chat_id=chat_id,
            is_active=is_active == "on",
        )
    except ChannelValidationError as exc:
        return templates.TemplateResponse(
            request,
            "channels/form.html",
            {
                "user": user,
                "agents": agents,
                "form": {
                    "agent_id": str(agent_id),
                    "chat_id": chat_id,
                    "is_active": is_active == "on",
                },
                "errors": exc.errors,
                "active_nav": "channels",
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return RedirectResponse(
        url=f"/channels?flash=linked&run_id={link.config.get('conversation_run_id', '')}",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/channels/{link_id}/delete")
def channels_delete(
    link_id: int,
    _user: User = Depends(get_current_user_web),
    service: ChannelService = Depends(_channel_service),
):
    try:
        service.delete_link(link_id)
    except ChannelNotFound:
        return RedirectResponse(
            url="/channels?flash=not_found",
            status_code=status.HTTP_302_FOUND,
        )
    return RedirectResponse(
        url="/channels?flash=deleted",
        status_code=status.HTTP_302_FOUND,
    )
