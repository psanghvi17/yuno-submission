# Database Documentation

## ORM & schema

| Item | Value |
|------|-------|
| ORM | SQLAlchemy 2.x declarative (`Mapped`, `mapped_column`) |
| Base | `app.core.database.Base` |
| PostgreSQL schema | **`app`** (`APP_SCHEMA = "app"`) |
| Migrations | Alembic (`backend/alembic/versions/`) |
| Connection | `DATABASE_URL` -> `postgresql+psycopg2://...` |

Alembic `env.py` runs `CREATE SCHEMA IF NOT EXISTS "app"` before online migrations and stores the version table in the `app` schema.

## Migration history

| Revision | File | Creates |
|----------|------|---------|
| `001` | `001_create_users_table.py` | `app.users` |
| `002` | `002_create_agents_table.py` | `app.agents` |
| `003` | `003_create_workflows_tables.py` | `app.workflows`, `app.workflow_agents` |
| `004` | `004_user_password_reset_and_updated_at.py` | password reset columns, `users.updated_at` |
| `005` | `005_create_workflow_runs_tables.py` | `workflow_runs`, `run_messages`, `run_logs`, `run_usage` |
| `006` | `006_create_channel_links_table.py` | `app.channel_links` |

Apply:

```bash
cd backend
alembic upgrade head
```

## Entity-relationship (textual)

```mermaid
erDiagram
    users ||--o{ : "no FK from users"
    agents ||--o{ workflow_agents : "assigned to nodes"
    workflows ||--o{ workflow_agents : "has links"
    workflows ||--o{ workflow_runs : "executed as"
    workflow_runs ||--o{ run_messages : "contains"
    workflow_runs ||--o{ run_logs : "contains"
    workflow_runs ||--o{ run_usage : "contains"
    agents ||--o{ run_messages : "from_agent_id"
    agents ||--o{ run_messages : "to_agent_id"
    agents ||--o{ run_usage : "agent_id"
    agents ||--o{ channel_links : "linked"

    users {
        int id PK
        string email UK
        string hashed_password
        string full_name
        bool is_active
        string password_reset_token_hash
        datetime password_reset_expires_at
        datetime created_at
        datetime updated_at
    }

    agents {
        int id PK
        string name
        string role
        text system_prompt
        string model
        json tools
        json config
        bool is_active
        datetime created_at
        datetime updated_at
    }

    workflows {
        int id PK
        string name
        text description
        json graph_json
        int version
        bool is_template
        datetime created_at
        datetime updated_at
    }

    workflow_agents {
        int id PK
        int workflow_id FK
        int agent_id FK
        string node_id
    }

    workflow_runs {
        int id PK
        int workflow_id FK
        string status
        datetime started_at
        datetime finished_at
        text error
        string triggered_by
        datetime created_at
    }

    run_messages {
        int id PK
        int run_id FK
        int from_agent_id FK
        int to_agent_id FK
        string role
        text content
        string channel
        datetime created_at
    }

    run_logs {
        int id PK
        int run_id FK
        string level
        text message
        json metadata
        datetime created_at
    }

    run_usage {
        int id PK
        int run_id FK
        int agent_id FK
        int prompt_tokens
        int completion_tokens
        numeric cost_usd
        datetime created_at
    }

    channel_links {
        int id PK
        int agent_id FK
        string channel_type
        json config
        bool is_active
        datetime created_at
        datetime updated_at
    }
```

## Tables (detail)

### `app.users`

| Column | Type | Constraints / notes |
|--------|------|---------------------|
| `id` | Integer | PK, autoincrement |
| `email` | String(255) | **unique**, indexed |
| `hashed_password` | String(255) | bcrypt hash |
| `full_name` | String(255) | default `""` |
| `is_active` | Boolean | default true |
| `password_reset_token_hash` | String(64) | nullable |
| `password_reset_expires_at` | Timestamptz | nullable |
| `created_at`, `updated_at` | Timestamptz | server default `now()` |

### `app.agents`

| Column | Type | Constraints / notes |
|--------|------|---------------------|
| `id` | Integer | PK |
| `name` | String(255) | indexed |
| `role` | String(255) | |
| `system_prompt` | Text | |
| `model` | String(128) | default `gpt-4o-mini` |
| `tools` | JSON | list of tool names |
| `config` | JSON | memory, schedule, guardrails |
| `is_active` | Boolean | |

### `app.workflows`

| Column | Type | Notes |
|--------|------|-------|
| `graph_json` | JSON | `{ "nodes": [], "edges": [] }` Drawflow-compatible simplified graph |
| `is_template` | Boolean | indexed; templates vs user workflows |
| `version` | Integer | default 1 |

### `app.workflow_agents`

Join table mapping **Drawflow node IDs** to **agent IDs**.

| Column | FK | ondelete |
|--------|-----|----------|
| `workflow_id` | `workflows.id` | CASCADE |
| `agent_id` | `agents.id` | CASCADE |

### `app.workflow_runs`

| `status` values (constants) | `pending`, `running`, `completed`, `failed` |
| `triggered_by` | e.g. `api`, `ui`, `demo`, `manual` |

### `app.run_messages`

- `channel`: `internal`, `telegram`, etc.
- Agent FKs: `SET NULL` on agent delete

### `app.run_logs`

- DB column `metadata` mapped as ORM attribute `log_metadata` (JSON)

### `app.channel_links`

- `config` JSON: Telegram stores `chat_id`, `conversation_run_id`, etc.
- `channel_type`: e.g. `telegram` (`CHANNEL_TYPE_TELEGRAM`)

## Relationships (ORM)

| Parent | Child | Relationship |
|--------|-------|--------------|
| `Workflow` | `WorkflowAgent` | `cascade="all, delete-orphan"` |
| `WorkflowRun` | `RunMessage`, `RunLog`, `RunUsage` | cascade delete-orphan |
| `Agent` | `ChannelLink` | `backref="channel_links"` on Agent |

## Indexes (from migrations / models)

| Table | Index |
|-------|-------|
| `users` | unique `email` |
| `agents` | `name` |
| `workflows` | `name`, `is_template` |
| `workflow_agents` | `workflow_id`, `agent_id` |
| `workflow_runs` | `workflow_id`, `status` |
| `run_messages` | `run_id`, `from_agent_id`, `to_agent_id` |
| `run_logs` | `run_id` |
| `run_usage` | `run_id`, `agent_id` |
| `channel_links` | `agent_id`, `channel_type` |

## Workflow graph JSON (application contract)

Stored in `workflows.graph_json`. Node `type` values used by runtime (`graph_builder.py`, `nodes.py`):

- `agent` - LangChain agent node
- `condition` - branching / confidence loop
- `channel` - outbound Telegram notification node
- `end` - terminal

Edges use `from` / `to` node id strings. Agent nodes require matching rows in `workflow_agents` (`node_id` ↔ graph node `id`).
