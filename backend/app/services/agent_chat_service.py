from langchain_core.messages import HumanMessage, SystemMessage

from app.models.agent import Agent
from app.repositories.run_repository import RunRepository
from app.runtime.callbacks import UsageAccumulator, RunUsageCallbackHandler, estimate_cost_usd
from app.runtime.nodes import create_llm_for_agent
from app.runtime.tool_runner import ai_message_text, invoke_agent_llm
from app.runtime.tools import tools_for_agent
from app.services.run_service import RunService


class AgentChatService:
    """Single-turn agent reply for human channels (e.g. Telegram)."""

    def __init__(self, run_repo: RunRepository) -> None:
        self.run_repo = run_repo

    def generate_reply(
        self,
        *,
        agent: Agent,
        user_message: str,
        run_id: int,
        mock_llm: bool | None = None,
    ) -> str:
        use_mock = RunService._resolve_mock(mock_llm)

        self.run_repo.add_message(
            run_id=run_id,
            from_agent_id=None,
            to_agent_id=agent.id,
            role="user",
            content=user_message,
            channel="telegram",
        )
        self.run_repo.add_log(
            run_id=run_id,
            level="info",
            message=f"Telegram message received for agent {agent.name}",
            metadata={"agent_id": agent.id},
        )

        llm = create_llm_for_agent(agent, mock_llm=use_mock)
        agent_tools = tools_for_agent(agent.tools if isinstance(agent.tools, list) else [])

        messages = [
            SystemMessage(
                content=(
                    agent.system_prompt
                    or f"You are {agent.name}, a helpful assistant."
                )
            ),
            HumanMessage(content=user_message),
        ]

        accumulator = UsageAccumulator()
        if use_mock:
            accumulator.add(8, 16)

        def _log_tool(name: str, args: dict, result: str) -> None:
            self.run_repo.add_log(
                run_id=run_id,
                level="info",
                message=f"Tool executed: {name}",
                metadata={
                    "agent_id": agent.id,
                    "tool": name,
                    "args": args,
                    "result_preview": result[:500],
                },
            )

        def _log_tool_limit(iterations: int) -> None:
            self.run_repo.add_log(
                run_id=run_id,
                level="warning",
                message="Tool iteration limit reached",
                metadata={"agent_id": agent.id, "max_iterations": iterations},
            )

        callbacks = None if use_mock else [RunUsageCallbackHandler(accumulator)]
        response = invoke_agent_llm(
            llm,
            messages,
            tools=agent_tools,
            mock_llm=use_mock,
            callbacks=callbacks,
            on_tool_call=None if use_mock else _log_tool,
            on_iteration_limit=None if use_mock else _log_tool_limit,
        )
        reply = ai_message_text(response)

        self.run_repo.add_message(
            run_id=run_id,
            from_agent_id=agent.id,
            to_agent_id=None,
            role="assistant",
            content=reply,
            channel="telegram",
        )
        cost = estimate_cost_usd(
            prompt_tokens=accumulator.prompt_tokens,
            completion_tokens=accumulator.completion_tokens,
            mock=use_mock,
        )
        self.run_repo.add_usage(
            run_id=run_id,
            agent_id=agent.id,
            prompt_tokens=accumulator.prompt_tokens,
            completion_tokens=accumulator.completion_tokens,
            cost_usd=cost,
        )
        self.run_repo.add_log(
            run_id=run_id,
            level="info",
            message=f"Telegram reply sent by agent {agent.name}",
            metadata={"agent_id": agent.id, "mock_llm": use_mock},
        )
        return reply
