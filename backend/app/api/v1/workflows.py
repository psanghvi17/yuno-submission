from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import (
    get_agent_repository,
    get_current_user,
    get_workflow_repository,
)
from app.models.user import User
from app.repositories.agent_repository import AgentRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowGraphSave,
    WorkflowResponse,
    WorkflowUpdate,
)
from app.services.workflow_service import (
    WorkflowNotFound,
    WorkflowService,
    WorkflowValidationError,
)

router = APIRouter(prefix="/workflows", tags=["Workflows"])


def _workflow_service(
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
    agent_repo: AgentRepository = Depends(get_agent_repository),
) -> WorkflowService:
    return WorkflowService(workflow_repo, agent_repo)


@router.get("", response_model=list[WorkflowResponse])
def list_workflows(
    templates_only: bool | None = None,
    _user: User = Depends(get_current_user),
    service: WorkflowService = Depends(_workflow_service),
):
    return service.list_workflows(templates_only=templates_only)


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
def create_workflow(
    payload: WorkflowCreate,
    _user: User = Depends(get_current_user),
    service: WorkflowService = Depends(_workflow_service),
):
    try:
        return service.create_workflow(payload)
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(
    workflow_id: int,
    _user: User = Depends(get_current_user),
    service: WorkflowService = Depends(_workflow_service),
):
    try:
        return service.get_workflow(workflow_id)
    except WorkflowNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")


@router.put("/{workflow_id}/graph", response_model=WorkflowResponse)
def save_workflow_graph(
    workflow_id: int,
    payload: WorkflowGraphSave,
    _user: User = Depends(get_current_user),
    service: WorkflowService = Depends(_workflow_service),
):
    try:
        return service.save_workflow_graph(workflow_id, payload.graph_json)
    except WorkflowNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(
    workflow_id: int,
    payload: WorkflowUpdate,
    _user: User = Depends(get_current_user),
    service: WorkflowService = Depends(_workflow_service),
):
    try:
        return service.update_workflow(workflow_id, payload)
    except WorkflowNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
    workflow_id: int,
    _user: User = Depends(get_current_user),
    service: WorkflowService = Depends(_workflow_service),
):
    try:
        service.delete_workflow(workflow_id)
    except WorkflowNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")


@router.post(
    "/templates/{template_id}/duplicate",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_template(
    template_id: int,
    name: str | None = None,
    _user: User = Depends(get_current_user),
    service: WorkflowService = Depends(_workflow_service),
):
    try:
        return service.duplicate_from_template(template_id, name=name)
    except WorkflowNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors)
