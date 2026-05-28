import json
from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from app.models.agent import DEFAULT_AGENT_CONFIG, Agent
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import AgentCreate, AgentUpdate


class AgentNotFound(Exception):
    pass


class AgentValidationError(Exception):
    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__(str(errors))


class AgentService:
    def __init__(self, agent_repo: AgentRepository) -> None:
        self.agent_repo = agent_repo

    def list_agents(self) -> list[Agent]:
        return self.agent_repo.list_all()

    def get_agent(self, agent_id: int) -> Agent:
        agent = self.agent_repo.get_by_id(agent_id)
        if not agent:
            raise AgentNotFound(f"Agent {agent_id} not found")
        return agent

    def create_agent(self, data: AgentCreate) -> Agent:
        self._ensure_unique_name(data.name)
        return self.agent_repo.create(
            name=data.name,
            role=data.role,
            system_prompt=data.system_prompt,
            model=data.model,
            tools=data.tools,
            config=self._normalize_config(data.config),
            is_active=data.is_active,
        )

    def update_agent(self, agent_id: int, data: AgentUpdate) -> Agent:
        agent = self.get_agent(agent_id)
        updates = data.model_dump(exclude_unset=True)

        if "name" in updates and updates["name"] != agent.name:
            self._ensure_unique_name(updates["name"], exclude_id=agent.id)

        if "config" in updates:
            updates["config"] = self._normalize_config(updates["config"])

        if not updates:
            return agent

        return self.agent_repo.update(agent, **updates)

    def delete_agent(self, agent_id: int) -> None:
        agent = self.get_agent(agent_id)
        self.agent_repo.delete(agent)

    def seed_default_agents(self) -> list[Agent]:
        if self.agent_repo.count() > 0:
            return []

        defaults = [
            AgentCreate(
                name="Researcher",
                role="Gather information",
                system_prompt=(
                    "You are a research agent. Gather accurate, concise information "
                    "and cite sources when possible."
                ),
                model="gpt-4o-mini",
                tools=["web_search"],
            ),
            AgentCreate(
                name="Writer",
                role="Summarize and format",
                system_prompt=(
                    "You are a writing agent. Turn research into clear summaries "
                    "for humans and downstream agents."
                ),
                model="gpt-4o-mini",
                tools=[],
            ),
            AgentCreate(
                name="Coordinator",
                role="Route and delegate",
                system_prompt=(
                    "You are a support triage agent. Classify the user request and "
                    "respond with JSON containing confidence (0-1), category, and a short "
                    "summary. Example: {\"confidence\": 0.82, \"category\": \"billing\", "
                    "\"summary\": \"User cannot access invoice.\"}"
                ),
                model="gpt-4o-mini",
                tools=[],
                config={
                    "memory": {"context": "Retain last triage decision.", "max_turns": 8},
                    "schedule": {"enabled": False, "cron": "", "notes": ""},
                    "guardrails": {
                        "max_tokens": 800,
                        "blocked_topics": ["medical diagnosis"],
                    },
                },
            ),
        ]
        return [self.create_agent(item) for item in defaults]

    E2E_PIPELINE_AGENT_NAMES = (
        "Brief Intake",
        "Market Scout",
        "Campaign Strategist",
        "Launch Copywriter",
        "Editorial Reviewer",
    )

    def seed_e2e_pipeline_agents(self) -> list[Agent]:
        """Five agents for the Product Launch Pipeline end-to-end demo."""
        if self.agent_repo.get_by_name(self.E2E_PIPELINE_AGENT_NAMES[0]):
            return []

        specs = [
            AgentCreate(
                name="Brief Intake",
                role="Parse launch briefs",
                system_prompt=(
                    "You are a product marketing intake specialist. Read the campaign "
                    "brief and output a clear bullet list: product, audience, goal, tone, "
                    "mandatory talking points, and constraints. Be concise; do not write "
                    "the final announcement yet."
                ),
                model="gpt-4o-mini",
                tools=[],
            ),
            AgentCreate(
                name="Market Scout",
                role="Market and competitor research",
                system_prompt=(
                    "You are a market research analyst. Using the brief and any tool "
                    "results, summarize 3–5 relevant market trends, competitor angles, "
                    "or customer pain points that should inform the launch. Cite sources "
                    "when web search data is available."
                ),
                model="gpt-4o-mini",
                tools=["web_search"],
            ),
            AgentCreate(
                name="Campaign Strategist",
                role="Launch strategy",
                system_prompt=(
                    "You are a campaign strategist. Based on the brief and market research, "
                    "propose a launch plan with: (1) core message, (2) three channels "
                    "(e.g. email, blog, social), (3) CTA, (4) success metrics. "
                    "Keep it actionable for a copywriter."
                ),
                model="gpt-4o-mini",
                tools=[],
            ),
            AgentCreate(
                name="Launch Copywriter",
                role="Draft announcement copy",
                system_prompt=(
                    "You are a B2B product copywriter. Write a first-draft launch "
                    "announcement (150–250 words) using the strategy and prior context. "
                    "Include a headline, body, and clear CTA. Match the tone from the brief."
                ),
                model="gpt-4o-mini",
                tools=["write_file"],
            ),
            AgentCreate(
                name="Editorial Reviewer",
                role="Polish final copy",
                system_prompt=(
                    "You are a senior editor. Polish the draft into a final launch "
                    "announcement under 400 words. Fix clarity and flow; keep facts "
                    "accurate. Output only the finished announcement text (headline + body + CTA), "
                    "ready to send to stakeholders."
                ),
                model="gpt-4o-mini",
                tools=[],
            ),
        ]
        return [self.create_agent(item) for item in specs]

    DEV_PIPELINE_AGENT_NAMES = (
        "Dev Planner",
        "Backend Engineer",
        "Frontend Engineer",
        "Code Reviewer",
        "QA Tester",
        "DevOps Engineer",
    )

    @staticmethod
    def dev_pipeline_agent_specs() -> list[AgentCreate]:
        """Agent definitions for the build-and-deploy dev pipeline."""
        return [
            AgentCreate(
                name="Dev Planner",
                role="Break user request into dev tasks",
                system_prompt=(
                    "You are a senior software architect. The Task describes the business "
                    "(any industry — use only what the Task says).\n\n"
                    "TOOL BUDGET: exactly 2 tool calls, then stop.\n"
                    "1. init_dev_project\n"
                    "2. list_project_files\n"
                    "Do not call any other tools.\n\n"
                    "Then output a short written plan (no more tools):\n"
                    "- Business name + tagline\n"
                    "- API list (method, path, purpose) — extend scaffold /api/health, /api/info, /api/bookings\n"
                    "- DB columns for bookings\n"
                    "- Frontend sections + form fields\n"
                    "- QA: GET /api/health → 200; POST /api/bookings → 201 Created and row persisted\n\n"
                    "Keep the plan under 400 words so engineers can implement in few file edits."
                ),
                model="gpt-4o-mini",
                tools=["init_dev_project", "list_project_files"],
            ),
            AgentCreate(
                name="Backend Engineer",
                role="Implement FastAPI backend from the plan",
                system_prompt=(
                    "You are a backend engineer. Implement the Task + Planner plan on the scaffold "
                    "(FastAPI, SQLite, CORS, static frontend mount, GET /api/health).\n\n"
                    "REST: POST /api/bookings must return HTTP 201 Created — use "
                    "@app.post(\"/api/bookings\", status_code=201). "
                    "backend/tests/test_api.py must assert status_code == 201 for that POST.\n\n"
                    "TOOL BUDGET: at most 5 tool calls, then you MUST reply with text only (no tools).\n"
                    "Typical first pass (4 calls):\n"
                    "1. read_project_file backend/main.py\n"
                    "2. write_project_file backend/main.py — full file, business-specific routes\n"
                    "3. read_project_file backend/tests/test_api.py\n"
                    "4. write_project_file backend/tests/test_api.py — health + booking test only\n"
                    "Do NOT call list_project_files. Do NOT read the same file twice.\n"
                    "Write complete files in one write each — no incremental patches.\n\n"
                    "If sent back from Reviewer/Tester: at most 2 tools (read one file, write one file) "
                    "for the broken file only, then text summary.\n\n"
                    "Final message: 3–5 bullets — endpoints added, files changed, ready for frontend."
                ),
                model="gpt-4o-mini",
                tools=["read_project_file", "write_project_file"],
            ),
            AgentCreate(
                name="Frontend Engineer",
                role="Build HTML/CSS/JS from the plan",
                system_prompt=(
                    "You are a frontend engineer. Build the site for the Task + Planner plan.\n\n"
                    "CRITICAL ASSETS RULES:\n"
                    "- index.html MUST link CSS as /static/styles.css\n"
                    "- index.html MUST load JS as /static/app.js\n"
                    "- UI QUALITY BAR: produce a premium, modern UI (hero section, cards, polished spacing, "
                    "clear typography hierarchy, responsive layout).\n"
                    "- Write non-empty, visibly styled CSS in frontend/styles.css (layout, spacing, colors, "
                    "buttons, forms, section cards).\n"
                    "- Do NOT output plain unstyled HTML. Keep visual polish high.\n"
                    "- Keep API fetch calls pointing at /api/... paths.\n\n"
                    "TOOL BUDGET: at most 5 tool calls, then text only (no tools).\n"
                    "Typical first pass (4 calls):\n"
                    "1. read_project_file backend/main.py — learn API paths only\n"
                    "2. write_project_file frontend/index.html — full file, real business copy\n"
                    "3. write_project_file frontend/styles.css — full file\n"
                    "4. write_project_file frontend/app.js — full file, wire form to Backend APIs\n"
                    "Do NOT call list_project_files. Do NOT read frontend files before overwriting.\n"
                    "Replace all 'Your Business' placeholders.\n\n"
                    "If sent back from Reviewer: one read + one write on the flagged file only.\n\n"
                    "Final message: short summary of pages and which API endpoints the form uses."
                ),
                model="gpt-4o-mini",
                tools=["read_project_file", "write_project_file"],
            ),
            AgentCreate(
                name="Code Reviewer",
                role="Review code quality, security, and correctness",
                system_prompt=(
                    "You are a code reviewer. Check the Task + plan against the code.\n\n"
                    "BOOKING API: POST /api/bookings must return 201 Created (FastAPI status_code=201 on "
                    "that route). Tests must expect 201 for the booking POST — not 200.\n\n"
                    "FRONTEND ASSETS: index.html must reference /static/styles.css and /static/app.js. "
                    "If missing/wrong, reject with fix_target frontend.\n"
                    "FRONTEND QUALITY: reject plain/minimal UI. Require meaningful styled layout in "
                    "frontend/styles.css (hero/sections/cards/form polish).\n\n"
                    "TOOL BUDGET: at most 5 read_project_file calls, then stop with JSON only.\n"
                    "Read exactly these (once each):\n"
                    "- backend/main.py\n"
                    "- backend/tests/test_api.py\n"
                    "- frontend/index.html\n"
                    "- frontend/app.js\n"
                    "- frontend/styles.css\n"
                    "Do NOT call list_project_files. Do NOT write files.\n\n"
                    "Then output raw JSON only (no markdown):\n"
                    '{"approved": true, "issues": [], "fix_target": null}\n'
                    'or {"approved": false, "issues": ["..."], "fix_target": "backend|frontend|both"}'
                ),
                model="gpt-4o-mini",
                tools=["read_project_file"],
            ),
            AgentCreate(
                name="QA Tester",
                role="Run automated tests and verify the app",
                system_prompt=(
                    "You are a QA engineer. Call run_project_tests and report results.\n\n"
                    "End with raw JSON only:\n"
                    '{"tests_passed": true, "details": "..."}\n'
                    'or {"tests_passed": false, "details": "...", "fix_target": "backend|frontend|both"}\n'
                    "Do not fix code yourself."
                ),
                model="gpt-4o-mini",
                tools=["run_project_tests"],
            ),
            AgentCreate(
                name="DevOps Engineer",
                role="Publish to GitHub and deploy to DigitalOcean",
                system_prompt=(
                    "You are a DevOps engineer.\n\n"
                    "TOOL BUDGET: exactly 3 tool calls in order, then one short text line (no tools).\n"
                    "1. github_publish_project — if JSON has status failed, stop; do not deploy\n"
                    "2. do_deploy_from_github (clone_url from step 1 only when status is published)\n"
                    "3. send_notification — include business name from Task, live URL, GitHub link\n"
                    "Do not call any other tools. Do not repeat publish or deploy."
                ),
                model="gpt-4o-mini",
                tools=["github_publish_project", "do_deploy_from_github", "send_notification"],
            ),
        ]

    def seed_dev_pipeline_agents(self) -> list[Agent]:
        """Six agents for the build-and-deploy dev pipeline."""
        if self.agent_repo.get_by_name(self.DEV_PIPELINE_AGENT_NAMES[0]):
            return []
        return [self.create_agent(item) for item in self.dev_pipeline_agent_specs()]

    def refresh_dev_pipeline_agents(self) -> int:
        """Update prompts/tools for existing dev pipeline agents (after prompt changes)."""
        updated = 0
        specs_by_name = {s.name: s for s in self.dev_pipeline_agent_specs()}
        for name in self.DEV_PIPELINE_AGENT_NAMES:
            spec = specs_by_name.get(name)
            agent = self.agent_repo.get_by_name(name) if spec else None
            if not agent or not spec:
                continue
            self.agent_repo.update(
                agent,
                role=spec.role,
                system_prompt=spec.system_prompt,
                tools=spec.tools,
            )
            updated += 1
        return updated

    @staticmethod
    def parse_tools_field(raw: str) -> list[str]:
        if not raw.strip():
            return []
        return [
            part.strip()
            for part in raw.replace(",", "\n").split("\n")
            if part.strip()
        ]

    @staticmethod
    def parse_config_field(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if not text:
            return deepcopy(DEFAULT_AGENT_CONFIG)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AgentValidationError(
                {"config": f"Invalid JSON: {exc.msg}"}
            ) from exc
        if not isinstance(parsed, dict):
            raise AgentValidationError({"config": "Config must be a JSON object"})
        return AgentService._normalize_config(parsed)

    @staticmethod
    def config_from_form_fields(
        *,
        memory_context: str = "",
        memory_max_turns: str = "10",
        schedule_enabled: bool = False,
        schedule_cron: str = "",
        schedule_notes: str = "",
        guardrails_max_tokens: str = "",
        guardrails_topics: str = "",
        config_raw: str = "",
    ) -> dict[str, Any]:
        if config_raw.strip():
            return AgentService.parse_config_field(config_raw)

        max_turns = 10
        if memory_max_turns.strip().isdigit():
            max_turns = int(memory_max_turns.strip())

        max_tokens = None
        if guardrails_max_tokens.strip().isdigit():
            max_tokens = int(guardrails_max_tokens.strip())

        blocked = [
            line.strip()
            for line in guardrails_topics.replace(",", "\n").split("\n")
            if line.strip()
        ]

        return AgentService._normalize_config(
            {
                "memory": {
                    "context": memory_context.strip(),
                    "max_turns": max_turns,
                },
                "schedule": {
                    "enabled": schedule_enabled,
                    "cron": schedule_cron.strip(),
                    "notes": schedule_notes.strip(),
                },
                "guardrails": {
                    "max_tokens": max_tokens,
                    "blocked_topics": blocked,
                },
            }
        )

    @staticmethod
    def form_fields_from_config(config: dict[str, Any] | None) -> dict[str, Any]:
        base = AgentService._normalize_config(config)
        memory = base.get("memory") or {}
        schedule = base.get("schedule") or {}
        guardrails = base.get("guardrails") or {}
        topics = guardrails.get("blocked_topics") or []
        if isinstance(topics, list):
            topics_text = "\n".join(str(t) for t in topics)
        else:
            topics_text = str(topics)
        return {
            "memory_context": memory.get("context", ""),
            "memory_max_turns": str(memory.get("max_turns", 10)),
            "schedule_enabled": bool(schedule.get("enabled", False)),
            "schedule_cron": schedule.get("cron", ""),
            "schedule_notes": schedule.get("notes", ""),
            "guardrails_max_tokens": (
                str(guardrails["max_tokens"])
                if guardrails.get("max_tokens") is not None
                else ""
            ),
            "guardrails_topics": topics_text,
            "config_raw": json.dumps(base, indent=2),
        }

    @staticmethod
    def build_create_from_form(
        *,
        name: str,
        role: str,
        system_prompt: str,
        model: str,
        tools_raw: str,
        config_raw: str = "",
        is_active: bool,
        memory_context: str = "",
        memory_max_turns: str = "10",
        schedule_enabled: bool = False,
        schedule_cron: str = "",
        schedule_notes: str = "",
        guardrails_max_tokens: str = "",
        guardrails_topics: str = "",
    ) -> AgentCreate:
        errors: dict[str, str] = {}
        try:
            tools = AgentService.parse_tools_field(tools_raw)
        except ValidationError as exc:
            errors["tools"] = "Invalid tools format"
            tools = []

        try:
            config = AgentService.config_from_form_fields(
                memory_context=memory_context,
                memory_max_turns=memory_max_turns,
                schedule_enabled=schedule_enabled,
                schedule_cron=schedule_cron,
                schedule_notes=schedule_notes,
                guardrails_max_tokens=guardrails_max_tokens,
                guardrails_topics=guardrails_topics,
                config_raw=config_raw,
            )
        except AgentValidationError as exc:
            errors.update(exc.errors)
            config = deepcopy(DEFAULT_AGENT_CONFIG)

        try:
            payload = AgentCreate(
                name=name,
                role=role,
                system_prompt=system_prompt,
                model=model or "gpt-4o-mini",
                tools=tools,
                config=config,
                is_active=is_active,
            )
        except ValidationError as exc:
            for err in exc.errors():
                field = ".".join(str(part) for part in err["loc"])
                errors[field or "form"] = err["msg"]
            raise AgentValidationError(errors) from exc

        if errors:
            raise AgentValidationError(errors)
        return payload

    def _ensure_unique_name(self, name: str, *, exclude_id: int | None = None) -> None:
        existing = self.agent_repo.get_by_name(name)
        if existing and existing.id != exclude_id:
            raise AgentValidationError({"name": "An agent with this name already exists"})

    @staticmethod
    def _normalize_config(config: dict[str, Any] | None) -> dict[str, Any]:
        base = deepcopy(DEFAULT_AGENT_CONFIG)
        if not config:
            return base
        for key in ("memory", "schedule", "guardrails"):
            if key in config:
                base[key] = config[key]
        return base
