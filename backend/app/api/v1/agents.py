from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_agent_repository, get_current_user
from app.models.user import User
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate
from app.services.agent_service import AgentNotFound, AgentService, AgentValidationError

router = APIRouter(prefix="/agents", tags=["Agents"])


def _agent_service(
    agent_repo: AgentRepository = Depends(get_agent_repository),
) -> AgentService:
    return AgentService(agent_repo)


@router.get("", response_model=list[AgentResponse])
def list_agents(
    _user: User = Depends(get_current_user),
    service: AgentService = Depends(_agent_service),
):
    return service.list_agents()


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreate,
    _user: User = Depends(get_current_user),
    service: AgentService = Depends(_agent_service),
):
    try:
        return service.create_agent(payload)
    except AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors)


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(
    agent_id: int,
    _user: User = Depends(get_current_user),
    service: AgentService = Depends(_agent_service),
):
    try:
        return service.get_agent(agent_id)
    except AgentNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


@router.put("/{agent_id}", response_model=AgentResponse)
def update_agent(
    agent_id: int,
    payload: AgentUpdate,
    _user: User = Depends(get_current_user),
    service: AgentService = Depends(_agent_service),
):
    try:
        return service.update_agent(agent_id, payload)
    except AgentNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    except AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(
    agent_id: int,
    _user: User = Depends(get_current_user),
    service: AgentService = Depends(_agent_service),
):
    try:
        service.delete_agent(agent_id)
    except AgentNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
