# Environment Variables

Source: `backend/app/config.py` (`Settings`), `.env.example`, `docker-compose.yml`.

Pydantic Settings loads `.env` at the repository root (path: `PROJECT_ROOT / ".env"`).

## Variable reference

| Variable | Default (code) | Required | Sensitive | Purpose |
|----------|----------------|----------|-----------|---------|
| `APP_NAME` | `Orqestra` | No | No | OpenAPI title (field: `app_name`) |
| `APP_TAGLINE` | `AI Agent Orchestration Platform` | No | No | OpenAPI description suffix |
| `APP_ENV` | `development` | No | No | Environment label (`app_env`) |
| `DEBUG` | `true` | No | No | FastAPI `debug` flag |
| `API_VERSION` | `0.1.0` | No | No | OpenAPI version |
| `OPENAPI_ENABLED` | `true` | No | No | Toggle `/docs`, `/redoc`, `/openapi.json` |
| `DOCS_URL` | `/docs` | No | No | Swagger path when enabled |
| `REDOC_URL` | `/redoc` | No | No | ReDoc path |
| `OPENAPI_URL` | `/openapi.json` | No | No | OpenAPI JSON path |
| `DATABASE_URL` | `postgresql+psycopg2://yuno:yuno@localhost:5432/yuno` | **Yes** (prod) | **Yes** | SQLAlchemy connection string |
| `SESSION_SECRET_KEY` | `change-me-in-production` | **Yes** (prod) | **Yes** | Signs session cookies |
| `SESSION_MAX_AGE_SECONDS` | `604800` (7d) | No | No | Cookie max age |
| `ADMIN_EMAIL` | `admin@yuno.local` | No | No | Seed admin if DB empty |
| `ADMIN_PASSWORD` | `admin123` | No | **Yes** | Seed admin password |
| `ADMIN_FULL_NAME` | `Platform Admin` | No | No | Seed admin display name |
| `APP_BASE_URL` | `http://localhost:3000` | No | No | Password reset link base |
| `PASSWORD_RESET_TOKEN_HOURS` | `24` | No | No | Reset token TTL |
| `SMTP_HOST` | `""` | No | No | SMTP server (optional) |
| `SMTP_PORT` | `587` | No | No | SMTP port |
| `SMTP_USER` | `""` | No | **Yes** | SMTP auth user |
| `SMTP_PASSWORD` | `""` | No | **Yes** | SMTP auth password |
| `SMTP_FROM` | `""` | No | No | From address (required with host for mail) |
| `SMTP_USE_TLS` | `true` | No | No | TLS for SMTP |
| `REDIS_URL` | `redis://localhost:6379/0` | **Yes** if Celery async | No | Celery broker and result backend |
| `CELERY_TASK_ALWAYS_EAGER` | `false` | No | No | Run tasks in-process (dev without worker) |
| `OPENAI_API_KEY` | `""` | No* | **Yes** | OpenAI API key |
| `RUNTIME_MOCK_LLM` | `false` | No | No | `true` = FakeListChatModel (tests/CI); `false` = OpenAI when key present |
| `RUNTIME_MOCK_TOOLS` | `false` | No | No | `true` = stub `web_search`; `false` = live DuckDuckGo search |
| `TELEGRAM_BOT_TOKEN` | `""` | **Yes** (challenge) | **Yes** | Telegram BotFather token - required external channel |
| `TELEGRAM_WEBHOOK_SECRET` | `""` | No | **Yes** | Webhook header validation (production) |
| `TELEGRAM_USE_POLLING` | `false` | Recommended (local) | No | Long-polling in API process; set `true` for local demos |
| `UI_ASSETS_DIR` | `ui/assets` (repo root) | No | No | Static Craft assets mount |
| `UI_JS_DIR` | `ui/js` (repo root) | No | No | JS bundle mount |

\*Required for real OpenAI calls when `RUNTIME_MOCK_LLM=false`.

## Docker Compose overrides

`docker-compose.yml` sets for **api** and **worker**:

| Variable | Compose value |
|----------|---------------|
| `DATABASE_URL` | `postgresql+psycopg2://yuno:yuno@postgres:5432/yuno` |
| `REDIS_URL` | `redis://redis:6379/0` |
| `UI_ASSETS_DIR` | `/ui-assets` (api only) |
| `UI_JS_DIR` | `/ui-js` (api only) |

The bundled `postgres` service uses user/password/database `yuno` and persists data in the `postgres_data` volume. Values in `.env` for `DATABASE_URL` are overridden inside containers so a single `docker compose up --build` works without an external database.

## Production checklist

1. Set long random `SESSION_SECRET_KEY`
2. Set strong `ADMIN_PASSWORD` or create users and disable seed reliance
3. Set `DEBUG=false`, `APP_ENV=production`
4. Set `RUNTIME_MOCK_LLM=false` and provide `OPENAI_API_KEY` if using real models
5. Set `TELEGRAM_BOT_TOKEN` and link agents under **Channels** (required external channel)
6. Configure `TELEGRAM_WEBHOOK_SECRET` when using webhooks (or `TELEGRAM_USE_POLLING=true` locally)
7. Use TLS termination so session cookies can be marked secure (**Needs Verification** - app sets `https_only=False`; may require proxy cookie flags)
