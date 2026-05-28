# Developer Onboarding

## Prerequisites

| Tool | Version (from project) |
|------|------------------------|
| Python | 3.12 (`Dockerfile`) |
| PostgreSQL | 14+ (bundled in Compose, or external) |
| Redis | 7 (for Celery unless eager mode) |
| Docker / Compose | Recommended for one-command setup |
| Telegram bot | Required for external-channel demo (`TELEGRAM_BOT_TOKEN`) |

## Local setup (no Docker)

```bash
cp .env.example .env
# Edit DATABASE_URL, SESSION_SECRET_KEY

cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 3000
```

**Celery worker** (second terminal):

```bash
cd backend
celery -A app.workers.celery_app worker --loglevel=info
```

**Without Redis:** set `CELERY_TASK_ALWAYS_EAGER=true` in `.env` to execute tasks inside the API process.

Default login after seed: `admin@yuno.local` / `admin123` (from `.env`).

## Local setup (Docker Compose)

Single command (creates `.env`, generates session secret, starts stack):

```bash
./scripts/setup.sh          # macOS/Linux
# .\scripts\setup.ps1       # Windows
```

Or manually: `cp .env.example .env` then `docker compose up --build`. No `OPENAI_API_KEY`? The app auto-falls back to mock LLM responses.

- API: http://localhost:3000 (host 3000 -> container 8000)
- Migrations run on api container start: `alembic upgrade head`
- Worker container runs Celery
- **Channels:** link an agent to your Telegram chat ID - see [DEMO.md](../DEMO.md)

## Debugging

| Approach | How |
|----------|-----|
| FastAPI reload | `uvicorn ... --reload` (Compose api service uses reload) |
| Breakpoints | Attach debugger to `app.main:app` or worker process |
| DB state | Connect to Postgres `app` schema; inspect `workflow_runs`, `run_logs` |
| Eager Celery | `CELERY_TASK_ALWAYS_EAGER=true` - stack traces in API terminal |
| Mock LLM | `RUNTIME_MOCK_LLM=true` - no OpenAI billing |
| Tests | `cd backend && python -m pytest -q` |

**Logging:** No centralized logging config in `main.py`. Module loggers:

- `app.services.channel_service`
- `app.channels.telegram_polling`
- `app.services.email_service`

Default Python logging levels apply unless you configure `logging` in the shell or add config (**Needs Verification** for production log aggregation).

## Adding a new REST endpoint

1. **Schema** - Add Pydantic models in `backend/app/schemas/`.
2. **Repository** (if new persistence) - `backend/app/repositories/`.
3. **Service** - Business rules + `*ValidationError` with `.errors: dict[str,str]`.
4. **Router** - `backend/app/api/v1/<resource>.py`:
   - `router = APIRouter(prefix="/...", tags=[...])`
   - `Depends(get_current_user)` for protected routes
   - Map service exceptions -> `HTTPException`
5. **Register** - `include_router` in `app/main.py` with `prefix="/api/v1"`.
6. **OpenAPI** - Add tag in `app/openapi.py` `OPENAPI_TAGS` if new domain.
7. **Migration** - If new tables: `alembic revision` + model in `app/models/`.

**Convention sample** (from `agents.py`):

```python
@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreate,
    _user: User = Depends(get_current_user),
    service: AgentService = Depends(_agent_service),
):
    try:
        return service.create_agent(payload)
    except AgentValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors)
```

## Adding a web (HTML) page

1. Template under `backend/app/templates/`.
2. Route in `backend/app/api/web/` using `templates.TemplateResponse`.
3. Use `get_current_user_web` for auth.
4. Mount static assets already configured in `main.py`.

## How auth works

See [Architecture - Authentication](../architecture/README.md).

- Session key: `user_id` in Starlette session.
- Passwords: bcrypt via `AuthService` + `UserRepository`.
- API: 401 JSON; Web: redirect via `LoginRequired` handler.

## How validation works

| Layer | Mechanism |
|-------|-----------|
| Request body | Pydantic v2 models (`Field`, `field_validator`) |
| Web forms | `UserService.build_*_from_form` / `AgentService.build_*_from_form` -> Pydantic |
| Service rules | Raise `*ValidationError(errors: dict[str,str])` |
| HTTP mapping | Routers catch and return 422 with `detail=exc.errors` |

Email fields use `EmailStr`; web login uses `TypeAdapter(EmailStr)` for form posts.

## How to add migrations

```bash
cd backend
alembic revision -m "describe_change"
# Edit backend/alembic/versions/<rev>_describe_change.py
# Use schema=APP_SCHEMA from app.core.schema in op.create_table(...)
alembic upgrade head
```

Import new models in `alembic/env.py` if Alembic autogenerate is used (project currently hand-writes revisions).

## Code conventions (inferred)

| Area | Convention |
|------|------------|
| Layering | api -> service -> repository -> model |
| Router DI | Private factory `_foo_service(repo=Depends(...))` |
| Exceptions | Domain `*NotFound`, `*ValidationError` per service |
| IDs in paths | `snake_case` path params (`user_id`, `workflow_id`) |
| Deletes | API: 204; Web: POST `.../delete` + redirect |
| JSON graphs | `graph_json` with `nodes` / `edges` arrays |
| Tests | `backend/tests/test_*.py`, pytest, fixtures in `conftest.py` |
| Settings | Single `Settings` class, `get_settings()` cached |

## Test commands

```bash
cd backend
pip install -r requirements.txt
python -m pytest -q
python -m pytest tests/test_agents.py -v
```

| Test file | Focus |
|-----------|-------|
| `test_agents.py` | Agent CRUD |
| `test_workflows.py` | Graph, templates |
| `test_runtime.py` | LangGraph |
| `test_runs.py` | Celery / monitor |
| `test_workflow_run.py` | E2E runs |
| `test_telegram.py` | Telegram adapter |
| `test_message_delivery.py` | Channel messaging |
| `test_dashboard.py` | Dashboard, conditions |

## Verify install

```powershell
.\scripts\verify_setup.ps1
```

```bash
./scripts/verify_setup.sh
```

Checks `GET /health` and optionally authenticated flows.
