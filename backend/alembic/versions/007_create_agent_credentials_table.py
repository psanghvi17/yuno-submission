"""create agent_credentials table

Revision ID: 007
Revises: 006
Create Date: 2026-05-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.schema import APP_SCHEMA

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("credential_type", sa.String(length=64), nullable=False),
        sa.Column("vault_path", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
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
        sa.ForeignKeyConstraint(
            ["agent_id"],
            [f"{APP_SCHEMA}.agents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "slug", name="uq_agent_credentials_agent_slug"),
        schema=APP_SCHEMA,
    )
    op.create_index(
        op.f("ix_app_agent_credentials_agent_id"),
        "agent_credentials",
        ["agent_id"],
        unique=False,
        schema=APP_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_app_agent_credentials_agent_id"),
        table_name="agent_credentials",
        schema=APP_SCHEMA,
    )
    op.drop_table("agent_credentials", schema=APP_SCHEMA)
