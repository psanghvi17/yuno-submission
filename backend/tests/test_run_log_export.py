"""Tests for run log download export."""

from datetime import datetime, timezone
from decimal import Decimal

from app.schemas.run import RunLogRead, RunMessageRead, WorkflowRunDetail
from app.services.run_log_export import format_run_logs_export


def _run_detail(**overrides) -> WorkflowRunDetail:
    now = datetime.now(timezone.utc)
    base = {
        "id": 6,
        "workflow_id": 1,
        "status": "completed",
        "started_at": now,
        "finished_at": now,
        "error": None,
        "triggered_by": "ui",
        "created_at": now,
        "messages": [],
        "logs": [],
        "usage": [],
        "total_cost_usd": Decimal("0.000195"),
    }
    base.update(overrides)
    return WorkflowRunDetail(**base)


def test_export_includes_logs_messages_and_error():
    now = datetime.now(timezone.utc)
    detail = _run_detail(
        status="failed",
        error="CapRover connection refused",
        logs=[
            RunLogRead(
                id=1,
                run_id=6,
                level="info",
                message="Run started",
                log_metadata={},
                created_at=now,
            ),
            RunLogRead(
                id=2,
                run_id=6,
                level="error",
                message="Run failed: timeout",
                log_metadata={},
                created_at=now,
            ),
        ],
        messages=[
            RunMessageRead(
                id=1,
                run_id=6,
                from_agent_id=1,
                to_agent_id=None,
                role="assistant",
                content="Listed apps on CapRover.",
                channel="internal",
                created_at=now,
            ),
        ],
    )

    text = format_run_logs_export(run=detail, workflow_name="CapRover Ops")

    assert "Workflow Run #6" in text
    assert "CapRover Ops" in text
    assert "RUN ERROR" in text
    assert "CapRover connection refused" in text
    assert "[info]" in text
    assert "Run started" in text
    assert "[error]" in text
    assert "Run failed: timeout" in text
    assert "INTER-AGENT MESSAGES" in text
    assert "Listed apps on CapRover." in text
    assert "[assistant]" in text
