"""Cooperative cancellation checks for in-flight workflow runs."""

from __future__ import annotations

from app.repositories.run_repository import RunRepository


class RunCancelledError(Exception):
    """Raised when a run is stopped by the user."""


def ensure_run_not_cancelled(run_repo: RunRepository, run_id: int) -> None:
    """Read cancel flag from DB and abort the graph if the user requested stop."""
    if run_repo.is_cancel_requested(run_id):
        raise RunCancelledError("Workflow run stopped by user")
