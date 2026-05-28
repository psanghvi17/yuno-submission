#!/usr/bin/env python3
"""Seed E2E pipeline agents/workflows and optionally queue a run.

Usage (from repository root):
  docker compose exec api python scripts/seed_e2e_demo.py
  docker compose exec api python scripts/seed_e2e_demo.py --run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as scripts/seed_e2e_demo.py inside the api container (/app).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.agent_service import AgentService
from app.services.run_service import RunService
from app.services.workflow_service import WorkflowService


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Product Launch E2E demo")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Enqueue a workflow run after seeding",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force mock LLM for the run",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        agent_service = AgentService(AgentRepository(db))
        agents = agent_service.seed_e2e_pipeline_agents()
        if agents:
            print("Created agents:", ", ".join(a.name for a in agents))
        else:
            print("E2E agents already exist")

        wf_service = WorkflowService(WorkflowRepository(db), AgentRepository(db))
        template = wf_service.seed_e2e_pipeline_template()
        if template:
            print(f"Created template: {template.name} (id={template.id})")
        runnable = wf_service.seed_e2e_run_workflow()
        if runnable:
            print(f"Created workflow: {runnable.name} (id={runnable.id})")
        else:
            existing = wf_service.workflow_repo.get_by_name(
                WorkflowService.E2E_RUN_WORKFLOW_NAME,
                is_template=False,
            )
            runnable = existing
            if runnable:
                print(f"Using existing workflow: {runnable.name} (id={runnable.id})")

        if args.run:
            if not runnable:
                print("No runnable E2E workflow found", file=sys.stderr)
                return 1
            run_service = RunService(
                RunRepository(db),
                WorkflowRepository(db),
                AgentRepository(db),
            )
            run = run_service.enqueue_run(
                runnable.id,
                task_input=WorkflowService.E2E_DEFAULT_TASK_INPUT,
                triggered_by="e2e_script",
                mock_llm=True if args.mock else None,
            )
            print(f"Queued run id={run.id} — open /runs/{run.id} in the UI")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
