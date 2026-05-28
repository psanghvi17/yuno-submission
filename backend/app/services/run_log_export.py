"""Plain-text export of workflow run logs and inter-agent messages."""

from app.schemas.run import RunLogRead, RunMessageRead, WorkflowRunDetail


def _ts(value) -> str:
    return str(value) if value is not None else "—"


def format_run_logs_export(
    *,
    run: WorkflowRunDetail,
    workflow_name: str,
) -> str:
    lines: list[str] = [
        "=" * 72,
        f"Workflow Run #{run.id}",
        "=" * 72,
        f"Workflow: {workflow_name}",
        f"Status: {run.status}",
        f"Triggered by: {run.triggered_by}",
        f"Created: {_ts(run.created_at)}",
        f"Started: {_ts(run.started_at)}",
        f"Finished: {_ts(run.finished_at)}",
        f"Total cost (USD): {run.total_cost_usd}",
    ]

    if run.error:
        lines.extend(
            [
                "",
                "=" * 72,
                "RUN ERROR",
                "=" * 72,
                run.error,
            ]
        )

    lines.extend(["", "=" * 72, "LOGS", "=" * 72])
    if run.logs:
        for log in run.logs:
            lines.append(_format_log_line(log))
    else:
        lines.append("(no logs)")

    lines.extend(["", "=" * 72, "INTER-AGENT MESSAGES", "=" * 72])
    if run.messages:
        for msg in run.messages:
            lines.extend(_format_message_block(msg))
            lines.append("-" * 72)
    else:
        lines.append("(no messages)")

    return "\n".join(lines).rstrip() + "\n"


def _format_log_line(log: RunLogRead) -> str:
    return f"[{log.level}] {_ts(log.created_at)}  {log.message}"


def _format_message_block(msg: RunMessageRead) -> list[str]:
    from_agent = msg.from_agent_id if msg.from_agent_id is not None else "—"
    to_agent = msg.to_agent_id if msg.to_agent_id is not None else "—"
    return [
        f"[{msg.role}] {_ts(msg.created_at)}",
        f"Agent {from_agent} → {to_agent} · channel: {msg.channel}",
        "",
        msg.content,
    ]
