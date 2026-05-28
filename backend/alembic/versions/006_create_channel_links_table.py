"""create channel_links table

Revision ID: 006
Revises: 005
Create Date: 2026-05-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.schema import APP_SCHEMA

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channel_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("channel_type", sa.String(length=64), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
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
        sa.ForeignKeyConstraint(
            ["agent_id"],
            [f"{APP_SCHEMA}.agents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=APP_SCHEMA,
    )
    op.create_index(
        op.f("ix_app_channel_links_agent_id"),
        "channel_links",
        ["agent_id"],
        unique=False,
        schema=APP_SCHEMA,
    )
    op.create_index(
        op.f("ix_app_channel_links_channel_type"),
        "channel_links",
        ["channel_type"],
        unique=False,
        schema=APP_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_app_channel_links_channel_type"),
        table_name="channel_links",
        schema=APP_SCHEMA,
    )
    op.drop_index(
        op.f("ix_app_channel_links_agent_id"),
        table_name="channel_links",
        schema=APP_SCHEMA,
    )
    op.drop_table("channel_links", schema=APP_SCHEMA)
