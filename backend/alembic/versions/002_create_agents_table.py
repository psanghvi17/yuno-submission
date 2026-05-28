"""create agents table

Revision ID: 002
Revises: 001
Create Date: 2026-05-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.schema import APP_SCHEMA

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("system_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "model",
            sa.String(length=128),
            nullable=False,
            server_default="gpt-4o-mini",
        ),
        sa.Column("tools", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "config",
            sa.JSON(),
            nullable=False,
            server_default='{"memory": {}, "schedule": {}, "guardrails": {}}',
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=APP_SCHEMA,
    )
    op.create_index(
        op.f("ix_app_agents_name"),
        "agents",
        ["name"],
        unique=False,
        schema=APP_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_app_agents_name"),
        table_name="agents",
        schema=APP_SCHEMA,
    )
    op.drop_table("agents", schema=APP_SCHEMA)
