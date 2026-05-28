"""create workflow_runs, run_messages, run_logs, run_usage tables

Revision ID: 005
Revises: 004
Create Date: 2026-05-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.schema import APP_SCHEMA

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(length=128), nullable=False, server_default="manual"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            [f"{APP_SCHEMA}.workflows.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=APP_SCHEMA,
    )
    op.create_index(
        op.f("ix_app_workflow_runs_workflow_id"),
        "workflow_runs",
        ["workflow_id"],
        unique=False,
        schema=APP_SCHEMA,
    )
    op.create_index(
        op.f("ix_app_workflow_runs_status"),
        "workflow_runs",
        ["status"],
        unique=False,
        schema=APP_SCHEMA,
    )

    op.create_table(
        "run_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("from_agent_id", sa.Integer(), nullable=True),
        sa.Column("to_agent_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="assistant"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("channel", sa.String(length=64), nullable=False, server_default="internal"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{APP_SCHEMA}.workflow_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["from_agent_id"],
            [f"{APP_SCHEMA}.agents.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["to_agent_id"],
            [f"{APP_SCHEMA}.agents.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=APP_SCHEMA,
    )
    op.create_index(
        op.f("ix_app_run_messages_run_id"),
        "run_messages",
        ["run_id"],
        unique=False,
        schema=APP_SCHEMA,
    )

    op.create_table(
        "run_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{APP_SCHEMA}.workflow_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=APP_SCHEMA,
    )
    op.create_index(
        op.f("ix_app_run_logs_run_id"),
        "run_logs",
        ["run_id"],
        unique=False,
        schema=APP_SCHEMA,
    )

    op.create_table(
        "run_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{APP_SCHEMA}.workflow_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            [f"{APP_SCHEMA}.agents.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=APP_SCHEMA,
    )
    op.create_index(
        op.f("ix_app_run_usage_run_id"),
        "run_usage",
        ["run_id"],
        unique=False,
        schema=APP_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_app_run_usage_run_id"),
        table_name="run_usage",
        schema=APP_SCHEMA,
    )
    op.drop_table("run_usage", schema=APP_SCHEMA)
    op.drop_index(
        op.f("ix_app_run_logs_run_id"),
        table_name="run_logs",
        schema=APP_SCHEMA,
    )
    op.drop_table("run_logs", schema=APP_SCHEMA)
    op.drop_index(
        op.f("ix_app_run_messages_run_id"),
        table_name="run_messages",
        schema=APP_SCHEMA,
    )
    op.drop_table("run_messages", schema=APP_SCHEMA)
    op.drop_index(
        op.f("ix_app_workflow_runs_status"),
        table_name="workflow_runs",
        schema=APP_SCHEMA,
    )
    op.drop_index(
        op.f("ix_app_workflow_runs_workflow_id"),
        table_name="workflow_runs",
        schema=APP_SCHEMA,
    )
    op.drop_table("workflow_runs", schema=APP_SCHEMA)
