# Orqestra - Yuno Agent Orchestration Platform

Multi-agent workflow orchestration with a visual builder (Drawflow), **LangGraph** runtime, live run monitoring (HTMX), and **Telegram** as the human channel.

FastAPI app name: **Orqestra** (`APP_NAME`).

## Features

- **Agents** - System prompts, models, tools (`web_search`, `write_file`, `send_notification`) with a tool-calling loop (results fed back to the model), memory/schedule/guardrails JSON config
- **Workflows** - Visual graph editor; node types: `agent`, `condition`, `channel`, `end`
- **Templates** - Seed templates (e.g. research notify, support triage); duplicate into editable workflows
- **Runs** - Async execution via Celery; messages, logs, token usage and cost per run
- **Channels** - Telegram inbound/outbound (webhook or long-polling)
- **Users** - Session auth, admin seeding, optional SMTP password reset
- **Dashboard** - Active/recent/failed runs and message feed

## Tech stack

| Layer | Technology |
|-------|------------|
| API / UI server | FastAPI, Jinja2, Starlette SessionMiddleware |
| ORM / DB | SQLAlchemy 2, PostgreSQL (`app` schema), Alembic |
| Task queue | Celery, Redis |
| AI runtime | LangGraph, LangChain, OpenAI (optional mocks) |
| External | **Telegram** (required human channel), SMTP (optional) |
| Frontend assets | Craft theme (`ui/assets`), custom JS (`ui/js`) |

## Architecture

**Modular monolith** - one codebase, two runtime processes (API + Celery worker), PostgreSQL + Redis.

```mermaid
flowchart LR
    UI[Web UI\nCraft + HTMX] --> API[FastAPI]
    API --> DB[(PostgreSQL)]
    API --> Redis[(Redis)]
    Redis --> Worker[Celery worker]
    Worker --> LG[LangGraph]
    LG --> LC[LangChain]
    TG[Telegram] --> API
    Worker --> DB
    LG --> DB
```

**Full documentation:** [docs/README.md](docs/README.md)

| Topic | Document |
|-------|----------|
| Architecture & flows | [docs/architecture/README.md](docs/architecture/README.md) |
| REST & web API | [docs/api/README.md](docs/api/README.md) |
| Database | [docs/database/README.md](docs/database/README.md) |
| Environment variables | [docs/development/environment.md](docs/development/environment.md) |
| Developer guide | [docs/development/README.md](docs/development/README.md) |
| Deployment | [docs/deployment/README.md](docs/deployment/README.md) |

## Quick start (single command)

From the repository root, run the setup script (creates `.env` if missing, generates `SESSION_SECRET_KEY`, starts Compose):

```bash
./scripts/setup.sh          # macOS/Linux
# .\scripts\setup.ps1       # Windows PowerShell
```

Or manually:

```bash
cp .env.example .env
# Compose sets DATABASE_URL and REDIS_URL in containers
# For Telegram demo: TELEGRAM_BOT_TOKEN + TELEGRAM_USE_POLLING=true
docker compose up --build
```

No `OPENAI_API_KEY`? The app automatically uses mock LLM responses until you add a key.

| Service | Role |
|---------|------|
| `postgres` | PostgreSQL 16 (host **5433** -> 5432 in network; data in `postgres_data` volume) |
| `api` | FastAPI on port **3000** (-> 8000 in container); runs migrations on start |
| `redis` | Celery broker |
| `worker` | LangGraph execution |

| URL | Purpose |
|-----|---------|
| http://localhost:3000/auth/login | Web UI |
| http://localhost:3000/docs | Swagger (REST `/api/v1` only) |
| http://localhost:3000/health | Health check |

**Default login** (seeded when users table is empty): `admin@yuno.local` / `admin123` - change in production.

```bash
curl http://localhost:3000/health
# PowerShell: .\scripts\verify_setup.ps1
# Bash: ./scripts/verify_setup.sh
```

## Environment variables

Minimum to run:

| Variable | Purpose |
|----------|---------|
| `SESSION_SECRET_KEY` | Session cookie signing |
| `DATABASE_URL` | Only if not using Compose defaults; Compose sets `postgresql+psycopg2://yuno:yuno@postgres:5432/yuno` |
| `REDIS_URL` | Celery (Compose sets `redis://redis:6379/0` in containers) |

External channel (required for challenge demo):

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | BotFather token - enables Telegram inbound/outbound |
| `TELEGRAM_USE_POLLING` | `true` - local dev without ngrok (recommended for demos) |

Common optional:

| Variable | Purpose |
|----------|---------|
| `RUNTIME_MOCK_LLM` | `true` - force offline LLM (default: real OpenAI when key set; auto-mock if key empty) |
| `RUNTIME_MOCK_TOOLS` | `true` - stub `web_search`; default uses live DuckDuckGo |
| `CELERY_TASK_ALWAYS_EAGER` | `true` - run tasks in API process (no worker) |
| `TELEGRAM_WEBHOOK_SECRET` | Production webhook validation |

**Complete table:** [docs/development/environment.md](docs/development/environment.md)

## Local development (no Docker)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 3000
```

Separate terminal:

```bash
celery -A app.workers.celery_app worker --loglevel=info
```

Or set `CELERY_TASK_ALWAYS_EAGER=true` in `.env`.

## API documentation

- **Swagger:** http://localhost:3000/docs - session cookie auth; login via **Auth -> POST /api/v1/auth/login**
- **ReDoc:** http://localhost:3000/redoc
- **Written reference:** [docs/api/README.md](docs/api/README.md) (includes web routes and webhooks)

## Tests

```bash
cd backend
pip install -r requirements.txt
python -m pytest -q
```

| File | Covers |
|------|--------|
| `test_agents.py` | Agent CRUD |
| `test_workflows.py` | Graph save, templates |
| `test_runtime.py` | LangGraph execution |
| `test_runs.py` | Celery enqueue, HTMX monitor |
| `test_workflow_run.py` | End-to-end workflow runs |
| `test_telegram.py` | Telegram adapter + webhook |
| `test_message_delivery.py` | Inbound/outbound messaging |
| `test_dashboard.py` | Dashboard, conditions, config UI |

## Common commands

| Command | Description |
|---------|-------------|
| `alembic upgrade head` | Apply DB migrations |
| `alembic revision -m "msg"` | Create new migration |
| `uvicorn app.main:app --reload --port 3000` | Dev API server |
| `celery -A app.workers.celery_app worker --loglevel=info` | Background worker |
| `docker compose up --build` | Stack with Redis + worker |

## Deployment

- **CapRover:** build from root `Dockerfile` via `captain-definition`
- **Compose:** `docker-compose.yml` for dev/staging

Details: [docs/deployment/README.md](docs/deployment/README.md)

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `connection refused` to DB | `docker compose ps` - is `postgres` healthy? For external DB, set `DATABASE_URL` host reachable from container |
| Runs stay `pending` | Worker running? Redis up? Or use `CELERY_TASK_ALWAYS_EAGER=true` |
| 401 on API | Call `/api/v1/auth/login` first; send `session` cookie |
| Telegram no replies | `TELEGRAM_BOT_TOKEN`, channel link chat ID, polling vs webhook |
| OpenAI errors | Set `RUNTIME_MOCK_LLM=true` or provide `OPENAI_API_KEY` |
| Migration errors | Postgres user can `CREATE SCHEMA app`; run `alembic upgrade head` |

## Project layout

```text
├── backend/              # FastAPI, LangGraph, Celery, Alembic
│   └── app/
│       ├── api/v1/       # REST JSON
│       ├── api/web/      # HTML + HTMX
│       ├── api/webhooks/
│       ├── services/
│       ├── repositories/
│       ├── models/
│       ├── runtime/
│       └── workers/
├── ui/                   # Static assets + workflow-builder JS
├── docs/                 # Architecture, API, deployment guides
├── scripts/              # setup.sh, setup.ps1, verify_setup helpers
├── docker-compose.yml
├── Dockerfile            # Production (CapRover)
└── .env.example
```

## Demo video

**Full walkthrough (includes live Telegram conversation):** https://youtu.be/PotqKA5dRJE

The recording covers:
- Creating and configuring agents in the web UI
- Building a workflow in the visual graph editor
- Running the **6-agent Software development pipeline** end-to-end
- Live monitoring (logs, inter-agent messages, token/cost per run)
- Human triggering the pipeline via Telegram (`/launch`) and receiving the final announcement reply

**5-agent end-to-end workflow details:** [docs/E2E_DEMO.md](docs/E2E_DEMO.md).


## Why LangGraph + LangChain

- **LangGraph** executes stored workflow JSON: agent pipelines, **condition** nodes (e.g. support triage confidence loop), **channel** nodes (Telegram notify).
- **LangChain** provides chat models, tool binding, and token/cost callbacks persisted per run.

## Extending the platform

| Task | Where to start |
|------|----------------|
| New workflow template | `WorkflowService.seed_workflow_templates()` / template factories |
| New channel (e.g. Slack) | `app/channels/` adapter + `ChannelService` + webhook route |
| New REST endpoint | [docs/development/README.md](docs/development/README.md) |
