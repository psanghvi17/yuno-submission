"""create app schema and users table

Revision ID: 001
Revises:
Create Date: 2026-05-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.schema import APP_SCHEMA

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{APP_SCHEMA}"')

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=APP_SCHEMA,
    )
    op.create_index(
        op.f("ix_app_users_email"),
        "users",
        ["email"],
        unique=True,
        schema=APP_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_app_users_email"),
        table_name="users",
        schema=APP_SCHEMA,
    )
    op.drop_table("users", schema=APP_SCHEMA)
    op.execute(f'DROP SCHEMA IF EXISTS "{APP_SCHEMA}" CASCADE')
