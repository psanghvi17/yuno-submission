from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.workflow import Workflow
from app.models.workflow_run import (
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PENDING,
    RUN_STATUS_RUNNING,
    RUN_ACTIVE_STATUSES,
    WorkflowRun,
)
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.runtime.cancellation import RunCancelledError
from app.runtime.graph_builder import build_and_run_graph, build_demo_graph
from app.schemas.run import WorkflowRunDetail
from app.services.workflow_service import WorkflowNotFound, WorkflowService


class RunNotFound(Exception):
    pass


class RunExecutionError(Exception):
    pass


class RunCannotBeCancelled(Exception):
    pass


class RunService:
    def __init__(
        self,
        run_repo: RunRepository,
        workflow_repo: WorkflowRepository,
        agent_repo: AgentRepository,
    ) -> None:
        self.run_repo = run_repo
        self.workflow_repo = workflow_repo
        self.agent_repo = agent_repo

    def get_run(self, run_id: int) -> WorkflowRun:
        run = self.run_repo.get_run(run_id)
        if not run:
            raise RunNotFound(f"Run {run_id} not found")
        return run

    def get_run_detail(self, run_id: int) -> WorkflowRunDetail:
        run = self.get_run(run_id)
        return WorkflowRunDetail(
            id=run.id,
            workflow_id=run.workflow_id,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            error=run.error,
            triggered_by=run.triggered_by,
            cancel_requested=run.cancel_requested,
            created_at=run.created_at,
            messages=self.run_repo.list_messages(run.id),
            logs=self.run_repo.list_logs(run.id),
            usage=self.run_repo.list_usage(run.id),
            total_cost_usd=self.run_repo.total_cost(run.id),
        )

    def cancel_run(self, run_id: int) -> WorkflowRun:
        """Request cooperative stop for a pending or running workflow run."""
        run = self.get_run(run_id)
        if run.status not in RUN_ACTIVE_STATUSES:
            raise RunCannotBeCancelled(
                f"Run {run_id} cannot be stopped (status={run.status})"
            )
        if run.cancel_requested:
            return run

        self.run_repo.request_cancel(run)
        self.run_repo.add_log(
            run_id=run.id,
            level="warning",
            message="Stop requested by user",
        )
        return self.get_run(run.id)

    def enqueue_run(
        self,
        workflow_id: int,
        *,
        task_input: str = "Execute the workflow for the demo task.",
        triggered_by: str = "manual",
        mock_llm: bool | None = None,
        telegram_chat_id: str | None = None,
    ) -> WorkflowRun:
        """Create a pending run and dispatch execution to the Celery worker."""
        workflow = self.workflow_repo.get_by_id(workflow_id)
        if not workflow:
            raise WorkflowNotFound(f"Workflow {workflow_id} not found")

        use_mock = self._resolve_mock(mock_llm)
        run = self.run_repo.create_run(
            workflow_id=workflow_id,
            triggered_by=triggered_by,
        )
        queue_metadata: dict[str, Any] = {
            "workflow_id": workflow.id,
            "mock_llm": use_mock,
            "task_input": task_input,
        }
        if telegram_chat_id:
            queue_metadata["telegram_chat_id"] = str(telegram_chat_id).strip()
        self.run_repo.add_log(
            run_id=run.id,
            level="info",
            message=f"Run queued for workflow '{workflow.name}'",
            metadata=queue_metadata,
        )

        from app.workers.tasks import execute_workflow_run

        execute_workflow_run.apply_async(
            args=[run.id],
            kwargs={"task_input": task_input, "mock_llm": use_mock},
            throw=False,
        )
        return self.get_run(run.id)

    def enqueue_demo_two_agent_run(
        self,
        *,
        workflow_id: int | None = None,
        researcher_name: str = "Researcher",
        writer_name: str = "Writer",
        task_input: str = "Research AI agent orchestration and summarize findings.",
        triggered_by: str = "demo",
        mock_llm: bool | None = None,
    ) -> WorkflowRun:
        """Queue the hardcoded Researcher → Writer demo graph."""
        use_mock = self._resolve_mock(mock_llm)
        researcher = self.agent_repo.get_by_name(researcher_name)
        writer = self.agent_repo.get_by_name(writer_name)
        if not researcher or not writer:
            raise RunExecutionError(
                f"Demo agents not found ({researcher_name}, {writer_name}). "
                "Seed default agents first."
            )

        resolved_workflow_id = workflow_id
        if resolved_workflow_id is None:
            demo = self.workflow_repo.get_by_name(
                WorkflowService.DEMO_WORKFLOW_NAME,
                is_template=False,
            )
            resolved_workflow_id = demo.id if demo else None
        if resolved_workflow_id is None:
            raise RunExecutionError(
                "No workflow_id provided and demo workflow not found in database."
            )

        run = self.run_repo.create_run(
            workflow_id=resolved_workflow_id,
            triggered_by=triggered_by,
        )
        self.run_repo.add_log(
            run_id=run.id,
            level="info",
            message="Demo two-agent run queued",
            metadata={"mock_llm": use_mock, "task_input": task_input, "demo": True},
        )

        from app.workers.tasks import execute_workflow_run

        execute_workflow_run.apply_async(
            args=[run.id],
            kwargs={
                "task_input": task_input,
                "mock_llm": use_mock,
                "demo": True,
            },
            throw=False,
        )
        return self.get_run(run.id)

    def execute_run(
        self,
        run_id: int,
        *,
        task_input: str = "Execute the workflow for the demo task.",
        mock_llm: bool | None = None,
        demo: bool = False,
    ) -> WorkflowRun:
        """Execute an existing run (worker or synchronous CLI/tests)."""
        run = self.get_run(run_id)
        if run.status in (RUN_STATUS_COMPLETED, RUN_STATUS_FAILED, RUN_STATUS_CANCELLED):
            return run

        if self.run_repo.is_cancel_requested(run_id):
            self.run_repo.mark_cancelled(run)
            self.run_repo.add_log(
                run_id=run.id,
                level="warning",
                message="Run stopped before execution started",
            )
            return self.get_run(run.id)

        workflow = self.workflow_repo.get_by_id(run.workflow_id)
        if not workflow:
            self.run_repo.mark_failed(run, f"Workflow {run.workflow_id} not found")
            raise RunExecutionError(f"Workflow {run.workflow_id} not found")

        use_mock = self._resolve_mock(mock_llm)

        if run.status == RUN_STATUS_PENDING:
            self.run_repo.mark_running(run)
            self.run_repo.add_log(
                run_id=run.id,
                level="info",
                message=f"Run started for workflow '{workflow.name}'",
                metadata={"workflow_id": workflow.id, "mock_llm": use_mock},
            )

        try:
            if demo:
                self._execute_demo_graph(
                    run=run,
                    workflow=workflow,
                    task_input=task_input,
                    mock_llm=use_mock,
                )
            else:
                agents_by_node = self._agents_for_workflow(workflow)
                if not agents_by_node:
                    raise RunExecutionError("Workflow has no linked agent nodes")

                build_and_run_graph(
                    graph_json=workflow.graph_json or {"nodes": [], "edges": []},
                    agents_by_node=agents_by_node,
                    run_repo=self.run_repo,
                    run_id=run.id,
                    task_input=task_input,
                    mock_llm=use_mock,
                )

            self.run_repo.mark_completed(run)
            self.run_repo.add_log(
                run_id=run.id,
                level="info",
                message="Run completed successfully",
                metadata={"total_cost_usd": str(self.run_repo.total_cost(run.id))},
            )
        except RunCancelledError as exc:
            self.run_repo.mark_cancelled(run, reason=str(exc))
            self.run_repo.add_log(
                run_id=run.id,
                level="warning",
                message=str(exc),
            )
            return self.get_run(run.id)
        except Exception as exc:
            self.run_repo.mark_failed(run, str(exc))
            self.run_repo.add_log(
                run_id=run.id,
                level="error",
                message=f"Run failed: {exc}",
            )
            if run.triggered_by == "telegram":
                from app.services.channel_service import build_channel_service

                build_channel_service(self.run_repo.db).notify_telegram_run_failed(
                    run.id,
                    error=str(exc),
                )
            raise RunExecutionError(str(exc)) from exc

        return self.get_run(run.id)

    def start_run(
        self,
        workflow_id: int,
        *,
        task_input: str = "Execute the workflow for the demo task.",
        triggered_by: str = "manual",
        mock_llm: bool | None = None,
    ) -> WorkflowRun:
        """Synchronous run (CLI/tests) — creates run then executes inline."""
        workflow = self.workflow_repo.get_by_id(workflow_id)
        if not workflow:
            raise WorkflowNotFound(f"Workflow {workflow_id} not found")

        run = self.run_repo.create_run(
            workflow_id=workflow_id,
            triggered_by=triggered_by,
        )
        return self.execute_run(
            run.id,
            task_input=task_input,
            mock_llm=mock_llm,
        )

    def start_demo_two_agent_run(
        self,
        *,
        workflow_id: int | None = None,
        researcher_name: str = "Researcher",
        writer_name: str = "Writer",
        task_input: str = "Research AI agent orchestration and summarize findings.",
        triggered_by: str = "demo",
        mock_llm: bool | None = None,
    ) -> WorkflowRun:
        """Synchronous demo run (CLI/tests)."""
        use_mock = self._resolve_mock(mock_llm)
        researcher = self.agent_repo.get_by_name(researcher_name)
        writer = self.agent_repo.get_by_name(writer_name)
        if not researcher or not writer:
            raise RunExecutionError(
                f"Demo agents not found ({researcher_name}, {writer_name}). "
                "Seed default agents first."
            )

        resolved_workflow_id = workflow_id
        if resolved_workflow_id is None:
            demo = self.workflow_repo.get_by_name(
                WorkflowService.DEMO_WORKFLOW_NAME,
                is_template=False,
            )
            resolved_workflow_id = demo.id if demo else None
        if resolved_workflow_id is None:
            raise RunExecutionError(
                "No workflow_id provided and demo workflow not found in database."
            )

        run = self.run_repo.create_run(
            workflow_id=resolved_workflow_id,
            triggered_by=triggered_by,
        )
        return self.execute_run(
            run.id,
            task_input=task_input,
            mock_llm=use_mock,
            demo=True,
        )

    def _execute_demo_graph(
        self,
        *,
        run: WorkflowRun,
        workflow: Workflow,
        task_input: str,
        mock_llm: bool,
    ) -> None:
        researcher = self.agent_repo.get_by_name("Researcher")
        writer = self.agent_repo.get_by_name("Writer")
        if not researcher or not writer:
            raise RunExecutionError("Demo agents Researcher and Writer not found")

        graph = build_demo_graph(
            researcher=researcher,
            writer=writer,
            run_repo=self.run_repo,
            mock_llm=mock_llm,
        )
        app = graph.compile()
        app.invoke(
            {
                "messages": [],
                "run_id": run.id,
                "task_input": task_input,
                "node_outputs": {},
                "last_agent_node": None,
                "last_agent_id": None,
                "loop_counts": {},
                "pending_route": None,
            },
            config={"recursion_limit": 100},
        )

    def _agents_for_workflow(self, workflow: Workflow) -> dict[str, Agent]:
        agents_by_node: dict[str, Agent] = {}
        links = workflow.agent_links or []
        for link in links:
            agent = self.agent_repo.get_by_id(link.agent_id)
            if agent:
                agents_by_node[link.node_id] = agent

        graph_json = workflow.graph_json or {}
        nodes = graph_json.get("nodes") if isinstance(graph_json, dict) else []
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict) or node.get("type") != "agent":
                    continue
                node_id = str(node.get("id", "")).strip()
                if not node_id or node_id in agents_by_node:
                    continue
                agent_id = node.get("agent_id")
                if agent_id is not None:
                    agent = self.agent_repo.get_by_id(int(agent_id))
                    if agent:
                        agents_by_node[node_id] = agent
                        continue
                agent_name = node.get("agent_name")
                if agent_name:
                    agent = self.agent_repo.get_by_name(str(agent_name))
                    if agent:
                        agents_by_node[node_id] = agent
        return agents_by_node

    @staticmethod
    def _resolve_mock(mock_llm: bool | None) -> bool:
        from app.config import get_settings

        settings = get_settings()
        if mock_llm is not None:
            return mock_llm
        if settings.runtime_mock_llm:
            return True
        return not bool(settings.openai_api_key.strip())
