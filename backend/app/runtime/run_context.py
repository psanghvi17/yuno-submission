"""Per-run context for tools (run_id set during agent node execution)."""

from __future__ import annotations

from contextvars import ContextVar

current_run_id: ContextVar[int | None] = ContextVar("current_run_id", default=None)


def get_current_run_id() -> int | None:
    return current_run_id.get()


def require_run_id() -> int:
    run_id = get_current_run_id()
    if run_id is None:
        raise RuntimeError("No workflow run_id in tool context")
    return run_id
