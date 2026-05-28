from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from app.config import get_settings
from app.core.email import is_valid_login_email, normalize_email
from app.templating import templates
from app.core.deps import SESSION_USER_ID_KEY, get_current_user_optional, get_user_repository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.email_service import EmailDeliveryError

router = APIRouter(tags=["auth-web"])
settings = get_settings()


def _auth_service(user_repo: UserRepository = Depends(get_user_repository)) -> AuthService:
    return AuthService(user_repo)


def _login_redirect(*, error: str | None = None) -> str:
    if error:
        return f"/auth/login?error={error}"
    return "/auth/login"


@router.get("/auth/login", response_class=HTMLResponse, name="login_page")
def login_page(
    request: Request,
    user=Depends(get_current_user_optional),
):
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "error": request.query_params.get("error"),
            "flash": request.query_params.get("flash"),
        },
    )


@router.post("/auth/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    auth: AuthService = Depends(_auth_service),
):
    if not is_valid_login_email(email):
        return RedirectResponse(
            url=_login_redirect(error="invalid_email"),
            status_code=status.HTTP_302_FOUND,
        )

    user = auth.authenticate(normalize_email(email), password)
    if not user:
        return RedirectResponse(
            url=_login_redirect(error="invalid_credentials"),
            status_code=status.HTTP_302_FOUND,
        )

    request.session[SESSION_USER_ID_KEY] = user.id
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)


@router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)


@router.get("/auth/logout")
def logout_get(request: Request):
    request.session.clear()
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)


@router.get("/auth/forgot-password", response_class=HTMLResponse, name="forgot_password")
def forgot_password_page(
    request: Request,
    user=Depends(get_current_user_optional),
):
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request,
        "auth/forgot_password.html",
        {
            "error": request.query_params.get("error"),
            "flash": request.query_params.get("flash"),
        },
    )


@router.post("/auth/forgot-password")
def forgot_password_submit(
    email: str = Form(...),
    auth: AuthService = Depends(_auth_service),
):
    if not is_valid_login_email(email):
        return RedirectResponse(
            url="/auth/forgot-password?error=invalid_email",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        auth.request_password_reset(normalize_email(email))
    except EmailDeliveryError:
        return RedirectResponse(
            url="/auth/forgot-password?error=email_failed",
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(
        url="/auth/forgot-password?flash=sent",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/auth/reset-password", response_class=HTMLResponse, name="reset_password")
def reset_password_page(
    request: Request,
    user=Depends(get_current_user_optional),
):
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

    token = request.query_params.get("token", "").strip()
    if not token:
        return RedirectResponse(
            url="/auth/forgot-password?error=missing_token",
            status_code=status.HTTP_302_FOUND,
        )

    return templates.TemplateResponse(
        request,
        "auth/reset_password.html",
        {
            "token": token,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/auth/reset-password")
def reset_password_submit(
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    auth: AuthService = Depends(_auth_service),
):
    if password != password_confirm:
        return RedirectResponse(
            url=f"/auth/reset-password?token={token}&error=mismatch",
            status_code=status.HTTP_302_FOUND,
        )
    if len(password) < 8:
        return RedirectResponse(
            url=f"/auth/reset-password?token={token}&error=weak_password",
            status_code=status.HTTP_302_FOUND,
        )

    if not auth.reset_password_with_token(token.strip(), password):
        return RedirectResponse(
            url="/auth/forgot-password?error=invalid_token",
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(
        url="/auth/login?flash=password_reset",
        status_code=status.HTTP_302_FOUND,
    )
