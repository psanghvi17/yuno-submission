from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import get_current_user_web, get_user_repository
from app.web.pagination import (
    DEFAULT_PER_PAGE,
    build_pagination,
    offset_limit,
    preserve_query,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserUpdate
from app.services.user_service import UserNotFound, UserService, UserValidationError
from app.templating import templates

router = APIRouter(tags=["users-web"])


def _user_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> UserService:
    return UserService(user_repo)


def _form_context(
    *,
    user: User,
    edit_user: User | None = None,
    form: dict | None = None,
    errors: dict[str, str] | None = None,
    is_edit: bool = False,
) -> dict:
    default_form = {
        "email": "",
        "full_name": "",
        "password": "",
        "password_confirm": "",
        "is_active": True,
    }
    if edit_user:
        default_form = {
            "email": edit_user.email,
            "full_name": edit_user.full_name,
            "password": "",
            "password_confirm": "",
            "is_active": edit_user.is_active,
        }
    if form:
        default_form.update(form)
    return {
        "user": user,
        "edit_user": edit_user,
        "form": default_form,
        "errors": errors or {},
        "is_edit": is_edit,
        "active_nav": "users",
    }


@router.get("/users", response_class=HTMLResponse, name="users_list")
def users_list(
    request: Request,
    page: int = Query(1, ge=1),
    user: User = Depends(get_current_user_web),
    user_repo: UserRepository = Depends(get_user_repository),
):
    offset, limit = offset_limit(page, DEFAULT_PER_PAGE)
    pagination = build_pagination(
        user_repo.list_paginated(offset=offset, limit=limit),
        total=user_repo.count(),
        page=page,
        per_page=DEFAULT_PER_PAGE,
    )
    return templates.TemplateResponse(
        request,
        "users/list.html",
        {
            "user": user,
            "users": pagination.items,
            "pagination": pagination,
            "query_extra": preserve_query(request, exclude={"page"}),
            "flash": request.query_params.get("flash"),
            "active_nav": "users",
        },
    )


@router.get("/users/new", response_class=HTMLResponse, name="users_new")
def users_new_form(
    request: Request,
    user: User = Depends(get_current_user_web),
):
    return templates.TemplateResponse(
        request,
        "users/form.html",
        _form_context(user=user, is_edit=False),
    )


@router.get("/users/{user_id}", response_class=HTMLResponse, name="users_edit")
def users_edit_form(
    request: Request,
    user_id: int,
    user: User = Depends(get_current_user_web),
    service: UserService = Depends(_user_service),
):
    try:
        edit_user = service.get_user(user_id)
    except UserNotFound:
        return RedirectResponse(url="/users", status_code=status.HTTP_302_FOUND)

    ctx = _form_context(user=user, edit_user=edit_user, is_edit=True)
    ctx["flash"] = request.query_params.get("flash")
    return templates.TemplateResponse(request, "users/form.html", ctx)


@router.post("/users", response_class=HTMLResponse)
def users_create(
    request: Request,
    user: User = Depends(get_current_user_web),
    service: UserService = Depends(_user_service),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    full_name: str = Form(""),
    is_active: bool = Form(False),
):
    form = {
        "email": email,
        "password": password,
        "password_confirm": password_confirm,
        "full_name": full_name,
        "is_active": is_active,
    }
    try:
        payload = UserService.build_create_from_form(
            email=email,
            password=password,
            password_confirm=password_confirm,
            full_name=full_name,
            is_active=is_active,
        )
        created = service.create_user(payload)
    except UserValidationError as exc:
        return templates.TemplateResponse(
            request,
            "users/form.html",
            _form_context(user=user, form=form, errors=exc.errors, is_edit=False),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return RedirectResponse(
        url=f"/users/{created.id}?flash=created",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/users/{user_id}", response_class=HTMLResponse)
def users_update(
    request: Request,
    user_id: int,
    user: User = Depends(get_current_user_web),
    service: UserService = Depends(_user_service),
    email: str = Form(...),
    password: str = Form(""),
    password_confirm: str = Form(""),
    full_name: str = Form(""),
    is_active: bool = Form(False),
):
    if user_id == user.id:
        is_active = True

    form = {
        "email": email,
        "password": password,
        "password_confirm": password_confirm,
        "full_name": full_name,
        "is_active": is_active,
    }
    try:
        payload = UserService.build_update_from_form(
            email=email,
            password=password,
            password_confirm=password_confirm,
            full_name=full_name,
            is_active=is_active,
        )
        updated = service.update_user(
            user_id,
            payload,
            acting_user_id=user.id,
        )
    except UserNotFound:
        return RedirectResponse(url="/users", status_code=status.HTTP_302_FOUND)
    except UserValidationError as exc:
        try:
            edit_user = service.get_user(user_id)
        except UserNotFound:
            return RedirectResponse(url="/users", status_code=status.HTTP_302_FOUND)
        return templates.TemplateResponse(
            request,
            "users/form.html",
            _form_context(
                user=user,
                edit_user=edit_user,
                form=form,
                errors=exc.errors,
                is_edit=True,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return RedirectResponse(
        url=f"/users/{updated.id}?flash=updated",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/users/{user_id}/delete")
def users_delete(
    user_id: int,
    user: User = Depends(get_current_user_web),
    service: UserService = Depends(_user_service),
):
    try:
        service.delete_user(user_id, acting_user_id=user.id)
    except (UserNotFound, UserValidationError):
        pass
    return RedirectResponse(
        url="/users?flash=deleted",
        status_code=status.HTTP_302_FOUND,
    )
