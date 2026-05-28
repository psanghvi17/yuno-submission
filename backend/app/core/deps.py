from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.repositories.agent_repository import AgentRepository
from app.repositories.user_repository import UserRepository
from app.repositories.workflow_repository import WorkflowRepository

SESSION_USER_ID_KEY = "user_id"
SESSION_COOKIE_NAME = "session"
LOGIN_PATH = "/auth/login"

session_cookie_scheme = APIKeyCookie(
    name=SESSION_COOKIE_NAME,
    auto_error=False,
    description="Session cookie set by POST /api/v1/auth/login",
)


class LoginRequired(Exception):
    """Raised by web dependencies; handled with a redirect to the login page."""

    def __init__(self, redirect_url: str = LOGIN_PATH) -> None:
        self.redirect_url = redirect_url
        super().__init__(redirect_url)


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_agent_repository(db: Session = Depends(get_db)) -> AgentRepository:
    return AgentRepository(db)


def get_workflow_repository(db: Session = Depends(get_db)) -> WorkflowRepository:
    return WorkflowRepository(db)


def _resolve_user_from_session(
    request: Request,
    user_repo: UserRepository,
    *,
    clear_invalid_session: bool = False,
) -> User | None:
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if not user_id:
        return None

    user = user_repo.get_by_id(int(user_id))
    if not user or not user.is_active:
        if clear_invalid_session:
            request.session.clear()
        return None
    return user


def get_current_user(
    request: Request,
    _session: str | None = Security(session_cookie_scheme),
    user_repo: UserRepository = Depends(get_user_repository),
) -> User:
    user = _resolve_user_from_session(request, user_repo, clear_invalid_session=True)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


def get_current_user_web(
    request: Request,
    user_repo: UserRepository = Depends(get_user_repository),
) -> User:
    user = _resolve_user_from_session(request, user_repo, clear_invalid_session=True)
    if not user:
        raise LoginRequired()
    return user


def get_current_user_optional(
    request: Request,
    user_repo: UserRepository = Depends(get_user_repository),
) -> User | None:
    return _resolve_user_from_session(request, user_repo, clear_invalid_session=True)
