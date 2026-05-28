from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password_reset_token
from app.models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self) -> list[User]:
        stmt = select(User).order_by(User.email.asc())
        return list(self.db.scalars(stmt).all())

    def list_paginated(self, *, offset: int, limit: int) -> list[User]:
        stmt = (
            select(User)
            .order_by(User.email.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower().strip())
        return self.db.scalars(stmt).first()

    def get_by_reset_token(self, plain_token: str) -> User | None:
        token_hash = hash_password_reset_token(plain_token)
        stmt = select(User).where(
            User.password_reset_token_hash == token_hash,
            User.password_reset_expires_at.isnot(None),
            User.password_reset_expires_at > func.now(),
        )
        return self.db.scalars(stmt).first()

    def count(self) -> int:
        stmt = select(func.count()).select_from(User)
        return int(self.db.scalar(stmt) or 0)

    def create(
        self,
        *,
        email: str,
        hashed_password: str,
        full_name: str = "",
        is_active: bool = True,
    ) -> User:
        user = User(
            email=email.lower().strip(),
            hashed_password=hashed_password,
            full_name=full_name,
            is_active=is_active,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update(self, user: User, **fields) -> User:
        for key, value in fields.items():
            setattr(user, key, value)
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, user: User) -> None:
        self.db.delete(user)
        self.db.commit()

    def set_password_reset_token(
        self,
        user: User,
        *,
        token_hash: str,
        expires_at: datetime,
    ) -> User:
        user.password_reset_token_hash = token_hash
        user.password_reset_expires_at = expires_at
        self.db.commit()
        self.db.refresh(user)
        return user

    def clear_password_reset_token(self, user: User) -> User:
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        self.db.commit()
        self.db.refresh(user)
        return user
