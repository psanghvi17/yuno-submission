"""Dashboard, templates, conditions, and agent config."""

from copy import deepcopy

import pytest

from app.models.agent import Agent
from app.models.workflow import Workflow, WorkflowAgent
from app.models.workflow_run import RUN_STATUS_COMPLETED
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.agent_service import AgentService
from app.services.run_service import RunService
from app.services.workflow_service import WorkflowService


@pytest.fixture
def runtime_agents(db):
    repo = AgentRepository(db)
    researcher = repo.create(
        name="Researcher",
        role="research",
        system_prompt="Research.",
        model="gpt-4o-mini",
        tools=["web_search"],
        config={"memory": {}, "schedule": {}, "guardrails": {}},
        is_active=True,
    )
    coordinator = repo.create(
        name="Coordinator",
        role="triage",
        system_prompt='Respond with JSON: {"confidence": 0.5, "category": "test"}',
        model="gpt-4o-mini",
        tools=[],
        config={"memory": {}, "schedule": {}, "guardrails": {}},
        is_active=True,
    )
    writer = repo.create(
        name="Writer",
        role="write",
        system_prompt="Specialist.",
        model="gpt-4o-mini",
        tools=[],
        config={"memory": {}, "schedule": {}, "guardrails": {}},
        is_active=True,
    )
    return researcher, coordinator, writer


@pytest.fixture
def run_service(db):
    return RunService(
        RunRepository(db),
        WorkflowRepository(db),
        AgentRepository(db),
    )


def test_templates_include_research_notify_and_triage(db):
    wf_service = WorkflowService(WorkflowRepository(db), AgentRepository(db))
    templates = wf_service.seed_workflow_templates()
    names = {t.name for t in templates}
    assert "Research & Notify" in names
    assert "Support Triage Loop" in names

    research = wf_service.workflow_repo.get_by_name("Research & Notify", is_template=True)
    assert research is not None
    nodes = research.graph_json["nodes"]
    types = {n["type"] for n in nodes}
    assert "agent" in types
    assert "channel" in types
    assert any(n.get("channel") == "telegram" for n in nodes if n["type"] == "channel")


def test_support_triage_template_runs(db, runtime_agents, run_service):
    _, coordinator, writer = runtime_agents
    graph_json = {
        "nodes": [
            {"id": "triage", "type": "agent", "agent_id": coordinator.id},
            {
                "id": "confidence_check",
                "type": "condition",
                "field": "confidence",
                "threshold": 0.7,
            },
            {"id": "specialist", "type": "agent", "agent_id": writer.id},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"from": "triage", "to": "confidence_check"},
            {"from": "confidence_check", "to": "specialist", "when": "ok"},
            {"from": "confidence_check", "to": "triage", "when": "low", "max_loops": 3},
            {"from": "specialist", "to": "end"},
        ],
    }
    workflow = Workflow(
        name="Triage Test",
        description="",
        graph_json=graph_json,
        version=1,
        is_template=False,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    db.add(WorkflowAgent(workflow_id=workflow.id, agent_id=coordinator.id, node_id="triage"))
    db.add(WorkflowAgent(workflow_id=workflow.id, agent_id=writer.id, node_id="specialist"))
    db.commit()

    run = run_service.start_run(workflow.id, mock_llm=True)
    assert run.status == RUN_STATUS_COMPLETED
    logs = run_service.run_repo.list_logs(run.id)
    assert any("Condition 'confidence_check'" in log.message for log in logs)


def test_agent_config_from_form_fields():
    config = AgentService.config_from_form_fields(
        memory_context="Remember user locale",
        memory_max_turns="5",
        schedule_enabled=True,
        schedule_cron="0 9 * * *",
        guardrails_max_tokens="500",
        guardrails_topics="spam\nphishing",
    )
    assert config["memory"]["context"] == "Remember user locale"
    assert config["memory"]["max_turns"] == 5
    assert config["schedule"]["enabled"] is True
    assert config["guardrails"]["max_tokens"] == 500
    assert "spam" in config["guardrails"]["blocked_topics"]


@pytest.fixture
def test_user(db):
    from app.core.security import hash_password
    from app.models.user import User

    user = User(
        email="dash@example.com",
        hashed_password=hash_password("secret123"),
        full_name="Dash",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_client(client, test_user):
    client.post(
        "/auth/login",
        data={"email": "dash@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    return client


def test_dashboard_page(auth_client):
    response = auth_client.get("/dashboard")
    assert response.status_code == 200
    assert "Active runs" in response.text
    assert "Recent messages" in response.text


def test_runs_list_page(auth_client):
    response = auth_client.get("/runs")
    assert response.status_code == 200
    assert "Run history" in response.text
