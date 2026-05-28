# API Reference

Generated from `backend/app/api/**` and Pydantic schemas. Application title in OpenAPI: **Orqestra** (`settings.app_name`).

## Authentication

| Mechanism | Details |
|-----------|---------|
| Type | Signed **session cookie** (`session`) |
| Set by | `POST /api/v1/auth/login` or web `POST /auth/login` |
| API protection | `Depends(get_current_user)` -> **401** `{"detail":"Not authenticated"}` |
| Web protection | `Depends(get_current_user_web)` -> **302** `/auth/login` |
| Swagger | Use Auth login first; cookie is sent on subsequent requests |

**Public REST endpoints:** `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /health`, `POST /webhooks/telegram` (optional secret header).

---

## System

### `GET /health`

| | |
|--|--|
| **Auth** | None |
| **Purpose** | Liveness probe |

**Response 200**

```json
{
  "status": "ok",
  "app": "Orqestra"
}
```

---

## Auth (`/api/v1/auth`)

### `POST /api/v1/auth/login`

| | |
|--|--|
| **Auth** | None |
| **Purpose** | JSON login; sets session cookie |

**Request body** (`LoginRequest`)

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `email` | string (email) | yes | `EmailStr` |
| `password` | string | yes | min length 1 |

**Response 200** (`LoginResponse`)

```json
{
  "message": "Logged in successfully",
  "user": {
    "id": 1,
    "email": "admin@yuno.local",
    "full_name": "Platform Admin",
    "is_active": true
  }
}
```

**Errors**

| Status | Body |
|--------|------|
| 401 | `{"detail":"Invalid email or password"}` |
| 422 | Pydantic validation errors |

**Example**

```bash
curl -c cookies.txt -X POST http://localhost:3000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@yuno.local","password":"admin123"}'
```

### `POST /api/v1/auth/logout`

| | |
|--|--|
| **Auth** | None (clears session if present) |
| **Purpose** | Clear session |

**Response 200**

```json
{"message": "Logged out successfully"}
```

### `GET /api/v1/auth/me`

| | |
|--|--|
| **Auth** | Session required |
| **Purpose** | Current user profile |

**Response 200** (`UserResponse` - same shape as login `user`)

**Errors:** 401 not authenticated

---

## Users (`/api/v1/users`)

All routes require authentication.

### `GET /api/v1/users`

**Response 200:** `UserResponse[]`

### `POST /api/v1/users`

**Request body** (`UserCreate`)

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `email` | email | yes | unique (service-level) |
| `password` | string | yes | 8-128 chars |
| `full_name` | string | no | max 255, stripped |
| `is_active` | boolean | no | default `true` |

**Response 201:** `UserResponse`

**Errors:** 422 `detail` = dict of field errors (from `UserValidationError`)

### `GET /api/v1/users/{user_id}`

| Param | Type | In |
|-------|------|-----|
| `user_id` | int | path |

**Response 200:** `UserResponse`  
**Errors:** 404 `User not found`

### `PUT /api/v1/users/{user_id}`

**Request body** (`UserUpdate` - all fields optional)

| Field | Type | Validation |
|-------|------|------------|
| `email` | email | optional |
| `password` | string | 8-128 if set |
| `full_name` | string | max 255 |
| `is_active` | boolean | cannot deactivate self |

**Response 200:** `UserResponse`  
**Errors:** 404, 422

### `DELETE /api/v1/users/{user_id}`

**Response 204** (empty)  
**Errors:** 404, 422 (cannot delete self)

---

## Agents (`/api/v1/agents`)

### `GET /api/v1/agents`

**Response 200:** `AgentResponse[]`

### `POST /api/v1/agents`

**Request body** (`AgentCreate`)

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `name` | string | - | 1-255 chars, stripped |
| `role` | string | `""` | max 255 |
| `system_prompt` | string | `""` | |
| `model` | string | `gpt-4o-mini` | 1-128 chars |
| `tools` | string[] | `[]` | list or comma/newline string |
| `config` | object | `{}` | memory/schedule/guardrails |
| `is_active` | boolean | `true` | |

**Response 201:** `AgentResponse`

```json
{
  "id": 1,
  "name": "Researcher",
  "role": "research",
  "system_prompt": "...",
  "model": "gpt-4o-mini",
  "tools": ["web_search"],
  "config": {"memory": {}, "schedule": {}, "guardrails": {}},
  "is_active": true,
  "created_at": "2026-05-25T12:00:00Z",
  "updated_at": "2026-05-25T12:00:00Z"
}
```

### `GET /api/v1/agents/{agent_id}`

**Errors:** 404 `Agent not found`

### `PUT /api/v1/agents/{agent_id}`

**Request body** (`AgentUpdate` - partial)

**Errors:** 404, 422

### `DELETE /api/v1/agents/{agent_id}`

**Response 204**

---

## Workflows (`/api/v1/workflows`)

### `GET /api/v1/workflows`

| Query | Type | Description |
|-------|------|-------------|
| `templates_only` | bool \| null | If true, only `is_template=true` workflows |

**Response 200:** `WorkflowResponse[]`

```json
{
  "id": 2,
  "name": "Support Triage",
  "description": "",
  "graph_json": {"nodes": [], "edges": []},
  "version": 1,
  "is_template": true,
  "agent_links": [
    {"id": 1, "agent_id": 3, "node_id": "triage"}
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

### `POST /api/v1/workflows`

**Request body** (`WorkflowCreate`)

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | required, 1-255 |
| `description` | string | optional |
| `graph_json` | object | default empty graph |
| `version` | int | ≥ 1 |
| `is_template` | boolean | |
| `agent_links` | object[] | `{agent_id, node_id}` entries |

**Response 201:** `WorkflowResponse`

### `GET /api/v1/workflows/{workflow_id}`

**Errors:** 404

### `PUT /api/v1/workflows/{workflow_id}/graph`

**Purpose:** Persist visual builder graph (used by `ui/js/workflow-builder.js`).

**Request body** (`WorkflowGraphSave`)

| Field | Type | Validation |
|-------|------|------------|
| `graph_json` | object | must be JSON object |

**Response 200:** `WorkflowResponse`  
**Errors:** 404, 422

**Example**

```bash
curl -b cookies.txt -X PUT http://localhost:3000/api/v1/workflows/2/graph \
  -H "Content-Type: application/json" \
  -d '{"graph_json":{"nodes":[{"id":"a1","type":"agent"}],"edges":[]}}'
```

### `PUT /api/v1/workflows/{workflow_id}`

**Request body** (`WorkflowUpdate` - partial metadata + optional `graph_json`, `agent_links`)

### `DELETE /api/v1/workflows/{workflow_id}`

**Response 204**

### `POST /api/v1/workflows/templates/{template_id}/duplicate`

| Param / Query | Type | Description |
|---------------|------|-------------|
| `template_id` | int | path |
| `name` | string | optional query - new workflow name |

**Response 201:** `WorkflowResponse` (non-template copy)  
**Errors:** 404 `Template not found`, 422

---

## Runs (`/api/v1/runs`)

### `POST /api/v1/runs`

| | |
|--|--|
| **Purpose** | Enqueue workflow execution (Celery) |
| **Response** | **202 Accepted** |

| Query | Type | Default | Description |
|-------|------|---------|-------------|
| `workflow_id` | int | **required** | Workflow to run |
| `task` | string | `Execute the workflow.` | Task prompt for agents |
| `mock` | bool \| null | null | Override mock LLM; null uses settings |

**Response 202** (`WorkflowRunRead`)

```json
{
  "id": 10,
  "workflow_id": 2,
  "status": "pending",
  "started_at": null,
  "finished_at": null,
  "error": null,
  "triggered_by": "api",
  "created_at": "2026-05-25T12:00:00Z"
}
```

**Errors**

| Status | Detail |
|--------|--------|
| 404 | Workflow not found |
| 500 | `RunExecutionError` message string |
| 401 | Not authenticated |

**Example**

```bash
curl -b cookies.txt -X POST "http://localhost:3000/api/v1/runs?workflow_id=2&task=Run%20support%20triage"
```

### `POST /api/v1/runs/demo`

Hardcoded Researcher -> Writer graph (does not require saved workflow graph).

| Query | Type | Default |
|-------|------|---------|
| `task` | string | Research AI agent orchestration... |
| `workflow_id` | int \| null | null |
| `mock` | bool \| null | null |

**Response 202:** `WorkflowRunRead`  
**Errors:** 500 if demo agents not seeded

### `GET /api/v1/runs/{run_id}`

**Response 200** (`WorkflowRunDetail`)

| Field | Type |
|-------|------|
| (all `WorkflowRunRead` fields) | |
| `messages` | `RunMessageRead[]` |
| `logs` | `RunLogRead[]` |
| `usage` | `RunUsageRead[]` |
| `total_cost_usd` | decimal string/number |

**RunMessageRead**

| Field | Type |
|-------|------|
| `id`, `run_id` | int |
| `from_agent_id`, `to_agent_id` | int \| null |
| `role` | string |
| `content` | string |
| `channel` | string |
| `created_at` | datetime |

**Errors:** 404 `Run not found`

---

## Webhooks

### `POST /webhooks/telegram`

| | |
|--|--|
| **Auth** | Optional `X-Telegram-Bot-Api-Secret-Token` if `TELEGRAM_WEBHOOK_SECRET` is set |
| **Purpose** | Receive Telegram updates; enqueue Celery `process_telegram_update` |

**Headers**

| Header | Required when |
|--------|----------------|
| `X-Telegram-Bot-Api-Secret-Token` | `TELEGRAM_WEBHOOK_SECRET` non-empty |

**Request body:** raw Telegram Update JSON (`dict`)

**Response 200**

```json
{"ok": true}
```

**Errors**

| Status | Detail |
|--------|--------|
| 401 | Invalid Telegram webhook secret |
| 400 | Invalid payload (not object) |

**Note:** Inbound processing is async; HTTP returns before agent reply completes.

---

## Web UI routes (HTML)

Not listed in Swagger (`openapi.py` filters them). All except auth pages require session (redirect if missing).

### Auth pages

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/auth/login` | Login form |
| POST | `/auth/login` | Form login -> redirect `/dashboard` |
| POST/GET | `/auth/logout` | Clear session |
| GET | `/auth/forgot-password` | Forgot password form |
| POST | `/auth/forgot-password` | Send reset email (if SMTP configured) |
| GET | `/auth/reset-password?token=` | Reset form |
| POST | `/auth/reset-password` | Apply new password |

Query error codes (login): `invalid_email`, `invalid_credentials`. Reset: `mismatch`, `weak_password`, `invalid_token`, etc.

### Dashboard

| GET | `/dashboard` | Stats, active/recent/failed runs, messages |

### Users

| GET | `/users`, `/users/new`, `/users/{id}` |
| POST | `/users`, `/users/{id}` (update), `/users/{id}/delete` |

### Agents

| GET | `/agents`, `/agents/new`, `/agents/{id}` |
| POST | `/agents`, `/agents/{id}`, `/agents/{id}/delete` |

### Workflows

| GET | `/workflows`, `/workflows/templates`, `/workflows/new`, `/workflows/{id}`, `/workflows/{id}/edit` (builder) |
| POST | `/workflows`, `/workflows/{id}`, `/workflows/templates/{id}/use`, `/workflows/{id}/delete` |

### Runs

| GET | `/runs`, `/runs/{id}` |
| GET | `/runs/{id}/fragment/status`, `toolbar-status`, `logs`, `messages`, `usage` | HTMX partials |
| POST | `/workflows/{workflow_id}/run` | Form enqueue -> redirect `/runs/{id}` |

### Channels

| GET | `/channels`, `/channels/new` |
| POST | `/channels`, `/channels/{link_id}/delete` |

**No REST API** for channel links - UI + Telegram only.

### Root

| GET | `/` | Redirect to `/dashboard` or `/auth/login` |

---

## Dead code / schema-only artifacts

| Symbol | Location | Status |
|--------|----------|--------|
| `ChannelLinkCreate` | `schemas/channel.py` | No router consumes it |
| `TelegramWebhookUpdate` | `schemas/channel.py` | Webhook uses raw `dict` |

---

## Security observations

| Issue | Severity | Detail |
|-------|----------|--------|
| Webhook secret optional | Medium | Empty `TELEGRAM_WEBHOOK_SECRET` accepts any POST |
| No RBAC | Medium | All users share admin-level API access |
| Session cookie | Medium | `https_only=False` on SessionMiddleware |
| Default credentials | High (dev) | Seeded `ADMIN_EMAIL` / `ADMIN_PASSWORD` from env |
| Telegram webhook unauthenticated | Low-Med | By design when secret unset |

---

## OpenAPI access

| URL | Content |
|-----|---------|
| `/docs` | Swagger UI (REST + health only) |
| `/redoc` | ReDoc |
| `/openapi.json` | Filtered schema |

Disable via `OPENAPI_ENABLED=false`.
