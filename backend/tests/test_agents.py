import json

import pytest

from app.core.security import hash_password
from app.models.user import User


@pytest.fixture
def test_user(db):
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


def _agent_payload(**overrides):
    base = {
        "name": "Test Agent",
        "role": "Tester",
        "system_prompt": "You are a test agent.",
        "model": "gpt-4o-mini",
        "tools": ["web_search"],
        "config": {"memory": {}, "schedule": {}, "guardrails": {"max_tokens": 1000}},
        "is_active": True,
    }
    base.update(overrides)
    return base


def test_api_agents_requires_auth(client):
    response = client.get("/api/v1/agents")
    assert response.status_code == 401


def test_api_create_list_get_update_delete(auth_client):
    create = auth_client.post("/api/v1/agents", json=_agent_payload())
    assert create.status_code == 201
    agent_id = create.json()["id"]
    assert create.json()["name"] == "Test Agent"
    assert create.json()["tools"] == ["web_search"]

    listing = auth_client.get("/api/v1/agents")
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    detail = auth_client.get(f"/api/v1/agents/{agent_id}")
    assert detail.status_code == 200
    assert detail.json()["role"] == "Tester"

    updated = auth_client.put(
        f"/api/v1/agents/{agent_id}",
        json={"name": "Updated Agent", "tools": []},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Agent"
    assert updated.json()["tools"] == []

    deleted = auth_client.delete(f"/api/v1/agents/{agent_id}")
    assert deleted.status_code == 204

    missing = auth_client.get(f"/api/v1/agents/{agent_id}")
    assert missing.status_code == 404


def test_api_create_duplicate_name(auth_client):
    auth_client.post("/api/v1/agents", json=_agent_payload())
    dup = auth_client.post("/api/v1/agents", json=_agent_payload(name="Test Agent"))
    assert dup.status_code == 422
    assert "name" in dup.json()["detail"]


def test_web_agents_list_requires_login(client):
    response = client.get("/agents", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login"


def test_web_create_and_list_agent(auth_client):
    create = auth_client.post(
        "/agents",
        data={
            "name": "Web Agent",
            "role": "Support",
            "system_prompt": "Help users.",
            "model": "gpt-4o-mini",
            "tools_raw": "web_search\nwrite_file",
            "config_raw": json.dumps({"memory": {}, "schedule": {}, "guardrails": {}}),
            "is_active": "true",
        },
        follow_redirects=False,
    )
    assert create.status_code == 302
    assert create.headers["location"].startswith("/agents/")

    listing = auth_client.get("/agents")
    assert listing.status_code == 200
    assert "Web Agent" in listing.text
    assert "web_search" in listing.text


def test_web_edit_and_delete_agent(auth_client):
    create = auth_client.post(
        "/api/v1/agents",
        json=_agent_payload(name="Lifecycle Agent"),
    )
    agent_id = create.json()["id"]

    edit_page = auth_client.get(f"/agents/{agent_id}")
    assert edit_page.status_code == 200
    assert "Lifecycle Agent" in edit_page.text

    update = auth_client.post(
        f"/agents/{agent_id}",
        data={
            "name": "Lifecycle Agent Updated",
            "role": "Updated role",
            "system_prompt": "Updated prompt",
            "model": "gpt-4o",
            "tools_raw": "",
            "config_raw": "{}",
            "is_active": "true",
        },
        follow_redirects=False,
    )
    assert update.status_code == 302

    listing = auth_client.get("/agents")
    assert "Lifecycle Agent Updated" in listing.text

    delete = auth_client.post(f"/agents/{agent_id}/delete", follow_redirects=False)
    assert delete.status_code == 302
    assert "flash=deleted" in delete.headers["location"]

    listing_after = auth_client.get("/agents")
    assert "Lifecycle Agent Updated" not in listing_after.text
