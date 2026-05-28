import json
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.config import get_settings
from app.runtime.tool_runner import invoke_agent_llm
from app.runtime.tools import registered_tool_names, web_search


def test_registered_tool_names_includes_core_and_dev_tools():
    names = registered_tool_names()
    assert names == sorted(names)
    for expected in (
        "web_search",
        "write_file",
        "send_notification",
        "init_dev_project",
        "list_project_files",
        "github_publish_project",
        "do_deploy_from_github",
    ):
        assert expected in names


def test_web_search_mock_returns_stub(monkeypatch):
    monkeypatch.setenv("RUNTIME_MOCK_TOOLS", "true")
    get_settings.cache_clear()
    result = json.loads(web_search.invoke({"query": "langgraph agents"}))
    assert result["source"] == "mock"
    assert len(result["results"]) >= 1


def test_web_search_live_uses_provider(monkeypatch):
    monkeypatch.setenv("RUNTIME_MOCK_TOOLS", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.runtime.tools._duckduckgo_search",
        lambda query, max_results=5: [
            {
                "title": "Test hit",
                "snippet": "Snippet text",
                "url": "https://example.com",
            }
        ],
    )
    result = json.loads(web_search.invoke({"query": "orchestration"}))
    assert result["source"] == "duckduckgo"
    assert result["results"][0]["title"] == "Test hit"


def test_invoke_agent_llm_executes_tool_calls():
    tool_calls_log: list[str] = []

    bound = MagicMock()
    bound.invoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "web_search",
                    "args": {"query": "ai agents"},
                    "id": "call-1",
                }
            ],
        ),
        AIMessage(content="Summary based on search results."),
    ]

    llm = MagicMock()
    llm.bind_tools.return_value = bound

    def on_tool(name: str, args: dict, result: str) -> None:
        tool_calls_log.append(name)

    response = invoke_agent_llm(
        llm,
        [HumanMessage(content="Research AI agents")],
        tools=[web_search],
        mock_llm=False,
        on_tool_call=on_tool,
    )

    assert bound.invoke.call_count == 2
    assert tool_calls_log == ["web_search"]
    assert response.content == "Summary based on search results."


def test_invoke_agent_llm_reports_iteration_limit():
    bound = MagicMock()
    bound.invoke.return_value = AIMessage(
        content="",
        tool_calls=[
            {"name": "web_search", "args": {"query": "loop"}, "id": "call-loop"},
        ],
    )
    llm = MagicMock()
    llm.bind_tools.return_value = bound

    limits: list[int] = []

    response = invoke_agent_llm(
        llm,
        [HumanMessage(content="Keep searching")],
        tools=[web_search],
        mock_llm=False,
        max_iterations=2,
        on_iteration_limit=limits.append,
    )

    assert bound.invoke.call_count == 2
    assert limits == [2]
    assert "Tool iteration limit reached" in str(response.content)
