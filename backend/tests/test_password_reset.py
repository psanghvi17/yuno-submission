from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import (
    generate_password_reset_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository


@pytest.fixture
def test_user(db):
    user = User(
        email="reset@example.com",
        hashed_password=hash_password("oldpassword"),
        full_name="Reset User",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_forgot_password_page(client):
    response = client.get("/auth/forgot-password")
    assert response.status_code == 200
    assert "Forgot password" in response.text


def test_password_reset_flow(client, test_user, db, monkeypatch):
    sent: list[dict] = []

    def fake_send(self, *, to_email, reset_url):
        sent.append({"to": to_email, "url": reset_url})

    monkeypatch.setattr(
        "app.services.email_service.EmailService.send_password_reset",
        fake_send,
    )

    response = client.post(
        "/auth/forgot-password",
        data={"email": "reset@example.com"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "flash=sent" in response.headers["location"]
    assert len(sent) == 1
    assert "token=" in sent[0]["url"]

    plain_token = sent[0]["url"].split("token=")[1]
    reset_page = client.get(f"/auth/reset-password?token={plain_token}")
    assert reset_page.status_code == 200

    submit = client.post(
        "/auth/reset-password",
        data={
            "token": plain_token,
            "password": "newpassword123",
            "password_confirm": "newpassword123",
        },
        follow_redirects=False,
    )
    assert submit.status_code == 302
    assert submit.headers["location"] == "/auth/login?flash=password_reset"

    db.refresh(test_user)
    assert verify_password("newpassword123", test_user.hashed_password)
    assert test_user.password_reset_token_hash is None

    login = client.post(
        "/auth/login",
        data={"email": "reset@example.com", "password": "newpassword123"},
        follow_redirects=False,
    )
    assert login.status_code == 302
    assert login.headers["location"] == "/dashboard"


def test_reset_token_expired(client, test_user, db):
    plain, token_hash = generate_password_reset_token()
    repo = UserRepository(db)
    repo.set_password_reset_token(
        test_user,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    response = client.post(
        "/auth/reset-password",
        data={
            "token": plain,
            "password": "newpassword123",
            "password_confirm": "newpassword123",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "invalid_token" in response.headers["location"]
