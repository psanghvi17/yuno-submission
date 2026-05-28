import pytest

from app.core.security import hash_password
from app.models.user import User


@pytest.fixture
def test_user(db):
    user = User(
        email="admin@example.com",
        hashed_password=hash_password("secret123"),
        full_name="Admin User",
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
        data={"email": "admin@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    return client


def _user_payload(**overrides):
    base = {
        "email": "newuser@example.com",
        "password": "password123",
        "full_name": "New User",
        "is_active": True,
    }
    base.update(overrides)
    return base


def test_api_users_requires_auth(client):
    assert client.get("/api/v1/users").status_code == 401


def test_api_user_crud(auth_client):
    create = auth_client.post("/api/v1/users", json=_user_payload())
    assert create.status_code == 201
    user_id = create.json()["id"]

    listing = auth_client.get("/api/v1/users")
    assert listing.status_code == 200
    assert len(listing.json()) == 2

    update = auth_client.put(
        f"/api/v1/users/{user_id}",
        json={"full_name": "Updated Name"},
    )
    assert update.status_code == 200
    assert update.json()["full_name"] == "Updated Name"

    delete = auth_client.delete(f"/api/v1/users/{user_id}")
    assert delete.status_code == 204


def test_api_cannot_delete_self(auth_client, test_user):
    response = auth_client.delete(f"/api/v1/users/{test_user.id}")
    assert response.status_code == 422


def test_web_users_list_requires_login(client):
    response = client.get("/users", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login"


def test_web_create_user(auth_client):
    response = auth_client.post(
        "/users",
        data={
            "email": "webuser@example.com",
            "password": "password123",
            "password_confirm": "password123",
            "full_name": "Web User",
            "is_active": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    listing = auth_client.get("/users")
    assert "webuser@example.com" in listing.text
