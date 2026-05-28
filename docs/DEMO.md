# Demo guide

Script for a product walkthrough that includes a **live Telegram conversation**. The challenge requires at least one external channel; Telegram is the supported channel in this project.

## Prerequisites

- `docker compose up --build` running from the repository root
- `SESSION_SECRET_KEY` set in `.env` (Compose sets `DATABASE_URL` and `REDIS_URL` in containers)
- Valid `OPENAI_API_KEY` in `.env` (default runtime uses real OpenAI + live tools)
- Or `RUNTIME_MOCK_LLM=true` / `RUNTIME_MOCK_TOOLS=true` for an offline recording
- **External channel (required):**
  - `TELEGRAM_BOT_TOKEN` from [@BotFather](https://t.me/BotFather) in `.env`
  - `TELEGRAM_USE_POLLING=true` for local demos (no ngrok or webhook setup)
  - Restart the stack after changing Telegram env vars: `docker compose up --build`

### Telegram setup (before recording)

1. Create a bot via BotFather and paste the token into `TELEGRAM_BOT_TOKEN`.
2. Start a chat with your bot in Telegram (send `/start`).
3. Obtain your **chat ID** (numeric): e.g. message [@userinfobot](https://t.me/userinfobot), or read `chat.id` from `https://api.telegram.org/bot<TOKEN>/getUpdates` after messaging the bot.
4. In the app, open **Channels** -> **Link agent** -> choose an agent (e.g. **Coordinator** or **Researcher**) and enter the chat ID.

## Suggested flow (6-9 minutes)

### 1. Login and dashboard (30s)

- Open http://localhost:3000/auth/login
- Sign in: `admin@yuno.local` / `admin123`
- Show **Dashboard**: agent count, active/recent runs, recent messages

### 2. Agents (45s)

- **Agents** -> show seeded Researcher, Writer, Coordinator
- Open **Researcher** -> point out system prompt, tools, memory/schedule/guardrails config

### 3. Workflow templates (1 min)

- **Workflows** -> **Templates**
- Open **Research & Notify** in builder - Researcher -> Writer -> Telegram channel node
- **Use template** -> save as user workflow

### 4. Run workflow + live monitor (2 min)

- Open the new workflow -> **Run workflow**
- Land on **Run monitor** - show status badge updating (HTMX)
- Expand **Logs**, **Inter-agent messages**, **Token usage**
- Highlight two agents' messages on the `internal` channel

### 5. Support triage template (1 min)

- Run **Support Triage Loop** (or duplicate and run)
- Mention condition node / confidence loop in logs

### 6. Live external channel - Telegram (required, 2-3 min)

**Include this in your recorded demo.** Evaluators expect a real back-and-forth on an external channel, not only in-app UI.

1. Confirm **Channels** shows Telegram configured (polling on if using `TELEGRAM_USE_POLLING`).
2. Show the agent ↔ chat link from setup above.
3. In Telegram, send a message to the bot (e.g. "Summarize our platform in one sentence").
4. Show the bot's reply in Telegram.
5. In the app, open the linked **Run #** - show `channel=telegram` inbound/outbound messages on the run monitor.

### 7. API / architecture (30s)

- Open `/docs` - show `POST /api/v1/runs`, agents API
- Mention LangGraph + worker (architecture slide or `docs/ARCHITECTURE.md`)

## Video link placeholder

After recording, add your URL to the root `README.md`:

```markdown
## Demo video

https://your-link-here
```

## Quick health check before recording

```bash
curl http://localhost:3000/health
cd backend && python -m pytest -q
```

Confirm Telegram: with polling enabled, API logs should not show repeated `409 Conflict` (only one process should poll the same bot token).
