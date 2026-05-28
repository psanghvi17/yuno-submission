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


def test_web_login_redirects_to_dashboard(client, test_user):
    response = client.post(
        "/auth/login",
        data={"email": "test@example.com", "password": "secret123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    assert response.cookies


def test_web_dashboard_requires_login(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login"


def test_web_dashboard_after_form_login(client, test_user):
    client.post(
        "/auth/login",
        data={"email": "test@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "test@example.com" in response.text


def test_web_logout_clears_session(client, test_user):
    client.post(
        "/auth/login",
        data={"email": "test@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    logout = client.post("/auth/logout", follow_redirects=False)
    assert logout.status_code == 302
    assert logout.headers["location"] == "/auth/login"

    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login"


def test_web_login_invalid_email(client):
    response = client.post(
        "/auth/login",
        data={"email": "not-an-email", "password": "secret123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=invalid_email" in response.headers["location"]


def test_web_login_invalid_credentials(client, test_user):
    response = client.post(
        "/auth/login",
        data={"email": "test@example.com", "password": "wrong"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=invalid_credentials" in response.headers["location"]


def test_inactive_user_session_cleared(client, test_user, db):
    client.post(
        "/auth/login",
        data={"email": "test@example.com", "password": "secret123"},
        follow_redirects=True,
    )

    test_user.is_active = False
    db.commit()

    dashboard = client.get("/dashboard", follow_redirects=False)
    assert dashboard.status_code == 302
    assert dashboard.headers["location"] == "/auth/login"

    login_page = client.get("/auth/login", follow_redirects=False)
    assert login_page.status_code == 200
    assert "Sign In" in login_page.text
