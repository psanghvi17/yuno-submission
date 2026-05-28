import os

# Tests must not use the VM DATABASE_URL from repo-root .env
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["RUNTIME_MOCK_LLM"] = "true"
os.environ["RUNTIME_MOCK_TOOLS"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Celery runs tasks inline during tests (see tests/test_runs.py).
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")

from app.config import get_settings
from app.core.database import Base, get_db
from app.models import (  # noqa: F401
    Agent,
    ChannelLink,
    RunLog,
    RunMessage,
    RunUsage,
    User,
    Workflow,
    WorkflowAgent,
    WorkflowRun,
)
from app.core.schema import APP_SCHEMA

get_settings.cache_clear()

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    execution_options={"schema_translate_map": {APP_SCHEMA: None}},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _disable_startup_seeds(monkeypatch):
    monkeypatch.setattr("app.startup.seed_admin_user", lambda: None)
    monkeypatch.setattr("app.main.seed_admin_user", lambda: None)
    monkeypatch.setattr("app.startup.seed_default_agents", lambda: None)
    monkeypatch.setattr("app.main.seed_default_agents", lambda: None)
    monkeypatch.setattr("app.startup.seed_workflow_templates", lambda: None)
    monkeypatch.setattr("app.main.seed_workflow_templates", lambda: None)
    monkeypatch.setattr("app.startup.seed_e2e_pipeline", lambda: None)
    monkeypatch.setattr("app.main.seed_e2e_pipeline", lambda: None)
    monkeypatch.setattr("app.startup.seed_demo_workflow", lambda: None)
    monkeypatch.setattr("app.main.seed_demo_workflow", lambda: None)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db):
    from app.main import app

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    import app.startup as startup_module

    original_seed = startup_module.seed_admin_user
    startup_module.seed_admin_user = lambda: None

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    startup_module.seed_admin_user = original_seed
