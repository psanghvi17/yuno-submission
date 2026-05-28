from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class WorkflowGraphState(TypedDict):
    """LangGraph state passed between agent nodes."""

    messages: Annotated[list[BaseMessage], add_messages]
    run_id: int
    task_input: str
    node_outputs: dict[str, str]
    last_agent_node: str | None
    last_agent_id: int | None
    loop_counts: dict[str, int]
    pending_route: str | None
