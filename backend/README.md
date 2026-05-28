# Backend - Yuno Agent Platform

FastAPI application with LangGraph runtime, Celery workers, PostgreSQL, and Telegram channel adapter.

## Run locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt

# Configure .env at repo root (copy from .env.example)
alembic upgrade head
uvicorn app.main:app --reload --port 3000
```

**With async runs:** start Redis and `celery -A app.workers.celery_app worker --loglevel=info`, or set `CELERY_TASK_ALWAYS_EAGER=true` in `.env`.

**Default login:** `admin@yuno.local` / `admin123`

## Tests

```bash
python -m pytest -q
```

Integration coverage: `test_workflow_run.py` (end-to-end runs), `test_message_delivery.py` (Telegram mocked), `test_dashboard.py` (UI flows).

## API documentation

| URL | Description |
|-----|-------------|
| http://localhost:3000/docs | Swagger UI |
| http://localhost:3000/redoc | ReDoc |

Use **Auth -> POST /api/v1/auth/login** in Swagger; the session cookie applies to other endpoints.

## Key endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| GET | `/dashboard` | Stats, active runs, messages |
| GET/POST | `/agents`, `/agents/{id}` | Agent CRUD |
| GET/POST | `/workflows`, `/workflows/templates` | Workflows + templates |
| GET | `/workflows/{id}/edit` | Drawflow builder |
| POST | `/workflows/{id}/run` | Enqueue workflow run |
| GET | `/runs`, `/runs/{id}` | Run history + live monitor |
| GET | `/runs/{id}/fragment/*` | HTMX partials (logs, messages, usage) |
| GET/POST | `/channels` | Telegram channel links |
| POST | `/webhooks/telegram` | Telegram webhook |
| POST | `/api/v1/runs?workflow_id=` | JSON: enqueue run (202) |
| PUT | `/api/v1/workflows/{id}/graph` | Save graph JSON |

## CLI - run workflow without UI

```bash
cd backend
python scripts/run_workflow.py --demo
python scripts/run_workflow.py --workflow-id 1
```

## Module map

| Path | Role |
|------|------|
| `app/runtime/` | LangGraph graph builder, nodes, tools |
| `app/workers/` | Celery tasks (`execute_workflow_run`, `process_telegram_update`) |
| `app/channels/` | Telegram adapter |
| `app/services/` | Business logic (agents, workflows, runs, channels) |
| `alembic/versions/` | DB migrations (`001`-`006`) |

See `../docs/ARCHITECTURE.md` and `../README.md` for full platform docs.
