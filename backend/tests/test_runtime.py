from copy import deepcopy

import pytest

from app.models.agent import Agent
from app.models.workflow import EMPTY_GRAPH_JSON, Workflow
from app.models.workflow_run import RUN_STATUS_COMPLETED, RUN_STATUS_FAILED
from app.repositories.agent_repository import AgentRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.run_service import RunExecutionError, RunService


def _seed_two_agent_workflow(db, researcher: Agent, writer: Agent) -> Workflow:
    graph_json = {
        "nodes": [
            {
                "id": "research",
                "type": "agent",
                "label": "Research",
                "agent_id": researcher.id,
            },
            {
                "id": "writer",
                "type": "agent",
                "label": "Writer",
                "agent_id": writer.id,
            },
        ],
        "edges": [{"from": "research", "to": "writer"}],
    }
    workflow = Workflow(
        name="Test Runtime Pipeline",
        description="Two-agent test workflow",
        graph_json=graph_json,
        version=1,
        is_template=False,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    from app.models.workflow import WorkflowAgent

    db.add(
        WorkflowAgent(
            workflow_id=workflow.id,
            agent_id=researcher.id,
            node_id="research",
        )
    )
    db.add(
        WorkflowAgent(
            workflow_id=workflow.id,
            agent_id=writer.id,
            node_id="writer",
        )
    )
    db.commit()
    db.refresh(workflow)
    return workflow


@pytest.fixture
def runtime_agents(db):
    repo = AgentRepository(db)
    researcher = repo.create(
        name="Researcher",
        role="research",
        system_prompt="You research topics.",
        model="gpt-4o-mini",
        tools=["web_search"],
        config={"memory": {}, "schedule": {}, "guardrails": {}},
        is_active=True,
    )
    writer = repo.create(
        name="Writer",
        role="write",
        system_prompt="You summarize research.",
        model="gpt-4o-mini",
        tools=[],
        config={"memory": {}, "schedule": {}, "guardrails": {}},
        is_active=True,
    )
    return researcher, writer


@pytest.fixture
def run_service(db):
    return RunService(
        RunRepository(db),
        WorkflowRepository(db),
        AgentRepository(db),
    )


def test_demo_two_agent_run_persists_messages(db, runtime_agents, run_service):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)

    run = run_service.start_demo_two_agent_run(
        workflow_id=workflow.id,
        mock_llm=True,
    )

    assert run.status == RUN_STATUS_COMPLETED
    detail = run_service.get_run_detail(run.id)
    assert len(detail.messages) >= 2
    assert len(detail.logs) >= 2
    assert len(detail.usage) >= 2
    assert detail.total_cost_usd == 0


def test_workflow_run_from_graph_json(db, runtime_agents, run_service):
    researcher, writer = runtime_agents
    workflow = _seed_two_agent_workflow(db, researcher, writer)

    run = run_service.start_run(workflow.id, mock_llm=True)

    assert run.status == RUN_STATUS_COMPLETED
    messages = run_service.run_repo.list_messages(run.id)
    assert any(m.from_agent_id == researcher.id for m in messages)
    assert any(m.from_agent_id == writer.id for m in messages)


def test_run_fails_without_agents(db, run_service):
    workflow_repo = WorkflowRepository(db)
    workflow = workflow_repo.create(
        name="Empty",
        description="",
        graph_json=deepcopy(EMPTY_GRAPH_JSON),
        version=1,
        is_template=False,
        agent_links=[],
    )

    with pytest.raises(RunExecutionError):
        run_service.start_run(workflow.id, mock_llm=True)

    run = run_service.run_repo.list_runs_for_workflow(workflow.id)[0]
    assert run.status == RUN_STATUS_FAILED
