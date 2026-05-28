from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.core.security import (
    generate_password_reset_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.email_service import EmailService


class AuthService:
    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.user_repo.get_by_email(email)
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def ensure_admin_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
    ) -> User | None:
        """Create the default admin when the database has no users."""
        if self.user_repo.count() > 0:
            return None
        return self.user_repo.create(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
        )

    def request_password_reset(self, email: str) -> None:
        """Issue reset token and email link. No-op if user unknown (anti-enumeration)."""
        user = self.user_repo.get_by_email(email)
        if not user or not user.is_active:
            return

        settings = get_settings()
        plain_token, token_hash = generate_password_reset_token()
        expires_at = datetime.now(UTC) + timedelta(
            hours=settings.password_reset_token_hours
        )
        self.user_repo.set_password_reset_token(
            user,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        reset_url = (
            f"{settings.app_base_url.rstrip('/')}/auth/reset-password"
            f"?token={plain_token}"
        )
        EmailService().send_password_reset(to_email=user.email, reset_url=reset_url)

    def reset_password_with_token(self, plain_token: str, new_password: str) -> bool:
        if len(new_password) < 8:
            return False

        user = self.user_repo.get_by_reset_token(plain_token)
        if not user or not user.is_active:
            return False

        self.user_repo.update(
            user,
            hashed_password=hash_password(new_password),
        )
        self.user_repo.clear_password_reset_token(user)
        return True
