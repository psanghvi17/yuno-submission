"""Telegram and channel message delivery tests (mocked)."""

from unittest.mock import patch

import pytest

from app.models.channel_link import CHANNEL_TYPE_TELEGRAM
from app.models.workflow import Workflow, WorkflowAgent
from app.repositories.agent_repository import AgentRepository
from app.repositories.channel_repository import ChannelRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.agent_service import AgentService
from app.services.channel_service import build_channel_service
from app.services.run_service import RunService
from app.services.workflow_service import WorkflowService


@pytest.fixture(autouse=True)
def _celery_eager(db, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.workers import tasks as worker_tasks
    from app.workers.celery_app import celery_app

    worker_session = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())

    monkeypatch.setattr(worker_tasks, "_open_worker_db", lambda: worker_session())
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False


def _telegram_update(chat_id: str, text: str) -> dict:
    return {
        "update_id": 99,
        "message": {
            "message_id": 1,
            "text": text,
            "chat": {"id": int(chat_id), "type": "private"},
            "from": {"id": 42, "username": "human"},
        },
    }


@pytest.fixture
def agents_and_workflow(db):
    agent_repo = AgentRepository(db)
    researcher = agent_repo.create(
        name="Researcher",
        role="research",
        system_prompt="Reply briefly.",
        model="gpt-4o-mini",
        tools=[],
        config={"memory": {}, "schedule": {}, "guardrails": {}},
        is_active=True,
    )
    writer = agent_repo.create(
        name="Writer",
        role="write",
        system_prompt="Summarize.",
        model="gpt-4o-mini",
        tools=[],
        config={"memory": {}, "schedule": {}, "guardrails": {}},
        is_active=True,
    )
    workflow = Workflow(
        name="Demo: Content Pipeline",
        description="",
        graph_json={"nodes": [], "edges": []},
        version=1,
        is_template=False,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return researcher, writer, workflow


def test_inbound_telegram_delivers_assistant_message(db, agents_and_workflow):
    researcher, _, _ = agents_and_workflow
    service = build_channel_service(db)
    service.link_agent(
        agent_id=researcher.id,
        channel_type=CHANNEL_TYPE_TELEGRAM,
        chat_id="700001",
    )

    with patch.object(service, "send_telegram_message", return_value={"ok": True}) as send:
        result = service.handle_telegram_update(
            _telegram_update("700001", "What is LangGraph?")
        )

    assert result["ok"] is True
    send.assert_called_once()
    call_args = send.call_args[0]
    assert call_args[0] == "700001"
    assert len(call_args[1]) > 0

    messages = RunRepository(db).list_messages(result["run_id"])
    roles = [(m.role, m.channel) for m in messages]
    assert ("user", "telegram") in roles
    assert ("assistant", "telegram") in roles


def test_workflow_notify_delivers_to_telegram(db, agents_and_workflow):
    researcher, writer, workflow = agents_and_workflow
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
    workflow.graph_json = graph_json
    db.commit()
    for node_id, agent_id in (("research", researcher.id), ("writer", writer.id)):
        db.add(WorkflowAgent(workflow_id=workflow.id, agent_id=agent_id, node_id=node_id))
    db.commit()

    ChannelRepository(db).create(
        agent_id=writer.id,
        channel_type=CHANNEL_TYPE_TELEGRAM,
        config={"chat_id": "700002"},
    )

    run_service = RunService(
        RunRepository(db),
        WorkflowRepository(db),
        AgentRepository(db),
    )

    with patch(
        "app.services.channel_service.TelegramChannel.send_message",
        return_value={"ok": True, "result": {"message_id": 1}},
    ) as send:
        run = run_service.start_run(workflow.id, mock_llm=True)

    assert run.status == "completed"
    send.assert_called()
    messages = run_service.run_repo.list_messages(run.id)
    assert any(m.channel == "telegram" for m in messages)


def test_webhook_message_delivery_via_worker(db, agents_and_workflow, client):
    researcher, _, _ = agents_and_workflow
    ChannelRepository(db).create(
        agent_id=researcher.id,
        channel_type=CHANNEL_TYPE_TELEGRAM,
        config={"chat_id": "700003"},
    )

    from app.workers import tasks as worker_tasks

    with patch(
        "app.services.channel_service.ChannelService.send_telegram_message",
        return_value={"ok": True},
    ):
        result = worker_tasks.process_telegram_update.apply(
            args=[_telegram_update("700003", "Hello bot")]
        ).get()

    assert result["ok"] is True
    messages = RunRepository(db).list_messages(result["run_id"])
    assert len(messages) >= 2


def test_telegram_launch_triggers_e2e_pipeline(db):
    agent_service = AgentService(AgentRepository(db))
    agent_service.seed_e2e_pipeline_agents()
    wf_service = WorkflowService(WorkflowRepository(db), AgentRepository(db))
    workflow = wf_service.seed_e2e_run_workflow()
    assert workflow is not None

    link_agent = agent_service.agent_repo.list_all()[0]
    service = build_channel_service(db)
    service.link_agent(
        agent_id=link_agent.id,
        channel_type=CHANNEL_TYPE_TELEGRAM,
        chat_id="700010",
    )

    sent: list[str] = []

    def capture_send(chat_id: str, text: str) -> dict:
        sent.append(text)
        return {"ok": True}

    with patch.object(service, "send_telegram_message", side_effect=capture_send):
        result = service.handle_telegram_update(
            _telegram_update("700010", "/launch")
        )

    assert result["ok"] is True
    assert result.get("mode") == "workflow_launch"
    assert any("pipeline started" in msg.lower() for msg in sent)

    run = RunRepository(db).get_run(result["run_id"])
    assert run is not None
    assert run.triggered_by == "telegram"
    logs = RunRepository(db).list_logs(run.id)
    assert any(
        (log.log_metadata or {}).get("telegram_chat_id") == "700010" for log in logs
    )
