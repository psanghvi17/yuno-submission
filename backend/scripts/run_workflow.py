#!/usr/bin/env python3
"""CLI to execute a workflow run synchronously (bypasses Celery queue)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.run_service import RunExecutionError, RunService


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a workflow run via LangGraph")
    parser.add_argument("--workflow-id", type=int, help="Workflow ID to execute")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run hardcoded Researcher → Writer demo graph",
    )
    parser.add_argument(
        "--task",
        default="Execute the workflow for the demo task.",
        help="Task input passed to the first agent",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force mock LLM (no OpenAI calls)",
    )
    parser.add_argument(
        "--no-mock",
        action="store_true",
        help="Force real OpenAI (requires OPENAI_API_KEY)",
    )
    args = parser.parse_args()

    if not args.demo and args.workflow_id is None:
        parser.error("Provide --workflow-id or --demo")

    mock_llm = True
    if args.no_mock:
        mock_llm = False
    elif args.mock:
        mock_llm = True

    db = SessionLocal()
    try:
        service = RunService(
            RunRepository(db),
            WorkflowRepository(db),
            AgentRepository(db),
        )
        if args.demo:
            run = service.start_demo_two_agent_run(
                task_input=args.task,
                triggered_by="cli",
                mock_llm=mock_llm,
            )
        else:
            run = service.start_run(
                args.workflow_id,
                task_input=args.task,
                triggered_by="cli",
                mock_llm=mock_llm,
            )

        detail = service.get_run_detail(run.id)
        print(f"Run {detail.id} status={detail.status} workflow_id={detail.workflow_id}")
        print(f"Messages: {len(detail.messages)}  Logs: {len(detail.logs)}  Cost: ${detail.total_cost_usd}")
        for msg in detail.messages:
            preview = (msg.content[:120] + "…") if len(msg.content) > 120 else msg.content
            print(f"  [{msg.role}] agent {msg.from_agent_id} → {msg.to_agent_id}: {preview}")
        return 0 if detail.status == "completed" else 1
    except RunExecutionError as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
