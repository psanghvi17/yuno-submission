"""OpenAPI schema customization for Swagger UI and ReDoc."""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

API_PATH_PREFIX = "/api/v1"
HEALTH_PATH = "/health"
SESSION_COOKIE_NAME = "session"
SECURITY_SCHEME_NAME = "SessionCookie"

PUBLIC_API_PATH_SUFFIXES = ("/auth/login", "/auth/logout")

OPENAPI_TAGS = [
    {
        "name": "Auth",
        "description": "Session-based authentication. Login sets a signed `session` cookie.",
    },
    {
        "name": "Users",
        "description": "User account CRUD (requires authentication).",
    },
    {
        "name": "Agents",
        "description": "AI agent definitions (requires authentication).",
    },
    {
        "name": "Workflows",
        "description": "Workflow graphs and templates (requires authentication).",
    },
    {
        "name": "Runs",
        "description": "Workflow execution runs, messages, logs, and token usage (requires authentication).",
    },
    {
        "name": "System",
        "description": "Health and readiness probes.",
    },
]


def _filter_paths(paths: dict) -> dict:
    """Expose only REST API routes in Swagger (exclude HTML web UI routes)."""
    return {
        path: definition
        for path, definition in paths.items()
        if path.startswith(API_PATH_PREFIX) or path == HEALTH_PATH
    }


def _apply_security_scheme(openapi_schema: dict) -> None:
    openapi_schema.setdefault("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        SECURITY_SCHEME_NAME: {
            "type": "apiKey",
            "in": "cookie",
            "name": SESSION_COOKIE_NAME,
            "description": (
                "Signed session cookie returned by `POST /api/v1/auth/login`. "
                "In Swagger UI, call login first; the browser stores the cookie "
                "for subsequent requests."
            ),
        }
    }


def _ensure_protected_operations_have_security(openapi_schema: dict) -> None:
    """Mark protected API operations when FastAPI did not infer security."""
    for path, methods in openapi_schema.get("paths", {}).items():
        if not path.startswith(API_PATH_PREFIX):
            continue
        is_public = any(path.endswith(suffix) for suffix in PUBLIC_API_PATH_SUFFIXES)
        for method_name, operation in methods.items():
            if method_name not in ("get", "post", "put", "delete", "patch", "options", "head"):
                continue
            if is_public:
                operation["security"] = []
            elif "security" not in operation:
                operation["security"] = [{SECURITY_SCHEME_NAME: []}]


def build_openapi_schema(app: FastAPI) -> dict:
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    openapi_schema["paths"] = _filter_paths(openapi_schema.get("paths", {}))
    _apply_security_scheme(openapi_schema)
    _ensure_protected_operations_have_security(openapi_schema)
    app.openapi_schema = openapi_schema
    return app.openapi_schema


def setup_openapi(app: FastAPI) -> None:
    app.openapi = lambda: build_openapi_schema(app)
