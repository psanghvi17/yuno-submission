from collections import defaultdict, deque
from typing import Any

from langgraph.graph import END, StateGraph

from app.models.agent import Agent
from app.repositories.run_repository import RunRepository
from app.runtime.nodes import create_agent_node, create_channel_node, create_condition_node
from app.runtime.state import WorkflowGraphState


def build_demo_graph(
    *,
    researcher: Agent,
    writer: Agent,
    run_repo: RunRepository,
    mock_llm: bool,
) -> StateGraph:
    """Default 2-agent pipeline: Researcher → Writer."""
    graph_json = {
        "nodes": [
            {"id": "research", "type": "agent"},
            {"id": "writer", "type": "agent"},
        ],
        "edges": [{"from": "research", "to": "writer"}],
    }
    agents_by_node = {
        "research": researcher,
        "writer": writer,
    }
    return _compile_graph(
        graph_json=graph_json,
        agents_by_node=agents_by_node,
        run_repo=run_repo,
        mock_llm=mock_llm,
    )


def build_graph_from_workflow(
    *,
    graph_json: dict[str, Any],
    agents_by_node: dict[str, Agent],
    run_repo: RunRepository,
    mock_llm: bool,
) -> StateGraph:
    return _compile_graph(
        graph_json=graph_json,
        agents_by_node=agents_by_node,
        run_repo=run_repo,
        mock_llm=mock_llm,
    )


def build_and_run_graph(
    *,
    graph_json: dict[str, Any],
    agents_by_node: dict[str, Agent],
    run_repo: RunRepository,
    run_id: int,
    task_input: str,
    mock_llm: bool,
) -> WorkflowGraphState:
    workflow = _compile_graph(
        graph_json=graph_json,
        agents_by_node=agents_by_node,
        run_repo=run_repo,
        mock_llm=mock_llm,
    )
    app = workflow.compile()
    initial: WorkflowGraphState = {
        "messages": [],
        "run_id": run_id,
        "task_input": task_input,
        "node_outputs": {},
        "last_agent_node": None,
        "last_agent_id": None,
        "loop_counts": {},
        "pending_route": None,
    }
    return app.invoke(initial, config={"recursion_limit": 100})


def _compile_graph(
    *,
    graph_json: dict[str, Any],
    agents_by_node: dict[str, Agent],
    run_repo: RunRepository,
    mock_llm: bool,
) -> StateGraph:
    nodes = _normalize_nodes(graph_json)
    edges = _normalize_edges(graph_json)
    if not nodes:
        raise ValueError("Workflow graph has no nodes")

    node_by_id = {n["id"]: n for n in nodes}
    outgoing = _outgoing_map(edges)
    incoming = _incoming_map(edges)

    graph = StateGraph(WorkflowGraphState)
    entry = _pick_entry_node(nodes, incoming)

    agent_order = _linear_agent_chain(entry, node_by_id, outgoing)
    next_agent_by_node: dict[str, int | None] = {}
    for idx, node_id in enumerate(agent_order):
        next_id = agent_order[idx + 1] if idx + 1 < len(agent_order) else None
        next_agent = agents_by_node.get(next_id) if next_id else None
        next_agent_by_node[node_id] = next_agent.id if next_agent else None

    for node in nodes:
        node_id = node["id"]
        node_type = node.get("type", "agent")

        if node_type == "agent":
            agent = agents_by_node.get(node_id)
            if not agent:
                raise ValueError(f"Agent node '{node_id}' has no linked agent in the database")
            graph.add_node(
                node_id,
                create_agent_node(
                    node_id=node_id,
                    agent=agent,
                    run_repo=run_repo,
                    mock_llm=mock_llm,
                    next_agent_id=next_agent_by_node.get(node_id),
                ),
            )
        elif node_type == "channel":
            graph.add_node(
                node_id,
                create_channel_node(
                    node_id=node_id,
                    channel=str(node.get("channel", "internal")),
                    run_repo=run_repo,
                ),
            )
        elif node_type == "condition":
            branches = outgoing.get(node_id, [])
            low_branch = ok_branch = None
            max_loops = 3
            threshold = float(node.get("threshold", 0.7))
            field = str(node.get("field", "confidence"))
            for branch in branches:
                when = branch.get("when", "ok")
                if when == "low":
                    low_branch = branch["to"]
                    max_loops = int(branch.get("max_loops", max_loops))
                else:
                    ok_branch = branch["to"]
            if not ok_branch and branches:
                ok_branch = branches[0]["to"]
            if not low_branch and len(branches) > 1:
                low_branch = branches[1]["to"]
            if not ok_branch or not low_branch:
                raise ValueError(f"Condition node '{node_id}' needs ok and low branches")
            graph.add_node(
                node_id,
                create_condition_node(
                    node_id=node_id,
                    field=field,
                    threshold=threshold,
                    low_branch=low_branch,
                    ok_branch=ok_branch,
                    max_loops=max_loops,
                    run_repo=run_repo,
                ),
            )
        elif node_type == "end":
            graph.add_node(node_id, lambda state, nid=node_id: state)

    _wire_edges(graph, nodes, edges, node_by_id, outgoing, entry)

    return graph


def _wire_edges(
    graph: StateGraph,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]],
    entry: str,
) -> None:
    end_nodes = {n["id"] for n in nodes if n.get("type") == "end"}
    condition_nodes = {n["id"] for n in nodes if n.get("type") == "condition"}

    if entry and node_by_id.get(entry, {}).get("type") != "end":
        graph.set_entry_point(entry)

    for edge in edges:
        src = edge["from"]
        dst = edge["to"]
        when = edge.get("when")
        src_type = node_by_id.get(src, {}).get("type")

        if src in condition_nodes:
            continue
        if src_type == "condition":
            continue
        if when:
            continue

        if dst in end_nodes:
            graph.add_edge(src, END)
        elif src_type != "end":
            graph.add_edge(src, dst)

    for cond_id in condition_nodes:
        branches = outgoing.get(cond_id, [])
        mapping: dict[str, str] = {}
        low_branch = None
        ok_branch = None

        for branch in branches:
            target = branch["to"]
            when = branch.get("when", "ok")
            mapping[target] = target
            if when == "low":
                low_branch = target
            else:
                ok_branch = target

        if not ok_branch and branches:
            ok_branch = branches[0]["to"]
        if not low_branch and len(branches) > 1:
            low_branch = branches[1]["to"]

        if ok_branch and low_branch:
            graph.add_conditional_edges(
                cond_id,
                lambda state, _ok=ok_branch, _low=low_branch: (
                    state.get("pending_route") or _ok
                ),
                mapping,
            )

    nodes_without_outgoing = [
        n["id"]
        for n in nodes
        if n["id"] not in {e["from"] for e in edges}
        and n.get("type") not in ("end", "condition")
    ]
    for node_id in nodes_without_outgoing:
        if node_id not in condition_nodes:
            graph.add_edge(node_id, END)


def _normalize_nodes(graph_json: dict[str, Any]) -> list[dict[str, Any]]:
    raw = graph_json.get("nodes")
    if not isinstance(raw, list):
        return []
    normalized = []
    for node in raw:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", "")).strip()
        if not node_id:
            continue
        normalized.append({**node, "id": node_id})
    return normalized


def _normalize_edges(graph_json: dict[str, Any]) -> list[dict[str, Any]]:
    raw = graph_json.get("edges")
    if not isinstance(raw, list):
        return []
    edges = []
    for edge in raw:
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("from", "")).strip()
        dst = str(edge.get("to", "")).strip()
        if src and dst:
            edges.append({**edge, "from": src, "to": dst})
    return edges


def _outgoing_map(edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        result[edge["from"]].append(edge)
    return result


def _incoming_map(edges: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        result[edge["to"]].append(edge["from"])
    return result


def _pick_entry_node(
    nodes: list[dict[str, Any]],
    incoming: dict[str, list[str]],
) -> str:
    for node in nodes:
        if node["id"] not in incoming:
            return node["id"]
    return nodes[0]["id"] if nodes else ""


def _linear_agent_chain(
    entry: str,
    node_by_id: dict[str, dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]],
) -> list[str]:
    order: list[str] = []
    visited: set[str] = set()
    queue = deque([entry])
    while queue:
        node_id = queue.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)
        node = node_by_id.get(node_id)
        if node and node.get("type") == "agent":
            order.append(node_id)
        for edge in outgoing.get(node_id, []):
            if edge.get("when"):
                continue
            queue.append(edge["to"])
    return order
