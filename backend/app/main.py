from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.agents import router as agents_api_router
from app.api.v1.auth import router as auth_api_router
from app.api.v1.users import router as users_api_router
from app.api.v1.workflows import router as workflows_api_router
from app.api.v1.runs import router as runs_api_router
from app.api.web.agents import router as agents_web_router
from app.api.web.workflows import router as workflows_web_router
from app.api.web.runs import router as runs_web_router
from app.api.web.channels import router as channels_web_router
from app.api.webhooks.telegram import router as telegram_webhook_router
from app.api.web.auth import router as auth_web_router
from app.api.web.users import router as users_web_router
from app.api.web.dashboard import router as dashboard_router
from app.config import UI_ASSETS_DIR, UI_JS_DIR, get_settings
from app.openapi import OPENAPI_TAGS, setup_openapi
from app.core.deps import LoginRequired
from app.startup import (
    migrate_legacy_admin_email,
    seed_admin_user,
    seed_default_agents,
    seed_demo_workflow,
    seed_dev_pipeline,
    seed_e2e_pipeline,
    seed_workflow_templates,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    migrate_legacy_admin_email()
    seed_admin_user()
    seed_default_agents()
    seed_workflow_templates()
    seed_demo_workflow()
    seed_e2e_pipeline()
    seed_dev_pipeline()
    from app.channels.telegram_polling import start_telegram_polling, stop_telegram_polling

    start_telegram_polling()
    yield
    stop_telegram_polling()


_openapi_description = (
    f"{settings.app_tagline}\n\n"
    "## Authentication\n\n"
    "Protected endpoints require a session cookie. Use **Auth → POST /api/v1/auth/login** "
    "in Swagger UI (or the web login form); the browser stores the `session` cookie "
    "for follow-up requests.\n\n"
    "## API surface\n\n"
    "This documentation lists **REST JSON** endpoints under `/api/v1` plus `/health`. "
    "HTML pages (`/dashboard`, `/agents`, etc.) are not included."
)

app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    description=_openapi_description,
    debug=settings.debug,
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    docs_url=settings.docs_url if settings.openapi_enabled else None,
    redoc_url=settings.redoc_url if settings.openapi_enabled else None,
    openapi_url=settings.openapi_url if settings.openapi_enabled else None,
)

setup_openapi(app)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    max_age=settings.session_max_age_seconds,
    https_only=False,
)

# Mount workflow editor assets before /static. Only use /static/workflow for ui/js —
# do not mount ui/js at /static/js or Craft bundles (scripts.bundle.js) 404.
if UI_JS_DIR.is_dir():
    app.mount(
        "/static/workflow",
        StaticFiles(directory=str(UI_JS_DIR)),
        name="static-workflow",
    )

if UI_ASSETS_DIR.is_dir():
    app.mount(
        "/static",
        StaticFiles(directory=str(UI_ASSETS_DIR)),
        name="static",
    )

@app.exception_handler(LoginRequired)
async def login_required_handler(_request: Request, exc: LoginRequired):
    return RedirectResponse(url=exc.redirect_url, status_code=status.HTTP_302_FOUND)


app.include_router(auth_web_router)
app.include_router(dashboard_router)
app.include_router(agents_web_router)
app.include_router(workflows_web_router)
app.include_router(runs_web_router)
app.include_router(channels_web_router)
app.include_router(users_web_router)
app.include_router(telegram_webhook_router)
app.include_router(auth_api_router, prefix="/api/v1")
app.include_router(users_api_router, prefix="/api/v1")
app.include_router(agents_api_router, prefix="/api/v1")
app.include_router(workflows_api_router, prefix="/api/v1")
app.include_router(runs_api_router, prefix="/api/v1")


@app.get("/health", tags=["System"])
def health():
    """Liveness probe for load balancers and Docker health checks."""
    return {"status": "ok", "app": settings.app_name}


@app.get("/")
def root(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
