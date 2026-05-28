import pytest

from app.core.security import hash_password
from app.models.user import User
from app.services.agent_service import AgentService
from app.repositories.agent_repository import AgentRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.workflow_service import WorkflowService


@pytest.fixture
def test_user(db):
    user = User(
        email="test@example.com",
        hashed_password=hash_password("secret123"),
        full_name="Test User",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_client(client, test_user):
    client.post(
        "/auth/login",
        data={"email": "test@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    return client


@pytest.fixture
def seeded_agents(db):
    service = AgentService(AgentRepository(db))
    return service.seed_default_agents()


def _workflow_payload(**overrides):
    base = {
        "name": "Test Workflow",
        "description": "A test workflow",
        "graph_json": {
            "nodes": [{"id": "a", "type": "agent", "label": "Agent A"}],
            "edges": [],
        },
        "version": 1,
        "is_template": False,
        "agent_links": [],
    }
    base.update(overrides)
    return base


def test_api_workflows_requires_auth(client):
    response = client.get("/api/v1/workflows")
    assert response.status_code == 401


def test_api_create_list_get_update_delete(auth_client):
    create = auth_client.post("/api/v1/workflows", json=_workflow_payload())
    assert create.status_code == 201
    workflow_id = create.json()["id"]
    assert create.json()["name"] == "Test Workflow"
    assert len(create.json()["graph_json"]["nodes"]) == 1

    listing = auth_client.get("/api/v1/workflows")
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    detail = auth_client.get(f"/api/v1/workflows/{workflow_id}")
    assert detail.status_code == 200
    assert detail.json()["description"] == "A test workflow"

    updated = auth_client.put(
        f"/api/v1/workflows/{workflow_id}",
        json={"name": "Updated Workflow"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Workflow"

    deleted = auth_client.delete(f"/api/v1/workflows/{workflow_id}")
    assert deleted.status_code == 204

    missing = auth_client.get(f"/api/v1/workflows/{workflow_id}")
    assert missing.status_code == 404


def test_seed_templates_and_duplicate(auth_client, db, seeded_agents):
    assert len(seeded_agents) == 3

    service = WorkflowService(WorkflowRepository(db), AgentRepository(db))
    templates = service.seed_workflow_templates()
    assert len(templates) == 2
    assert all(t.is_template for t in templates)

    template_id = templates[0].id
    dup = auth_client.post(f"/api/v1/workflows/templates/{template_id}/duplicate")
    assert dup.status_code == 201
    assert dup.json()["is_template"] is False
    assert dup.json()["name"].endswith("(copy)")
    assert len(dup.json()["graph_json"]["nodes"]) >= 2
    assert len(dup.json()["agent_links"]) >= 1

    templates_api = auth_client.get("/api/v1/workflows?templates_only=true")
    assert templates_api.status_code == 200
    assert len(templates_api.json()) == 2

    user_workflows = auth_client.get("/api/v1/workflows?templates_only=false")
    assert user_workflows.status_code == 200
    assert len(user_workflows.json()) == 1


def test_web_workflows_list_requires_login(client):
    response = client.get("/workflows", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login"


def test_web_create_blank_workflow(auth_client):
    create = auth_client.post(
        "/workflows",
        data={"name": "Blank Flow", "description": "Empty graph"},
        follow_redirects=False,
    )
    assert create.status_code == 302
    assert create.headers["location"].startswith("/workflows/")

    listing = auth_client.get("/workflows")
    assert listing.status_code == 200
    assert "Blank Flow" in listing.text


def test_api_save_workflow_graph(auth_client, db, seeded_agents):
    agents = seeded_agents
    researcher = next(a for a in agents if a.name == "Researcher")
    writer = next(a for a in agents if a.name == "Writer")

    create = auth_client.post("/api/v1/workflows", json=_workflow_payload(name="Graph Test"))
    workflow_id = create.json()["id"]

    graph = {
        "nodes": [
            {
                "id": "research",
                "type": "agent",
                "label": "Research",
                "agent_id": researcher.id,
                "pos_x": 100,
                "pos_y": 80,
            },
            {
                "id": "writer",
                "type": "agent",
                "label": "Writer",
                "agent_id": writer.id,
                "pos_x": 320,
                "pos_y": 80,
            },
            {"id": "done", "type": "end", "label": "END", "pos_x": 540, "pos_y": 80},
        ],
        "edges": [
            {"from": "research", "to": "writer"},
            {"from": "writer", "to": "done"},
        ],
    }

    saved = auth_client.put(
        f"/api/v1/workflows/{workflow_id}/graph",
        json={"graph_json": graph},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["version"] == 2
    assert len(body["graph_json"]["nodes"]) == 3
    assert len(body["agent_links"]) == 2
    link_ids = {link["node_id"] for link in body["agent_links"]}
    assert link_ids == {"research", "writer"}

    again = auth_client.get(f"/api/v1/workflows/{workflow_id}")
    assert again.json()["graph_json"]["nodes"][0]["pos_x"] == 100


def test_api_save_graph_invalid_agent(auth_client):
    create = auth_client.post("/api/v1/workflows", json=_workflow_payload())
    workflow_id = create.json()["id"]

    bad = auth_client.put(
        f"/api/v1/workflows/{workflow_id}/graph",
        json={
            "graph_json": {
                "nodes": [
                    {"id": "a", "type": "agent", "label": "A", "agent_id": 99999},
                ],
                "edges": [],
            }
        },
    )
    assert bad.status_code == 422


def test_web_workflow_builder(auth_client, db, seeded_agents):
    create = auth_client.post(
        "/workflows",
        data={"name": "Builder Flow", "description": ""},
        follow_redirects=False,
    )
    workflow_id = int(create.headers["location"].rstrip("/").split("/")[-1].split("?")[0])

    page = auth_client.get(f"/workflows/{workflow_id}/edit")
    assert page.status_code == 200
    assert "drawflow" in page.text
    assert "WORKFLOW_BUILDER_CONFIG" in page.text
    assert "btn-save-graph" in page.text


def test_web_builder_embeds_saved_graph(auth_client, db, seeded_agents):
    agents = seeded_agents
    researcher = next(a for a in agents if a.name == "Researcher")

    create = auth_client.post("/api/v1/workflows", json=_workflow_payload(name="Builder Reload"))
    workflow_id = create.json()["id"]

    graph = {
        "nodes": [
            {
                "id": "persisted_node",
                "type": "agent",
                "label": "Persisted",
                "agent_id": researcher.id,
                "pos_x": 120,
                "pos_y": 90,
            },
        ],
        "edges": [],
    }
    auth_client.put(f"/api/v1/workflows/{workflow_id}/graph", json={"graph_json": graph})

    page = auth_client.get(f"/workflows/{workflow_id}/edit")
    assert page.status_code == 200
    assert "persisted_node" in page.text
    assert '"nodes"' in page.text


def test_web_builder_template(auth_client, db, seeded_agents):
    service = WorkflowService(WorkflowRepository(db), AgentRepository(db))
    templates = service.seed_workflow_templates()
    template = templates[0]

    page = auth_client.get(f"/workflows/{template.id}/edit")
    assert page.status_code == 200
    assert "Research" in page.text or template.name in page.text
    assert "badge badge-light-info" in page.text


def test_seed_demo_workflow(db, seeded_agents):
    service = WorkflowService(WorkflowRepository(db), AgentRepository(db))
    demo = service.seed_demo_workflow()
    assert demo is not None
    assert demo.name == WorkflowService.DEMO_WORKFLOW_NAME
    assert demo.is_template is False
    assert len(demo.graph_json["nodes"]) == 4
    assert len(demo.graph_json["edges"]) == 3
    assert len(demo.agent_links) == 3

    again = service.seed_demo_workflow()
    assert again is None


def test_web_use_template(auth_client, db, seeded_agents):
    service = WorkflowService(WorkflowRepository(db), AgentRepository(db))
    templates = service.seed_workflow_templates()
    template = next(t for t in templates if t.name == "Research & Notify")

    use = auth_client.post(
        f"/workflows/templates/{template.id}/use",
        follow_redirects=False,
    )
    assert use.status_code == 302
    assert use.headers["location"].startswith("/workflows/")

    listing = auth_client.get("/workflows")
    assert "(copy)" in listing.text
    assert "Research" in listing.text and "Notify" in listing.text

    templates_page = auth_client.get("/workflows/templates")
    assert templates_page.status_code == 200
    assert "Research" in templates_page.text and "Notify" in templates_page.text
    assert "Use Template" in templates_page.text
