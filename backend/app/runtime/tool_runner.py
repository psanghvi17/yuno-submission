"""Execute LangChain tool calls until the model returns a final text response."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from app.runtime.tools import TOOL_REGISTRY

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 8


def tool_iteration_limit_message(max_iterations: int) -> str:
    return (
        "Tool iteration limit reached. The agent stopped after "
        f"{max_iterations} tool rounds without a final answer."
    )


def ai_message_text(message: AIMessage) -> str:
    content = message.content
    if isinstance(content, list):
        text_parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(part for part in text_parts if part)
    return str(content)


def invoke_agent_llm(
    llm: BaseChatModel,
    messages: list[BaseMessage],
    *,
    tools: list[Any],
    mock_llm: bool,
    callbacks: list[Any] | None = None,
    on_tool_call: Callable[[str, dict[str, Any], str], None] | None = None,
    on_iteration_limit: Callable[[int], None] | None = None,
    max_iterations: int = MAX_TOOL_ITERATIONS,
) -> AIMessage:
    """Invoke the model; run tool_calls and feed ToolMessages back until done."""
    config = {"callbacks": callbacks} if callbacks else {}

    if mock_llm or not tools:
        response = llm.invoke(messages, config=config)
        if isinstance(response, AIMessage):
            return response
        return AIMessage(content=str(response))

    bound = llm.bind_tools(tools)
    conversation = list(messages)
    response: AIMessage | None = None

    for _ in range(max_iterations):
        response = bound.invoke(conversation, config=config)
        if not isinstance(response, AIMessage):
            return AIMessage(content=str(response))
        if not response.tool_calls:
            return response

        conversation.append(response)
        for tool_call in response.tool_calls:
            name = str(tool_call.get("name", ""))
            args = dict(tool_call.get("args") or {})
            tool_call_id = str(tool_call.get("id") or name)
            result = _execute_tool(name, args)
            if on_tool_call is not None:
                on_tool_call(name, args, result)
            conversation.append(
                ToolMessage(content=result, tool_call_id=tool_call_id)
            )

    logger.warning(
        "Tool iteration limit reached after %s iterations",
        max_iterations,
    )
    if on_iteration_limit is not None:
        on_iteration_limit(max_iterations)
    return AIMessage(content=tool_iteration_limit_message(max_iterations))


def _execute_tool(name: str, args: dict[str, Any]) -> str:
    tool_fn = TOOL_REGISTRY.get(name)
    if tool_fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return str(tool_fn.invoke(args))
    except Exception as exc:
        return json.dumps({"error": str(exc), "tool": name})
