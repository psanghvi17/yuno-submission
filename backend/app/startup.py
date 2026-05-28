from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.database import SessionLocal
from app.repositories.user_repository import UserRepository
from app.repositories.agent_repository import AgentRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService
from app.services.workflow_service import WorkflowService

LEGACY_ADMIN_EMAIL = "admin@yuno.local"


def migrate_legacy_admin_email() -> None:
    """Rename seeded admin when ADMIN_EMAIL no longer uses a reserved .local domain."""
    settings = get_settings()
    new_email = settings.admin_email.strip().lower()
    if new_email == LEGACY_ADMIN_EMAIL:
        return

    db: Session = SessionLocal()
    try:
        repo = UserRepository(db)
        legacy = repo.get_by_email(LEGACY_ADMIN_EMAIL)
        if not legacy or repo.get_by_email(new_email):
            return
        repo.update(legacy, email=new_email)
        print(f"Migrated admin email: {LEGACY_ADMIN_EMAIL} -> {new_email}")
    finally:
        db.close()


def seed_admin_user() -> None:
    settings = get_settings()
    db: Session = SessionLocal()
    try:
        auth = AuthService(UserRepository(db))
        created = auth.ensure_admin_user(
            email=settings.admin_email,
            password=settings.admin_password,
            full_name=settings.admin_full_name,
        )
        if created:
            print(f"Seeded admin user: {created.email}")
    finally:
        db.close()


def seed_default_agents() -> None:
    db: Session = SessionLocal()
    try:
        service = AgentService(AgentRepository(db))
        created = service.seed_default_agents()
        if created:
            names = ", ".join(agent.name for agent in created)
            print(f"Seeded default agents: {names}")
    finally:
        db.close()


def seed_workflow_templates() -> None:
    db: Session = SessionLocal()
    try:
        service = WorkflowService(WorkflowRepository(db), AgentRepository(db))
        created = service.seed_workflow_templates()
        if created:
            names = ", ".join(workflow.name for workflow in created)
            print(f"Seeded workflow templates: {names}")
    finally:
        db.close()


def seed_demo_workflow() -> None:
    db: Session = SessionLocal()
    try:
        service = WorkflowService(WorkflowRepository(db), AgentRepository(db))
        created = service.seed_demo_workflow()
        if created:
            print(f"Seeded demo workflow: {created.name}")
    finally:
        db.close()


def seed_e2e_pipeline() -> None:
    """Five-agent product launch pipeline + template + runnable workflow."""
    db: Session = SessionLocal()
    try:
        agent_service = AgentService(AgentRepository(db))
        agents = agent_service.seed_e2e_pipeline_agents()
        if agents:
            names = ", ".join(agent.name for agent in agents)
            print(f"Seeded E2E pipeline agents: {names}")

        wf_service = WorkflowService(WorkflowRepository(db), AgentRepository(db))
        template = wf_service.seed_e2e_pipeline_template()
        if template:
            print(f"Seeded E2E template: {template.name}")
        runnable = wf_service.seed_e2e_run_workflow()
        if runnable:
            print(f"Seeded E2E runnable workflow: {runnable.name}")
    finally:
        db.close()


def seed_dev_pipeline() -> None:
    """Six-agent dev pipeline (build & deploy) + template + runnable workflow."""
    db: Session = SessionLocal()
    try:
        agent_service = AgentService(AgentRepository(db))
        agents = agent_service.seed_dev_pipeline_agents()
        if agents:
            names = ", ".join(agent.name for agent in agents)
            print(f"Seeded Dev pipeline agents: {names}")
        refreshed = agent_service.refresh_dev_pipeline_agents()
        if refreshed:
            print(f"Refreshed Dev pipeline agent prompts: {refreshed}")

        wf_service = WorkflowService(WorkflowRepository(db), AgentRepository(db))
        template = wf_service.seed_dev_pipeline_template()
        if template:
            print(f"Seeded Dev pipeline template: {template.name}")
        runnable = wf_service.seed_dev_run_workflow()
        if runnable:
            print(f"Seeded Dev pipeline runnable workflow: {runnable.name}")
        wf_updated = wf_service.refresh_dev_pipeline_workflows()
        if wf_updated:
            print(f"Refreshed Dev pipeline workflows: {wf_updated}")
    finally:
        db.close()
