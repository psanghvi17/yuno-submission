import pytest

from app.core.security import hash_password
from app.models.user import User


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_page(client):
    response = client.get("/auth/login")
    assert response.status_code == 200
    assert "Sign In" in response.text


def test_api_login_success(client, test_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "secret123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == "test@example.com"


def test_api_login_invalid_password(client, test_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


def test_api_me_requires_auth(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_api_me_after_login(client, test_user):
    client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "secret123"},
    )
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


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
