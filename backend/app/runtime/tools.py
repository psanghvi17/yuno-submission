import json
from pathlib import Path
from typing import Any

import httpx
from langchain_core.tools import tool

from app.config import get_settings
from app.runtime.dev_project import project_dir
from app.runtime.run_context import require_run_id

_TOOL_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "tool_outputs"
_DDG_TIMEOUT = 15.0


def _duckduckgo_search(query: str, *, max_results: int = 5) -> list[dict[str, str]]:
    """Query DuckDuckGo (no API key). Uses `ddgs` with fallback to `duckduckgo_search`."""
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        raw = list(ddgs.text(query, max_results=max_results))
    results: list[dict[str, str]] = []
    for item in raw:
        results.append(
            {
                "title": str(item.get("title") or ""),
                "snippet": str(item.get("body") or item.get("snippet") or ""),
                "url": str(item.get("href") or item.get("link") or ""),
            }
        )
    return results


def _duckduckgo_instant_answer(query: str) -> list[dict[str, str]]:
    """Fallback: DuckDuckGo Instant Answer API (no extra package, lighter results)."""
    with httpx.Client(timeout=_DDG_TIMEOUT) as client:
        response = client.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1,
            },
        )
        response.raise_for_status()
        data = response.json()
    results: list[dict[str, str]] = []
    abstract = (data.get("AbstractText") or "").strip()
    if abstract:
        results.append(
            {
                "title": data.get("Heading") or query,
                "snippet": abstract,
                "url": data.get("AbstractURL") or "",
            }
        )
    for topic in data.get("RelatedTopics") or []:
        if not isinstance(topic, dict):
            continue
        text = (topic.get("Text") or "").strip()
        if not text:
            continue
        results.append(
            {
                "title": text.split(" - ")[0][:120],
                "snippet": text,
                "url": str(topic.get("FirstURL") or ""),
            }
        )
        if len(results) >= 5:
            break
    return results


@tool
def web_search(query: str) -> str:
    """Search the web for information about a topic."""
    settings = get_settings()
    if settings.runtime_mock_tools:
        return json.dumps(
            {
                "query": query,
                "results": [
                    {
                        "title": "Sample result: AI orchestration trends",
                        "snippet": (
                            "Multi-agent workflows are increasingly used for research, "
                            "support triage, and content pipelines."
                        ),
                        "url": "https://example.com/ai-orchestration",
                    },
                    {
                        "title": "Sample result: LangGraph patterns",
                        "snippet": (
                            "StateGraph with agent nodes and conditional edges supports "
                            "loops and human-in-the-loop channels."
                        ),
                        "url": "https://example.com/langgraph",
                    },
                ],
                "source": "mock",
            },
            indent=2,
        )

    results: list[dict[str, str]] = []
    source = "duckduckgo"
    error: str | None = None
    try:
        results = _duckduckgo_search(query)
    except Exception as primary_exc:
        error = str(primary_exc)
        try:
            results = _duckduckgo_instant_answer(query)
            source = "duckduckgo_instant_answer"
        except Exception as fallback_exc:
            return json.dumps(
                {
                    "query": query,
                    "results": [],
                    "source": "error",
                    "error": error,
                    "fallback_error": str(fallback_exc),
                },
                indent=2,
            )

    return json.dumps(
        {
            "query": query,
            "results": results,
            "source": source,
            "result_count": len(results),
        },
        indent=2,
    )


@tool
def write_file(path: str, content: str) -> str:
    """Write text content to a file under the runtime data directory."""
    _TOOL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(path).name or "output.txt"
    target = _TOOL_OUTPUT_DIR / safe_name
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {target}"


@tool
def send_notification(message: str, channel: str = "telegram") -> str:
    """Send a notification to an external channel (Telegram when configured)."""
    from app.core.database import SessionLocal
    from app.services.channel_service import build_channel_service

    def _load_json(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _message_with_runtime_links(original: str) -> str:
        """
        Build deterministic notification text using real publish/deploy metadata
        so agent placeholders like [live URL] or yourusername are never sent.
        """
        text = (original or "").strip()
        try:
            run_id = require_run_id()
        except Exception:
            return text or original

        root = project_dir(run_id)
        publish = _load_json(root / ".orqestra_publish.json") or {}
        deploy = _load_json(root / ".orqestra_deploy.json") or {}
        live_url = str(deploy.get("url") or "").strip()
        health_url = str(deploy.get("health_url") or "").strip()
        repo_url = str(publish.get("html_url") or "").strip()
        repo_name = str(publish.get("full_name") or "").strip()

        if not live_url and not repo_url:
            # Prevent false-positive "live" notifications when publish/deploy failed.
            lower = text.lower()
            if "live" in lower or "deployed" in lower or "visit us" in lower:
                return (
                    "Deployment update: publish/deploy did not produce a live URL yet.\n"
                    "Check workflow logs for the exact failure and retry."
                )
            return text or original

        # Keep business phrase from model message when available.
        headline = "Website is live!"
        if "site is live" in text.lower():
            headline = text.split("site is live", 1)[0].strip() + " site is live!"
            headline = headline.replace("  ", " ").strip()

        lines = [headline]
        if live_url:
            lines.append(f"Live URL: {live_url}")
        if health_url:
            lines.append(f"Health Check: {health_url}")
        if repo_url:
            suffix = f" ({repo_name})" if repo_name else ""
            lines.append(f"GitHub Repo: {repo_url}{suffix}")
        return "\n".join(lines)

    final_message = _message_with_runtime_links(message)[:2000]
    settings = get_settings()
    payload = {"channel": channel, "message": final_message}
    if not settings.telegram_bot_token.strip():
        return json.dumps({"status": "queued", "payload": payload, "delivered": False})

    db = SessionLocal()
    try:
        service = build_channel_service(db)
        links = service.channel_repo.list_all()
        target = next(
            (
                link
                for link in links
                if link.channel_type == channel and link.is_active
            ),
            None,
        )
        if not target:
            return json.dumps(
                {"status": "skipped", "reason": "no_channel_link", "payload": payload}
            )
        chat_id = str((target.config or {}).get("chat_id", ""))
        if not chat_id:
            return json.dumps(
                {"status": "skipped", "reason": "missing_chat_id", "payload": payload}
            )
        result = service.send_telegram_message(chat_id, final_message)
        return json.dumps({"status": "sent", "payload": payload, "result": result})
    finally:
        db.close()


from app.runtime.dev_tools import DEV_TOOL_REGISTRY  # noqa: E402

TOOL_REGISTRY: dict[str, Any] = {
    "web_search": web_search,
    "write_file": write_file,
    "send_notification": send_notification,
    **DEV_TOOL_REGISTRY,
}


def registered_tool_names() -> list[str]:
    """Sorted tool names available for agent configuration."""
    return sorted(TOOL_REGISTRY.keys())


def tools_for_agent(tool_names: list[str]) -> list[Any]:
    selected = []
    for name in tool_names:
        tool_fn = TOOL_REGISTRY.get(name)
        if tool_fn is not None:
            selected.append(tool_fn)
    return selected
