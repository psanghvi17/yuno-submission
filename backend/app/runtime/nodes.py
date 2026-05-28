from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel

from app.models.agent import Agent
from app.repositories.run_repository import RunRepository
from app.runtime.cancellation import ensure_run_not_cancelled
from app.runtime.callbacks import UsageAccumulator, RunUsageCallbackHandler, estimate_cost_usd
from app.runtime.edges import evaluate_condition_branch
from app.runtime.run_context import current_run_id
from app.runtime.state import WorkflowGraphState
from app.runtime.tool_runner import ai_message_text, invoke_agent_llm
from app.runtime.tools import tools_for_agent


def create_llm_for_agent(agent: Agent, *, mock_llm: bool) -> BaseChatModel:
    from app.runtime.llm_factory import build_chat_model

    return build_chat_model(agent.model, mock=mock_llm)


def create_agent_node(
    *,
    node_id: str,
    agent: Agent,
    run_repo: RunRepository,
    mock_llm: bool,
    next_agent_id: int | None = None,
) -> Callable[[WorkflowGraphState], dict[str, Any]]:
    """Factory for a LangGraph node that runs one agent with optional tools."""

    def _node(state: WorkflowGraphState) -> dict[str, Any]:
        run_id = state["run_id"]
        # Make run_id available to tools (e.g. dev pipeline file tools)
        token = current_run_id.set(run_id)
        try:
            return _run_agent_node(state, run_id=run_id)
        finally:
            current_run_id.reset(token)

    def _run_agent_node(state: WorkflowGraphState, *, run_id: int) -> dict[str, Any]:
        ensure_run_not_cancelled(run_repo, run_id)
        task_input = state.get("task_input") or "Complete your part of the workflow."
        prior = _prior_context(state, node_id)

        run_repo.add_log(
            run_id=run_id,
            level="info",
            message=f"Agent node started: {agent.name} ({node_id})",
            metadata={"node_id": node_id, "agent_id": agent.id},
        )

        llm = create_llm_for_agent(agent, mock_llm=mock_llm)
        agent_tools = tools_for_agent(agent.tools if isinstance(agent.tools, list) else [])

        messages = [
            SystemMessage(content=agent.system_prompt or f"You are {agent.name}."),
            HumanMessage(
                content=(
                    f"Task (user brief — source of truth for business/domain):\n"
                    f"{task_input}\n\n"
                    f"Prior workflow context:\n{prior or '(none)'}\n\n"
                    "Respond with your findings or output for the next agent."
                )
            ),
        ]

        accumulator = UsageAccumulator()
        if mock_llm:
            accumulator.add(12, 24)

        def _log_tool(name: str, args: dict, result: str) -> None:
            run_repo.add_log(
                run_id=run_id,
                level="info",
                message=f"Tool executed: {name}",
                metadata={
                    "node_id": node_id,
                    "agent_id": agent.id,
                    "tool": name,
                    "args": args,
                    "result_preview": result[:500],
                },
            )

        def _log_tool_limit(iterations: int) -> None:
            run_repo.add_log(
                run_id=run_id,
                level="warning",
                message="Tool iteration limit reached",
                metadata={
                    "node_id": node_id,
                    "agent_id": agent.id,
                    "max_iterations": iterations,
                },
            )

        callbacks = None if mock_llm else [RunUsageCallbackHandler(accumulator)]
        response = invoke_agent_llm(
            llm,
            messages,
            tools=agent_tools,
            mock_llm=mock_llm,
            callbacks=callbacks,
            on_tool_call=None if mock_llm else _log_tool,
            on_iteration_limit=None if mock_llm else _log_tool_limit,
        )
        output_text = ai_message_text(response)

        run_repo.add_message(
            run_id=run_id,
            from_agent_id=agent.id,
            to_agent_id=next_agent_id,
            role="assistant",
            content=output_text,
            channel="internal",
        )
        if next_agent_id:
            run_repo.add_message(
                run_id=run_id,
                from_agent_id=agent.id,
                to_agent_id=next_agent_id,
                role="user",
                content=output_text,
                channel="handoff",
            )

        cost = estimate_cost_usd(
            prompt_tokens=accumulator.prompt_tokens,
            completion_tokens=accumulator.completion_tokens,
            mock=mock_llm,
        )
        run_repo.add_usage(
            run_id=run_id,
            agent_id=agent.id,
            prompt_tokens=accumulator.prompt_tokens,
            completion_tokens=accumulator.completion_tokens,
            cost_usd=cost,
        )
        run_repo.add_log(
            run_id=run_id,
            level="info",
            message=f"Agent node completed: {agent.name}",
            metadata={
                "node_id": node_id,
                "prompt_tokens": accumulator.prompt_tokens,
                "completion_tokens": accumulator.completion_tokens,
            },
        )

        node_outputs = dict(state.get("node_outputs") or {})
        node_outputs[node_id] = output_text

        return {
            "messages": [AIMessage(content=output_text, name=agent.name)],
            "node_outputs": node_outputs,
            "last_agent_node": node_id,
            "last_agent_id": agent.id,
        }

    return _node


def create_channel_node(
    *,
    node_id: str,
    channel: str,
    run_repo: RunRepository,
) -> Callable[[WorkflowGraphState], dict[str, Any]]:
    """Channel step (e.g. Telegram notify) — delivers when configured."""

    def _node(state: WorkflowGraphState) -> dict[str, Any]:
        run_id = state["run_id"]
        ensure_run_not_cancelled(run_repo, run_id)
        outputs = state.get("node_outputs") or {}
        summary = next(iter(outputs.values()), state.get("task_input", ""))
        text = str(summary)[:4000]
        agent_id = state.get("last_agent_id")

        run_repo.add_log(
            run_id=run_id,
            level="info",
            message=f"Channel notification ({channel})",
            metadata={"node_id": node_id, "channel": channel, "agent_id": agent_id},
        )

        from app.services.channel_service import build_channel_service

        channel_service = build_channel_service(run_repo.db)
        delivery = channel_service.deliver_workflow_notification(
            run_id=run_id,
            agent_id=agent_id,
            channel=channel,
            text=text,
        )
        payload = text if delivery.get("ok") else f"[{channel}] {text[:1500]}"
        run_repo.add_message(
            run_id=run_id,
            from_agent_id=agent_id,
            to_agent_id=None,
            role="assistant",
            content=payload,
            channel=channel,
        )
        node_outputs = dict(outputs)
        node_outputs[node_id] = payload
        return {
            "node_outputs": node_outputs,
            "last_agent_node": node_id,
            "last_agent_id": agent_id,
        }

    return _node


def create_condition_node(
    *,
    node_id: str,
    field: str = "confidence",
    threshold: float = 0.7,
    low_branch: str,
    ok_branch: str,
    max_loops: int = 3,
    run_repo: RunRepository,
) -> Callable[[WorkflowGraphState], dict[str, Any]]:
    """Evaluate a condition and persist loop counts + pending_route in state."""

    def _node(state: WorkflowGraphState) -> dict[str, Any]:
        ensure_run_not_cancelled(run_repo, state["run_id"])
        branch, loop_counts = evaluate_condition_branch(
            state,
            node_id=node_id,
            field=field,
            threshold=threshold,
            low_branch=low_branch,
            ok_branch=ok_branch,
            max_loops=max_loops,
        )
        run_repo.add_log(
            run_id=state["run_id"],
            level="info",
            message=f"Condition '{node_id}' → {branch}",
            metadata={
                "node_id": node_id,
                "branch": branch,
                "loop_counts": loop_counts,
            },
        )
        return {
            "loop_counts": loop_counts,
            "pending_route": branch,
        }

    return _node


def _prior_context(state: WorkflowGraphState, current_node_id: str) -> str:
    outputs = state.get("node_outputs") or {}
    parts = []
    for node_id, text in outputs.items():
        if node_id == current_node_id:
            continue
        if text:
            parts.append(f"[{node_id}]\n{text}")
    return "\n\n".join(parts)
