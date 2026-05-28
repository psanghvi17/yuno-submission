"""add cancel_requested to workflow_runs

Revision ID: 008
Revises: 007
Create Date: 2026-05-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.schema import APP_SCHEMA

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema=APP_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("workflow_runs", "cancel_requested", schema=APP_SCHEMA)
