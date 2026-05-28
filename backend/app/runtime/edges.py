import json
import re

from app.runtime.state import WorkflowGraphState


def _extract_confidence(text: str) -> float | None:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "confidence" in parsed:
            return float(parsed["confidence"])
    except json.JSONDecodeError:
        pass
    match = re.search(r"confidence[\"']?\s*[:=]\s*([0-9.]+)", text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _extract_bool_field(text: str, field: str) -> bool | None:
    """Extract a boolean field (e.g. approved, tests_passed) from JSON or plain text."""
    # Try JSON first — agent should output a JSON block
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and field in parsed:
                val = parsed[field]
                if isinstance(val, bool):
                    return val
                if isinstance(val, str):
                    return val.lower() in ("true", "yes", "1", "pass", "passed")
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: regex in surrounding text
    pattern = rf'["\']?{re.escape(field)}["\']?\s*[:=]\s*(true|false|yes|no|pass(?:ed)?|fail(?:ed)?)'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).lower() in ("true", "yes", "pass", "passed")
    return None


def _json_candidates(text: str) -> list[str]:
    """Return plausible JSON substrings from text (fenced or bare objects)."""
    candidates: list[str] = []
    # fenced code block: ```json ... ```
    for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL):
        candidates.append(m.group(1))
    # bare top-level object at end
    for m in re.finditer(r"\{[^{}]*\}", text, re.DOTALL):
        candidates.append(m.group(0))
    return candidates


def evaluate_condition_branch(
    state: WorkflowGraphState,
    *,
    node_id: str,
    field: str = "confidence",
    threshold: float = 0.7,
    low_branch: str,
    ok_branch: str,
    max_loops: int = 3,
) -> tuple[str, dict[str, int]]:
    """Pick the next branch and return updated loop_counts for persistence.

    Supports three field types:
    - ``confidence`` (float 0-1, compared against threshold)
    - ``approved`` (bool — Reviewer agent)
    - ``tests_passed`` (bool — Tester agent)
    """
    last_node = state.get("last_agent_node") or ""
    outputs = state.get("node_outputs") or {}
    text = outputs.get(last_node, "")
    loop_counts = dict(state.get("loop_counts") or {})
    loop_key = f"{node_id}:low"
    current_loops = loop_counts.get(loop_key, 0)

    # Boolean fields (approved, tests_passed)
    if field in ("approved", "tests_passed"):
        ok = _extract_bool_field(text, field)
        if ok is None:
            # No parseable value → assume ok so pipeline doesn't loop forever
            ok = True
        if ok or current_loops >= max_loops:
            return ok_branch, loop_counts
        loop_counts[loop_key] = current_loops + 1
        return low_branch, loop_counts

    # Confidence float field (existing behaviour)
    confidence = _extract_confidence(text) if field == "confidence" else None
    if confidence is None:
        confidence = 0.85 if "high confidence" in text.lower() else 0.5

    if confidence >= threshold:
        return ok_branch, loop_counts

    if current_loops >= max_loops:
        return ok_branch, loop_counts

    loop_counts[loop_key] = current_loops + 1
    return low_branch, loop_counts


def route_condition(
    state: WorkflowGraphState,
    *,
    field: str = "confidence",
    threshold: float = 0.7,
    low_branch: str,
    ok_branch: str,
    max_loops: int = 3,
) -> str:
    """Legacy router — prefer evaluate_condition_branch + pending_route."""
    branch, _ = evaluate_condition_branch(
        state,
        node_id="legacy",
        field=field,
        threshold=threshold,
        low_branch=low_branch,
        ok_branch=ok_branch,
        max_loops=max_loops,
    )
    return branch
