"""add password reset fields and updated_at to users

Revision ID: 004
Revises: 003
Create Date: 2026-05-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.schema import APP_SCHEMA

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_reset_token_hash", sa.String(length=64), nullable=True),
        schema=APP_SCHEMA,
    )
    op.add_column(
        "users",
        sa.Column("password_reset_expires_at", sa.DateTime(timezone=True), nullable=True),
        schema=APP_SCHEMA,
    )
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=APP_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("users", "updated_at", schema=APP_SCHEMA)
    op.drop_column("users", "password_reset_expires_at", schema=APP_SCHEMA)
    op.drop_column("users", "password_reset_token_hash", schema=APP_SCHEMA)
