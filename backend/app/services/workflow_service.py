from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from app.models.workflow import EMPTY_GRAPH_JSON, Workflow
from app.repositories.agent_repository import AgentRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate


class WorkflowNotFound(Exception):
    pass


class WorkflowValidationError(Exception):
    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__(str(errors))


def _graph_node_count(graph_json: dict[str, Any] | None) -> int:
    if not graph_json:
        return 0
    nodes = graph_json.get("nodes")
    if isinstance(nodes, list):
        return len(nodes)
    drawflow = graph_json.get("drawflow", {})
    if isinstance(drawflow, dict):
        home = drawflow.get("Home", {})
        data = home.get("data", {}) if isinstance(home, dict) else {}
        if isinstance(data, dict):
            return len(data)
    return 0


class WorkflowService:
    def __init__(
        self,
        workflow_repo: WorkflowRepository,
        agent_repo: AgentRepository,
    ) -> None:
        self.workflow_repo = workflow_repo
        self.agent_repo = agent_repo

    def list_workflows(self, *, templates_only: bool | None = None) -> list[Workflow]:
        return self.workflow_repo.list_all(templates_only=templates_only)

    def get_workflow(self, workflow_id: int) -> Workflow:
        workflow = self.workflow_repo.get_by_id(workflow_id)
        if not workflow:
            raise WorkflowNotFound(f"Workflow {workflow_id} not found")
        return workflow

    def create_workflow(self, data: WorkflowCreate) -> Workflow:
        self._ensure_unique_name(data.name, is_template=data.is_template)
        graph_json = self._normalize_graph_json(data.graph_json)
        agent_links = self._validate_agent_links(data.agent_links)
        return self.workflow_repo.create(
            name=data.name,
            description=data.description,
            graph_json=graph_json,
            version=data.version,
            is_template=data.is_template,
            agent_links=agent_links,
        )

    def update_workflow(self, workflow_id: int, data: WorkflowUpdate) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        updates = data.model_dump(exclude_unset=True)
        agent_links = updates.pop("agent_links", None)

        if "name" in updates and updates["name"] != workflow.name:
            self._ensure_unique_name(
                updates["name"],
                is_template=updates.get("is_template", workflow.is_template),
                exclude_id=workflow.id,
            )

        if "graph_json" in updates:
            updates["graph_json"] = self._normalize_graph_json(updates["graph_json"])

        if agent_links is not None:
            agent_links = self._validate_agent_links(agent_links)

        if not updates and agent_links is None:
            return workflow

        return self.workflow_repo.update(workflow, agent_links=agent_links, **updates)

    def delete_workflow(self, workflow_id: int) -> None:
        workflow = self.get_workflow(workflow_id)
        self.workflow_repo.delete(workflow)

    def save_workflow_graph(
        self,
        workflow_id: int,
        graph_json: dict[str, Any],
    ) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        normalized = self._normalize_graph_json(graph_json)
        agent_links = self._agent_links_from_graph(normalized)
        return self.workflow_repo.update(
            workflow,
            graph_json=normalized,
            agent_links=agent_links,
            version=workflow.version + 1,
        )

    def duplicate_from_template(
        self,
        template_id: int,
        *,
        name: str | None = None,
    ) -> Workflow:
        template = self.get_workflow(template_id)
        if not template.is_template:
            raise WorkflowValidationError(
                {"template": "Only template workflows can be duplicated"}
            )

        base_name = (name or f"{template.name} (copy)").strip()
        unique_name = self._next_available_name(base_name, is_template=False)

        agent_links = [
            {"agent_id": link.agent_id, "node_id": link.node_id}
            for link in template.agent_links
        ]
        payload = WorkflowCreate(
            name=unique_name,
            description=template.description,
            graph_json=deepcopy(template.graph_json or EMPTY_GRAPH_JSON),
            version=1,
            is_template=False,
            agent_links=agent_links,
        )
        return self.create_workflow(payload)

    DEMO_WORKFLOW_NAME = "Demo: Content Pipeline"
    E2E_TEMPLATE_NAME = "Product Launch Pipeline (E2E)"
    E2E_RUN_WORKFLOW_NAME = "E2E: Product Launch (run me)"
    DEV_TEMPLATE_NAME = "Dev Pipeline: Build & Deploy (template)"
    DEV_RUN_WORKFLOW_NAME = "Dev Pipeline: Build & Deploy (run me)"
    DEV_RUN_WORKFLOW_LEGACY_NAME = "Dev Pipeline: Trattoria Luna (run me)"
    DEV_DEFAULT_TASK_INPUT = (
        "Build a website for Trattoria Luna — Italian restaurant.\n"
        "Landing page with name, hours, menu highlights, and a table reservation form.\n"
        "Store reservations in SQLite. Deploy when tests pass."
    )
    E2E_DEFAULT_TASK_INPUT = (
        "Product launch brief:\n"
        "Product: Orqestra — multi-agent workflow orchestration platform for teams.\n"
        "Audience: Engineering managers and platform teams evaluating AI tooling.\n"
        "Goal: Announce public beta and drive demo signups.\n"
        "Tone: Professional, concise, confident.\n"
        "Deliverable: Short launch announcement for email and Telegram.\n"
        "Key points: visual workflow builder, LangGraph runtime, live run monitoring, "
        "Telegram human-in-the-loop channel, Celery async execution."
    )

    def seed_dev_pipeline_template(self) -> Workflow | None:
        if self.workflow_repo.get_by_name(self.DEV_TEMPLATE_NAME, is_template=True):
            return None
        agents_by_name = {agent.name: agent for agent in self.agent_repo.list_all()}
        return self.create_workflow(self._dev_pipeline_graph(agents_by_name, is_template=True))

    def seed_dev_run_workflow(self) -> Workflow | None:
        if self.workflow_repo.get_by_name(self.DEV_RUN_WORKFLOW_NAME, is_template=False):
            return None
        agents_by_name = {agent.name: agent for agent in self.agent_repo.list_all()}
        return self.create_workflow(self._dev_pipeline_graph(agents_by_name, is_template=False))

    def refresh_dev_pipeline_workflows(self) -> int:
        """Rename legacy runnable workflow and refresh descriptions."""
        updated = 0
        legacy = self.workflow_repo.get_by_name(
            self.DEV_RUN_WORKFLOW_LEGACY_NAME,
            is_template=False,
        )
        target = self.workflow_repo.get_by_name(self.DEV_RUN_WORKFLOW_NAME, is_template=False)
        if legacy and not target:
            self.workflow_repo.update(
                legacy,
                name=self.DEV_RUN_WORKFLOW_NAME,
                description=(
                    "6-agent dev pipeline: build and deploy from the user's Telegram brief."
                ),
            )
            updated += 1
        for wf in self.workflow_repo.list_all():
            if wf.name in (self.DEV_TEMPLATE_NAME, self.DEV_RUN_WORKFLOW_NAME):
                self.workflow_repo.update(
                    wf,
                    description=(
                        "6-agent dev pipeline: Planner → Backend → Frontend → "
                        "Reviewer (loop) → Tester (loop) → DevOps."
                    ),
                )
                updated += 1
        return updated

    def _dev_pipeline_graph(
        self, agents_by_name: dict[str, Any], *, is_template: bool
    ) -> "WorkflowCreate":
        planner = agents_by_name.get("Dev Planner")
        backend = agents_by_name.get("Backend Engineer")
        frontend = agents_by_name.get("Frontend Engineer")
        reviewer = agents_by_name.get("Code Reviewer")
        tester = agents_by_name.get("QA Tester")
        devops = agents_by_name.get("DevOps Engineer")

        nodes = [
            {"id": "planner", "type": "agent", "label": "Dev Planner", "agent_name": "Dev Planner"},
            {"id": "backend", "type": "agent", "label": "Backend Engineer", "agent_name": "Backend Engineer"},
            {"id": "frontend", "type": "agent", "label": "Frontend Engineer", "agent_name": "Frontend Engineer"},
            {"id": "reviewer", "type": "agent", "label": "Code Reviewer", "agent_name": "Code Reviewer"},
            {
                "id": "review_gate",
                "type": "condition",
                "label": "Review passed?",
                "field": "approved",
            },
            {"id": "tester", "type": "agent", "label": "QA Tester", "agent_name": "QA Tester"},
            {
                "id": "test_gate",
                "type": "condition",
                "label": "Tests passed?",
                "field": "tests_passed",
            },
            {"id": "devops", "type": "agent", "label": "DevOps Engineer", "agent_name": "DevOps Engineer"},
        ]

        edges = [
            {"from": "planner", "to": "backend"},
            {"from": "backend", "to": "frontend"},
            {"from": "frontend", "to": "reviewer"},
            {"from": "reviewer", "to": "review_gate"},
            # review_gate: ok → tester; low → backend (max 2 loops)
            {"from": "review_gate", "to": "tester", "when": "ok"},
            {"from": "review_gate", "to": "backend", "when": "low", "max_loops": 2},
            {"from": "tester", "to": "test_gate"},
            # test_gate: ok → devops; low → backend (max 2 loops)
            {"from": "test_gate", "to": "devops", "when": "ok"},
            {"from": "test_gate", "to": "backend", "when": "low", "max_loops": 2},
        ]

        agent_links = []
        for agent, node_id in [
            (planner, "planner"),
            (backend, "backend"),
            (frontend, "frontend"),
            (reviewer, "reviewer"),
            (tester, "tester"),
            (devops, "devops"),
        ]:
            if agent:
                agent_links.append({"agent_id": agent.id, "node_id": node_id})

        name = self.DEV_TEMPLATE_NAME if is_template else self.DEV_RUN_WORKFLOW_NAME
        description = (
            "6-agent dev pipeline: Planner → Backend → Frontend → Reviewer (loop) "
            "→ Tester (loop) → DevOps. Builds and deploys a site from the user's Telegram brief."
        )
        return WorkflowCreate(
            name=name,
            description=description,
            graph_json={"nodes": nodes, "edges": edges},
            is_template=is_template,
            agent_links=agent_links,
        )

    def seed_workflow_templates(self) -> list[Workflow]:
        if self.workflow_repo.count_templates() > 0:
            return []

        agents_by_name = {agent.name: agent for agent in self.agent_repo.list_all()}
        templates = [
            self._research_notify_template(agents_by_name),
            self._support_triage_template(agents_by_name),
        ]
        return [self.create_workflow(item) for item in templates]

    def seed_demo_workflow(self) -> Workflow | None:
        if self.workflow_repo.get_by_name(self.DEMO_WORKFLOW_NAME, is_template=False):
            return None

        agents_by_name = {agent.name: agent for agent in self.agent_repo.list_all()}
        return self.create_workflow(self._demo_content_pipeline(agents_by_name))

    def seed_e2e_pipeline_template(self) -> Workflow | None:
        if self.workflow_repo.get_by_name(self.E2E_TEMPLATE_NAME, is_template=True):
            return None
        agents_by_name = {agent.name: agent for agent in self.agent_repo.list_all()}
        return self.create_workflow(self._product_launch_pipeline_template(agents_by_name))

    def seed_e2e_run_workflow(self) -> Workflow | None:
        if self.workflow_repo.get_by_name(self.E2E_RUN_WORKFLOW_NAME, is_template=False):
            return None
        agents_by_name = {agent.name: agent for agent in self.agent_repo.list_all()}
        payload = self._product_launch_pipeline_template(agents_by_name)
        payload = payload.model_copy(
            update={
                "name": self.E2E_RUN_WORKFLOW_NAME,
                "description": (
                    "Ready-to-run 5-agent product launch pipeline. Open this workflow, "
                    "click Run workflow, and watch the run monitor."
                ),
                "is_template": False,
            }
        )
        return self.create_workflow(payload)

    @staticmethod
    def node_count(workflow: Workflow) -> int:
        return _graph_node_count(workflow.graph_json)

    def build_create_from_form(
        self,
        *,
        name: str,
        description: str,
    ) -> WorkflowCreate:
        errors: dict[str, str] = {}
        try:
            payload = WorkflowCreate(
                name=name,
                description=description,
                graph_json=deepcopy(EMPTY_GRAPH_JSON),
                is_template=False,
            )
        except ValidationError as exc:
            for err in exc.errors():
                field = ".".join(str(part) for part in err["loc"])
                errors[field or "form"] = err["msg"]
            raise WorkflowValidationError(errors) from exc
        return payload

    def _research_notify_template(
        self, agents_by_name: dict[str, Any]
    ) -> WorkflowCreate:
        researcher = agents_by_name.get("Researcher")
        writer = agents_by_name.get("Writer")
        graph_json = {
            "nodes": [
                {
                    "id": "research",
                    "type": "agent",
                    "label": "Research Agent",
                    "agent_name": "Researcher",
                },
                {
                    "id": "writer",
                    "type": "agent",
                    "label": "Writer Agent",
                    "agent_name": "Writer",
                },
                {
                    "id": "notify",
                    "type": "channel",
                    "label": "Notify via Telegram",
                    "channel": "telegram",
                },
            ],
            "edges": [
                {"from": "research", "to": "writer"},
                {"from": "writer", "to": "notify"},
            ],
        }
        agent_links = []
        if researcher:
            agent_links.append({"agent_id": researcher.id, "node_id": "research"})
        if writer:
            agent_links.append({"agent_id": writer.id, "node_id": "writer"})
        return WorkflowCreate(
            name="Research & Notify",
            description=(
                "Research agent gathers information, writer summarizes, "
                "then a Telegram notification is sent to the human."
            ),
            graph_json=graph_json,
            is_template=True,
            agent_links=agent_links,
        )

    def _demo_content_pipeline(self, agents_by_name: dict[str, Any]) -> WorkflowCreate:
        coordinator = agents_by_name.get("Coordinator")
        researcher = agents_by_name.get("Researcher")
        writer = agents_by_name.get("Writer")

        graph_json = {
            "nodes": [
                {
                    "id": "coordinate",
                    "type": "agent",
                    "label": "Coordinator",
                    "agent_name": "Coordinator",
                    "pos_x": 60,
                    "pos_y": 140,
                },
                {
                    "id": "research",
                    "type": "agent",
                    "label": "Researcher",
                    "agent_name": "Researcher",
                    "pos_x": 280,
                    "pos_y": 60,
                },
                {
                    "id": "write",
                    "type": "agent",
                    "label": "Writer",
                    "agent_name": "Writer",
                    "pos_x": 500,
                    "pos_y": 140,
                },
                {
                    "id": "done",
                    "type": "end",
                    "label": "Complete",
                    "pos_x": 720,
                    "pos_y": 140,
                },
            ],
            "edges": [
                {"from": "coordinate", "to": "research"},
                {"from": "research", "to": "write"},
                {"from": "write", "to": "done"},
            ],
        }

        agent_links = []
        if coordinator:
            graph_json["nodes"][0]["agent_id"] = coordinator.id
            agent_links.append({"agent_id": coordinator.id, "node_id": "coordinate"})
        if researcher:
            graph_json["nodes"][1]["agent_id"] = researcher.id
            agent_links.append({"agent_id": researcher.id, "node_id": "research"})
        if writer:
            graph_json["nodes"][2]["agent_id"] = writer.id
            agent_links.append({"agent_id": writer.id, "node_id": "write"})

        return WorkflowCreate(
            name=self.DEMO_WORKFLOW_NAME,
            description=(
                "Sample workflow for demos: the coordinator plans the task, "
                "the researcher gathers facts, and the writer produces the final summary."
            ),
            graph_json=graph_json,
            is_template=False,
            agent_links=agent_links,
        )

    def _product_launch_pipeline_template(
        self, agents_by_name: dict[str, Any]
    ) -> WorkflowCreate:
        """Five agents in series, then Telegram notify — end-to-end launch demo."""
        node_specs = [
            ("intake", "Brief Intake", "Brief Intake", 40, 120),
            ("scout", "Market Scout", "Market Scout", 220, 40),
            ("strategy", "Campaign Strategist", "Campaign Strategist", 400, 120),
            ("copy", "Launch Copywriter", "Launch Copywriter", 580, 40),
            ("review", "Editorial Reviewer", "Editorial Reviewer", 760, 120),
        ]
        nodes: list[dict[str, Any]] = []
        agent_links: list[dict[str, Any]] = []
        for node_id, label, agent_name, pos_x, pos_y in node_specs:
            agent = agents_by_name.get(agent_name)
            node: dict[str, Any] = {
                "id": node_id,
                "type": "agent",
                "label": label,
                "agent_name": agent_name,
                "pos_x": pos_x,
                "pos_y": pos_y,
            }
            if agent:
                node["agent_id"] = agent.id
                agent_links.append({"agent_id": agent.id, "node_id": node_id})
            nodes.append(node)

        nodes.append(
            {
                "id": "notify",
                "type": "channel",
                "label": "Notify via Telegram",
                "channel": "telegram",
                "pos_x": 940,
                "pos_y": 120,
            }
        )

        edges = [
            {"from": "intake", "to": "scout"},
            {"from": "scout", "to": "strategy"},
            {"from": "strategy", "to": "copy"},
            {"from": "copy", "to": "review"},
            {"from": "review", "to": "notify"},
        ]

        return WorkflowCreate(
            name=self.E2E_TEMPLATE_NAME,
            description=(
                "End-to-end product launch: intake brief → market research (web search) "
                "→ strategy → copy draft → editorial polish → Telegram notification."
            ),
            graph_json={"nodes": nodes, "edges": edges},
            is_template=True,
            agent_links=agent_links,
        )

    def _support_triage_template(self, agents_by_name: dict[str, Any]) -> WorkflowCreate:
        coordinator = agents_by_name.get("Coordinator")
        writer = agents_by_name.get("Writer")
        graph_json = {
            "nodes": [
                {
                    "id": "triage",
                    "type": "agent",
                    "label": "Triage Agent",
                    "agent_name": "Coordinator",
                },
                {
                    "id": "confidence_check",
                    "type": "condition",
                    "label": "Confidence OK?",
                    "field": "confidence",
                    "threshold": 0.7,
                },
                {
                    "id": "specialist",
                    "type": "agent",
                    "label": "Specialist Agent",
                    "agent_name": "Writer",
                },
                {"id": "end", "type": "end", "label": "END"},
            ],
            "edges": [
                {"from": "triage", "to": "confidence_check"},
                {"from": "confidence_check", "to": "specialist", "when": "ok"},
                {"from": "confidence_check", "to": "triage", "when": "low", "max_loops": 3},
                {"from": "specialist", "to": "end"},
            ],
        }
        agent_links = []
        if coordinator:
            agent_links.append({"agent_id": coordinator.id, "node_id": "triage"})
        if writer:
            agent_links.append({"agent_id": writer.id, "node_id": "specialist"})
        return WorkflowCreate(
            name="Support Triage Loop",
            description=(
                "Triage agent classifies the request; low confidence loops back "
                "to triage (max 3 times) before handing off to a specialist."
            ),
            graph_json=graph_json,
            is_template=True,
            agent_links=agent_links,
        )

    def _ensure_unique_name(
        self,
        name: str,
        *,
        is_template: bool,
        exclude_id: int | None = None,
    ) -> None:
        existing = self.workflow_repo.get_by_name(name, is_template=is_template)
        if existing and existing.id != exclude_id:
            scope = "template" if is_template else "workflow"
            raise WorkflowValidationError(
                {"name": f"A {scope} with this name already exists"}
            )

    def _next_available_name(self, base_name: str, *, is_template: bool) -> str:
        candidate = base_name
        suffix = 2
        while True:
            existing = self.workflow_repo.get_by_name(candidate, is_template=is_template)
            if not existing:
                return candidate
            candidate = f"{base_name} ({suffix})"
            suffix += 1

    @staticmethod
    def _normalize_graph_json(graph_json: dict[str, Any] | None) -> dict[str, Any]:
        if not graph_json:
            return deepcopy(EMPTY_GRAPH_JSON)
        if not isinstance(graph_json, dict):
            raise WorkflowValidationError({"graph_json": "Graph must be a JSON object"})
        normalized = deepcopy(graph_json)
        if "nodes" not in normalized and "drawflow" not in normalized:
            normalized.setdefault("nodes", [])
            normalized.setdefault("edges", [])
        return normalized

    def _agent_links_from_graph(self, graph_json: dict[str, Any]) -> list[dict[str, Any]]:
        links: list[dict[str, Any]] = []
        nodes = graph_json.get("nodes")
        if not isinstance(nodes, list):
            return links
        seen_node_ids: set[str] = set()
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("type") != "agent":
                continue
            node_id = str(node.get("id", "")).strip()
            agent_id = node.get("agent_id")
            if not node_id or agent_id is None:
                continue
            if node_id in seen_node_ids:
                raise WorkflowValidationError(
                    {"graph_json": f"Duplicate agent node id: {node_id}"}
                )
            seen_node_ids.add(node_id)
            if not self.agent_repo.get_by_id(int(agent_id)):
                raise WorkflowValidationError(
                    {"graph_json": f"Agent {agent_id} not found for node {node_id}"}
                )
            links.append({"agent_id": int(agent_id), "node_id": node_id})
        return links

    def _validate_agent_links(
        self, links: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        if not links:
            return []
        validated: list[dict[str, Any]] = []
        for index, link in enumerate(links):
            agent_id = link.get("agent_id")
            node_id = str(link.get("node_id", "")).strip()
            if not agent_id or not node_id:
                raise WorkflowValidationError(
                    {f"agent_links.{index}": "Each link requires agent_id and node_id"}
                )
            if not self.agent_repo.get_by_id(int(agent_id)):
                raise WorkflowValidationError(
                    {f"agent_links.{index}": f"Agent {agent_id} not found"}
                )
            validated.append({"agent_id": int(agent_id), "node_id": node_id})
        return validated
