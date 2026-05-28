"""End-to-end workflow run tests."""

from copy import deepcopy

import pytest

from app.models.agent import Agent
from app.models.workflow import EMPTY_GRAPH_JSON, Workflow, WorkflowAgent
from app.models.workflow_run import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PENDING,
)
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.run_service import RunExecutionError, RunService
from app.services.workflow_service import WorkflowService


@pytest.fixture(autouse=True)
def _celery_eager(db, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.workers import tasks as worker_tasks
    from app.workers.celery_app import celery_app

    worker_session = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())

    def open_test_db():
        return worker_session()

    monkeypatch.setattr(worker_tasks, "_open_worker_db", open_test_db)
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


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
    writer = repo.create(
        name="Writer",
        role="write",
        system_prompt="Write.",
        model="gpt-4o-mini",
        tools=[],
        config={"memory": {}, "schedule": {}, "guardrails": {}},
        is_active=True,
    )
    return researcher, writer


@pytest.fixture
def run_service(db):
    return RunService(
        RunRepository(db),
        WorkflowRepository(db),
        AgentRepository(db),
    )


def _linear_workflow(db, researcher: Agent, writer: Agent) -> Workflow:
    graph_json = {
        "nodes": [
            {"id": "research", "type": "agent", "agent_id": researcher.id},
            {"id": "writer", "type": "agent", "agent_id": writer.id},
        ],
        "edges": [{"from": "research", "to": "writer"}],
    }
    workflow = Workflow(
        name="E2E Pipeline",
        description="",
        graph_json=graph_json,
        version=1,
        is_template=False,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    db.add(WorkflowAgent(workflow_id=workflow.id, agent_id=researcher.id, node_id="research"))
    db.add(WorkflowAgent(workflow_id=workflow.id, agent_id=writer.id, node_id="writer"))
    db.commit()
    return workflow


def test_workflow_run_enqueue_completes_with_messages(db, runtime_agents, run_service):
    researcher, writer = runtime_agents
    workflow = _linear_workflow(db, researcher, writer)

    run = run_service.enqueue_run(workflow.id, mock_llm=True)
    assert run.status == RUN_STATUS_PENDING

    db.expire_all()
    finished = run_service.get_run(run.id)
    assert finished.status == RUN_STATUS_COMPLETED

    detail = run_service.get_run_detail(run.id)
    assert len(detail.messages) >= 2
    assert len(detail.logs) >= 2
    assert len(detail.usage) >= 1
    agent_ids = {m.from_agent_id for m in detail.messages}
    assert researcher.id in agent_ids
    assert writer.id in agent_ids


def test_workflow_run_from_research_notify_template_graph(db, runtime_agents, run_service):
    researcher, writer = runtime_agents
    graph_json = {
        "nodes": [
            {"id": "research", "type": "agent", "agent_id": researcher.id},
            {"id": "writer", "type": "agent", "agent_id": writer.id},
            {"id": "notify", "type": "channel", "channel": "telegram"},
        ],
        "edges": [
            {"from": "research", "to": "writer"},
            {"from": "writer", "to": "notify"},
        ],
    }
    workflow = Workflow(
        name="Research Notify E2E",
        description="",
        graph_json=graph_json,
        version=1,
        is_template=False,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    for node_id, agent_id in (("research", researcher.id), ("writer", writer.id)):
        db.add(WorkflowAgent(workflow_id=workflow.id, agent_id=agent_id, node_id=node_id))
    db.commit()

    run = run_service.start_run(workflow.id, mock_llm=True)
    assert run.status == RUN_STATUS_COMPLETED
    messages = run_service.run_repo.list_messages(run.id)
    assert any(m.channel == "telegram" for m in messages)


def test_workflow_run_fails_without_agents(db, run_service):
    workflow_repo = WorkflowRepository(db)
    workflow = workflow_repo.create(
        name="Empty E2E",
        description="",
        graph_json=deepcopy(EMPTY_GRAPH_JSON),
        version=1,
        is_template=False,
        agent_links=[],
    )

    run = run_service.enqueue_run(workflow.id, mock_llm=True)
    db.expire_all()
    assert run_service.get_run(run.id).status == RUN_STATUS_FAILED


def test_api_workflow_run_returns_202(client, db, runtime_agents):
    from app.core.security import hash_password
    from app.models.user import User

    user = User(
        email="runapi@example.com",
        hashed_password=hash_password("secret123"),
        full_name="Run API",
        is_active=True,
    )
    db.add(user)
    db.commit()

    client.post(
        "/auth/login",
        data={"email": "runapi@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    client.post(
        "/api/v1/auth/login",
        json={"email": "runapi@example.com", "password": "secret123"},
    )

    researcher, writer = runtime_agents
    workflow = _linear_workflow(db, researcher, writer)

    response = client.post(f"/api/v1/runs?workflow_id={workflow.id}&mock=true")
    assert response.status_code == 202
    body = response.json()
    assert body["workflow_id"] == workflow.id
    assert body["status"] in (RUN_STATUS_COMPLETED, RUN_STATUS_PENDING, "running")


def test_e2e_product_launch_five_agent_pipeline(db, run_service):
    agent_repo = AgentRepository(db)
    agent_service = __import__(
        "app.services.agent_service", fromlist=["AgentService"]
    ).AgentService(agent_repo)
    wf_service = WorkflowService(WorkflowRepository(db), agent_repo)

    created_agents = agent_service.seed_e2e_pipeline_agents()
    assert len(created_agents) == 5

    workflow = wf_service.seed_e2e_run_workflow()
    assert workflow is not None
    assert workflow.name == WorkflowService.E2E_RUN_WORKFLOW_NAME

    run = run_service.enqueue_run(
        workflow.id,
        task_input=WorkflowService.E2E_DEFAULT_TASK_INPUT,
        mock_llm=True,
    )
    db.expire_all()
    finished = run_service.get_run(run.id)
    assert finished.status == RUN_STATUS_COMPLETED

    detail = run_service.get_run_detail(run.id)
    log_text = " ".join(log.message for log in detail.logs)
    for label in (
        "Brief Intake",
        "Market Scout",
        "Campaign Strategist",
        "Launch Copywriter",
        "Editorial Reviewer",
    ):
        assert label in log_text
    assert any(m.channel == "telegram" for m in detail.messages)
    assert len(detail.usage) >= 5
