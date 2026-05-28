"""create workflows and workflow_agents tables

Revision ID: 003
Revises: 002
Create Date: 2026-05-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.schema import APP_SCHEMA

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "graph_json",
            sa.JSON(),
            nullable=False,
            server_default='{"nodes": [], "edges": []}',
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_template", sa.Boolean(), nullable=False, server_default="false"),
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
        op.f("ix_app_workflows_name"),
        "workflows",
        ["name"],
        unique=False,
        schema=APP_SCHEMA,
    )
    op.create_index(
        op.f("ix_app_workflows_is_template"),
        "workflows",
        ["is_template"],
        unique=False,
        schema=APP_SCHEMA,
    )

    op.create_table(
        "workflow_agents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            [f"{APP_SCHEMA}.workflows.id"],
            ondelete="CASCADE",
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
        op.f("ix_app_workflow_agents_workflow_id"),
        "workflow_agents",
        ["workflow_id"],
        unique=False,
        schema=APP_SCHEMA,
    )
    op.create_index(
        op.f("ix_app_workflow_agents_agent_id"),
        "workflow_agents",
        ["agent_id"],
        unique=False,
        schema=APP_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_app_workflow_agents_agent_id"),
        table_name="workflow_agents",
        schema=APP_SCHEMA,
    )
    op.drop_index(
        op.f("ix_app_workflow_agents_workflow_id"),
        table_name="workflow_agents",
        schema=APP_SCHEMA,
    )
    op.drop_table("workflow_agents", schema=APP_SCHEMA)
    op.drop_index(
        op.f("ix_app_workflows_is_template"),
        table_name="workflows",
        schema=APP_SCHEMA,
    )
    op.drop_index(
        op.f("ix_app_workflows_name"),
        table_name="workflows",
        schema=APP_SCHEMA,
    )
    op.drop_table("workflows", schema=APP_SCHEMA)
