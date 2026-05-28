from unittest.mock import MagicMock, patch

import pytest

from app.models.channel_link import CHANNEL_TYPE_TELEGRAM
from app.repositories.agent_repository import AgentRepository
from app.repositories.channel_repository import ChannelRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.channel_service import ChannelService, build_channel_service


@pytest.fixture
def channel_service(db):
    return build_channel_service(db)


@pytest.fixture
def researcher_agent(db):
    return AgentRepository(db).create(
        name="Researcher",
        role="research",
        system_prompt="You help via Telegram.",
        model="gpt-4o-mini",
        tools=[],
        config={"memory": {}, "schedule": {}, "guardrails": {}},
        is_active=True,
    )


@pytest.fixture
def demo_workflow(db, researcher_agent):
    from app.models.workflow import Workflow

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
    return workflow


def _telegram_update(chat_id: str, text: str) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "text": text,
            "chat": {"id": int(chat_id), "type": "private"},
            "from": {"id": 1, "username": "tester", "first_name": "Test"},
        },
    }


def test_link_agent(channel_service, researcher_agent):
    link = channel_service.link_agent(
        agent_id=researcher_agent.id,
        channel_type=CHANNEL_TYPE_TELEGRAM,
        chat_id="999001",
    )
    assert link.agent_id == researcher_agent.id
    assert link.config["chat_id"] == "999001"


def test_handle_inbound_creates_messages_and_run(
    db,
    channel_service,
    researcher_agent,
    demo_workflow,
):
    channel_service.link_agent(
        agent_id=researcher_agent.id,
        channel_type=CHANNEL_TYPE_TELEGRAM,
        chat_id="999002",
    )
    with patch.object(
        channel_service,
        "send_telegram_message",
        return_value={"ok": True},
    ) as mock_send:
        result = channel_service.handle_telegram_update(
            _telegram_update("999002", "Hello from Telegram")
        )

    assert result["ok"] is True
    assert "run_id" in result
    mock_send.assert_called_once()
    run_repo = RunRepository(db)
    messages = run_repo.list_messages(result["run_id"])
    assert len(messages) >= 2
    assert any(m.channel == "telegram" and m.role == "user" for m in messages)
    assert any(m.channel == "telegram" and m.role == "assistant" for m in messages)


def test_webhook_enqueues_task(client, db, researcher_agent, demo_workflow):
    from app.workers import tasks as worker_tasks

    ChannelRepository(db).create(
        agent_id=researcher_agent.id,
        channel_type=CHANNEL_TYPE_TELEGRAM,
        config={"chat_id": "999003"},
    )

    with patch.object(worker_tasks.process_telegram_update, "delay") as mock_delay:
        response = client.post(
            "/webhooks/telegram",
            json=_telegram_update("999003", "Ping"),
        )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock_delay.assert_called_once()


def test_webhook_rejects_bad_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "expected-secret")
    from app.config import get_settings

    get_settings.cache_clear()

    response = client.post(
        "/webhooks/telegram",
        json=_telegram_update("1", "Hi"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert response.status_code == 401
    get_settings.cache_clear()


def test_telegram_parse_inbound():
    from app.channels.telegram import TelegramChannel

    adapter = TelegramChannel(bot_token="test-token")
    inbound = adapter.parse_inbound(_telegram_update("42", "Hi"))
    assert inbound is not None
    assert inbound.chat_id == "42"
    assert inbound.text == "Hi"


def test_get_updates_raises_on_409_conflict():
    from app.channels.telegram import TelegramChannel, TelegramPollingConflictError

    adapter = TelegramChannel(bot_token="test-token")
    mock_response = MagicMock()
    mock_response.status_code = 409
    with patch("app.channels.telegram.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.get.return_value = mock_response
        with pytest.raises(TelegramPollingConflictError):
            adapter.get_updates()


@pytest.fixture
def test_user(db):
    from app.core.security import hash_password
    from app.models.user import User

    user = User(
        email="tg@example.com",
        hashed_password=hash_password("secret123"),
        full_name="TG User",
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
        data={"email": "tg@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    return client


def test_channels_ui_create_link(auth_client, db, researcher_agent):
    response = auth_client.post(
        "/channels",
        data={
            "agent_id": str(researcher_agent.id),
            "chat_id": "888777",
            "is_active": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith("/channels?")

    page = auth_client.get("/channels")
    assert page.status_code == 200
    assert "888777" in page.text
    assert "Researcher" in page.text


def test_process_telegram_task_eager(db, researcher_agent, demo_workflow, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.workers import tasks as worker_tasks
    from app.workers.celery_app import celery_app

    ChannelRepository(db).create(
        agent_id=researcher_agent.id,
        channel_type=CHANNEL_TYPE_TELEGRAM,
        config={"chat_id": "555444"},
    )

    worker_session = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())

    def open_test_db():
        return worker_session()

    monkeypatch.setattr(worker_tasks, "_open_worker_db", open_test_db)
    celery_app.conf.task_always_eager = True

    with patch(
        "app.services.channel_service.ChannelService.send_telegram_message",
        return_value={"ok": True},
    ):
        result = worker_tasks.process_telegram_update.apply(
            args=[_telegram_update("555444", "Worker hello")]
        ).get()

    assert result["ok"] is True
    assert result.get("run_id")
