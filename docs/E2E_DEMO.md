# End-to-end demo: Product Launch Pipeline (5 agents)

This walkthrough runs **five specialized agents** in sequence, then sends the final copy to **Telegram**.

## Pipeline

```text
Brief Intake → Market Scout → Campaign Strategist → Launch Copywriter → Editorial Reviewer → Telegram
     │              │                  │                    │                    │
  parse brief   web_search         launch plan          draft copy         final polish
```

| Agent | Role | Tools |
|-------|------|--------|
| **Brief Intake** | Extract goals, audience, tone from the brief | — |
| **Market Scout** | Trends and competitor angles | `web_search` |
| **Campaign Strategist** | Channels, CTA, metrics | — |
| **Launch Copywriter** | First-draft announcement | `write_file` |
| **Editorial Reviewer** | Final polished announcement | — |
| *(channel)* | Sends last agent output to linked Telegram chat | — |

## One-time setup

### 1. Seed agents and workflow

If the stack was already running before this feature was added:

```bash
bash scripts/seed_e2e_demo.sh
```

Or restart the API (seeds on startup if agents are missing):

```bash
docker compose up -d --build
```

### 2. Telegram (optional but recommended)

1. **Channels** → link an agent (e.g. **Editorial Reviewer**) to your chat ID.
2. `TELEGRAM_BOT_TOKEN` and polling enabled in `.env`.

## Run via Telegram (trigger + final reply)

1. Link **any** agent to your chat under **Channels** (chat ID from @userinfobot).
2. Ensure `docker compose` is up with **api** + **worker** (pipeline runs in the worker).
3. In Telegram, send to your bot:

```text
/launch
```

Or with a custom brief:

```text
/launch Product: Orqestra beta. Audience: platform engineers. Tone: upbeat.
```

4. You immediately get: *“Product launch pipeline started (Run #N)…”*
5. When all five agents finish, you receive the **final announcement** on Telegram (from the pipeline’s notify step).

Other commands: `/help`, `/chat <message>` (1:1 with linked agent), `/reset`.

## Run the demo (UI)

1. Open http://localhost:3000 and log in.
2. **Workflows** → open **`E2E: Product Launch (run me)`**.
3. Open the **builder** — you should see five agent nodes + **Notify via Telegram**.
4. Click **Run workflow**.
5. Open the **run monitor**:
   - **Logs** — each agent node start/complete
   - **Inter-agent messages** — handoffs on `internal` / `handoff`
   - **Token usage** — per agent
6. When the run completes, check **Telegram** for the final announcement (if channel link exists).

### Suggested task input

The default brief is pre-filled when you use the script below. In the UI, use **Run workflow** (default task text is in the run log) or paste:

```text
Product launch brief:
Product: Orqestra — multi-agent workflow orchestration platform for teams.
Audience: Engineering managers and platform teams evaluating AI tooling.
Goal: Announce public beta and drive demo signups.
Tone: Professional, concise, confident.
Deliverable: Short launch announcement for email and Telegram.
Key points: visual workflow builder, LangGraph runtime, live run monitoring,
Telegram human-in-the-loop channel, Celery async execution.
```

## Run from CLI (queue + monitor)

```bash
bash scripts/seed_e2e_demo.sh --run
# Mock LLM (no OpenAI cost):
bash scripts/seed_e2e_demo.sh --run --mock
```

Then open the printed run URL, e.g. http://localhost:3000/runs/12

## Verify success

| Check | Expected |
|-------|----------|
| Run status | `completed` |
| 5 agent steps in logs | intake → scout → strategy → copy → review |
| Market Scout | log may show `Tool executed: web_search` |
| Messages | Multiple `internal` / `handoff` rows |
| Telegram | Final announcement text (not JSON triage) |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Workflow missing | `bash scripts/seed_e2e_demo.sh` |
| Run stays `pending` | Ensure `worker` container is up: `docker compose ps` |
| No Telegram message | Link channel; run must reach **notify** node |
| Scout slow / errors | Set `RUNTIME_MOCK_TOOLS=true` for offline demo |

## Template vs runnable copy

| Name | Type | Use |
|------|------|-----|
| **Product Launch Pipeline (E2E)** | Template | Duplicate and customize in the builder |
| **E2E: Product Launch (run me)** | Workflow | Click Run immediately |
