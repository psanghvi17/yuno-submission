from copy import deepcopy

import pytest

from app.models.agent import Agent
from app.models.workflow import EMPTY_GRAPH_JSON, Workflow, WorkflowAgent
from app.models.workflow_run import (
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PENDING,
    RUN_STATUS_RUNNING,
)
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.run_service import RunCannotBeCancelled, RunService


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


def _seed_two_agent_workflow(db, researcher: Agent, writer: Agent) -> Workflow:
    graph_json = {
        "nodes": [
            {"id": "research", "type": "agent", "label": "Research", "agent_id": researcher.id},
            {"id": "writer", "type": "agent", "label": "Writer", "agent_id": writer.id},
        ],
        "edges": [{"from": "research", "to": "writer"}],
    }
    workflow = Workflow(
        name="Queue Test Pipeline",
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
    db.refresh(workflow)
    return workflow


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


def test_enqueue_run_completes_via_worker(db, runtime_agents, run_service):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)

    run = run_service.enqueue_run(workflow.id, mock_llm=True)
    db.expire_all()

    finished = run_service.get_run(run.id)
    assert finished.status == RUN_STATUS_COMPLETED
    detail = run_service.get_run_detail(run.id)
    assert len(detail.messages) >= 2
    assert any(
        "Run queued for workflow" in log.message for log in detail.logs
    )


def test_execute_run_status_transitions(db, runtime_agents, run_service):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)
    run = run_service.run_repo.create_run(workflow_id=workflow.id, triggered_by="test")

    assert run.status == RUN_STATUS_PENDING
    run_service.execute_run(run.id, mock_llm=True)
    updated = run_service.get_run(run.id)
    assert updated.status == RUN_STATUS_COMPLETED
    assert updated.started_at is not None
    assert updated.finished_at is not None


def test_enqueue_fails_without_agents(db, run_service):
    workflow_repo = WorkflowRepository(db)
    workflow = workflow_repo.create(
        name="Empty Queue",
        description="",
        graph_json=deepcopy(EMPTY_GRAPH_JSON),
        version=1,
        is_template=False,
        agent_links=[],
    )

    run = run_service.enqueue_run(workflow.id, mock_llm=True)
    db.expire_all()
    failed = run_service.get_run(run.id)
    assert failed.status == RUN_STATUS_FAILED


@pytest.fixture
def test_user(db):
    from app.core.security import hash_password
    from app.models.user import User

    user = User(
        email="test@example.com",
        hashed_password=hash_password("secret123"),
        full_name="Test User",
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
        data={"email": "test@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    return client


def test_api_enqueue_returns_202(auth_client, db, runtime_agents):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)

    auth_client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "secret123"},
    )

    response = auth_client.post(
        f"/api/v1/runs?workflow_id={workflow.id}&mock=true",
    )
    assert response.status_code == 202
    body = response.json()
    assert body["workflow_id"] == workflow.id
    assert body["status"] in (
        RUN_STATUS_PENDING,
        RUN_STATUS_COMPLETED,
        RUN_STATUS_RUNNING,
    )


def test_web_run_redirects_to_monitor(auth_client, db, runtime_agents):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)

    response = auth_client.post(f"/workflows/{workflow.id}/run", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/runs/")

    run_id = int(response.headers["location"].split("/runs/")[1].split("?")[0])
    page = auth_client.get(f"/runs/{run_id}")
    assert page.status_code == 200
    assert "Workflow run" in page.text
    assert "run-monitor-script" in page.text
    assert "run-logs-panel" in page.text
    assert "Download logs" in page.text
    # Eager worker may finish before first paint; polling only while pending/running
    assert (
        "data-run-poll" in page.text
        or "Completed" in page.text
        or "Failed" in page.text
    )


def test_run_fragments_require_auth(client, db, runtime_agents):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)
    run_repo = RunRepository(db)
    run = run_repo.create_run(workflow_id=workflow.id, triggered_by="test")

    for path in (
        f"/runs/{run.id}/fragment/logs",
        f"/runs/{run.id}/fragment/messages",
        f"/runs/{run.id}/fragment/usage",
        f"/runs/{run.id}/fragment/status",
        f"/runs/{run.id}/fragment/toolbar-status",
        f"/runs/{run.id}/fragment/history",
        f"/runs/{run.id}/download-logs",
    ):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["location"]


def test_run_fragments_return_html(auth_client, db, runtime_agents, run_service):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)
    run = run_service.start_run(workflow.id, mock_llm=True)

    logs = auth_client.get(f"/runs/{run.id}/fragment/logs")
    assert logs.status_code == 200
    assert "run-logs-panel" in logs.text
    assert "Run started" in logs.text or "Run queued" in logs.text or "Run completed" in logs.text

    messages = auth_client.get(f"/runs/{run.id}/fragment/messages")
    assert messages.status_code == 200
    assert "run-messages-panel" in messages.text

    usage = auth_client.get(f"/runs/{run.id}/fragment/usage")
    assert usage.status_code == 200
    assert "run-usage-panel" in usage.text

    status = auth_client.get(f"/runs/{run.id}/fragment/status")
    assert status.status_code == 200
    assert "run-status-panel" in status.text
    assert 'data-status="completed"' in status.text
    assert "data-run-poll" not in status.text


def test_run_fragments_poll_while_running(auth_client, db, runtime_agents):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)
    run_repo = RunRepository(db)
    run = run_repo.create_run(workflow_id=workflow.id, triggered_by="test")
    run_repo.mark_running(run)
    db.commit()

    fragment = auth_client.get(f"/runs/{run.id}/fragment/logs")
    assert fragment.status_code == 200
    assert "data-run-poll" in fragment.text
    assert f'id="run-logs-panel"' in fragment.text


def test_run_download_logs(auth_client, db, runtime_agents, run_service):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)
    run = run_service.start_run(workflow.id, mock_llm=True)

    response = auth_client.get(f"/runs/{run.id}/download-logs")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'filename="run-' in response.headers.get("content-disposition", "")
    body = response.text
    assert f"Workflow Run #{run.id}" in body
    assert "LOGS" in body
    assert "INTER-AGENT MESSAGES" in body
    assert "Run completed" in body or "Run started" in body


def test_run_history_fragment_returns_messages(auth_client, db, runtime_agents, run_service):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)
    run = run_service.start_run(workflow.id, mock_llm=True)

    fragment = auth_client.get(f"/runs/{run.id}/fragment/history")
    assert fragment.status_code == 200
    assert "run-history-content" in fragment.text
    assert "Agent responses" in fragment.text


def test_cancel_run_before_worker_starts(db, runtime_agents, run_service):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)
    run = run_service.run_repo.create_run(workflow_id=workflow.id, triggered_by="test")

    run_service.cancel_run(run.id)
    finished = run_service.execute_run(run.id, mock_llm=True)

    assert finished.status == RUN_STATUS_CANCELLED
    assert finished.cancel_requested is True


def test_cancel_run_while_running(db, runtime_agents, run_service, monkeypatch):
    from app.runtime import nodes as runtime_nodes

    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)
    run = run_service.run_repo.create_run(workflow_id=workflow.id, triggered_by="test")
    run_service.run_repo.mark_running(run)

    original = runtime_nodes.ensure_run_not_cancelled

    def stop_after_first_check(run_repo, run_id):
        original(run_repo, run_id)
        run_service.cancel_run(run_id)

    monkeypatch.setattr(runtime_nodes, "ensure_run_not_cancelled", stop_after_first_check)

    finished = run_service.execute_run(run.id, mock_llm=True)
    assert finished.status == RUN_STATUS_CANCELLED


def test_cancel_completed_run_raises(db, runtime_agents, run_service):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)
    run = run_service.start_run(workflow.id, mock_llm=True)

    with pytest.raises(RunCannotBeCancelled):
        run_service.cancel_run(run.id)


def test_web_stop_run_redirects(auth_client, db, runtime_agents):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)
    run_repo = RunRepository(db)
    run = run_repo.create_run(workflow_id=workflow.id, triggered_by="test")
    run_repo.mark_running(run)

    response = auth_client.post(f"/runs/{run.id}/stop", follow_redirects=False)
    assert response.status_code == 302
    assert f"/runs/{run.id}" in response.headers["location"]
    assert "stop_requested" in response.headers["location"]

    page = auth_client.get(f"/runs/{run.id}")
    assert "Stop run" in page.text or "Stopping" in page.text


def test_api_stop_run(auth_client, db, runtime_agents):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)
    run_repo = RunRepository(db)
    run = run_repo.create_run(workflow_id=workflow.id, triggered_by="test")
    run_repo.mark_running(run)

    auth_client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "secret123"},
    )

    response = auth_client.post(f"/api/v1/runs/{run.id}/stop")
    assert response.status_code == 200
    body = response.json()
    assert body["cancel_requested"] is True
