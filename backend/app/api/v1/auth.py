from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.deps import SESSION_USER_ID_KEY, get_current_user, get_user_repository
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, LoginResponse, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


def _auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(user_repo)


@router.post("/login", response_model=LoginResponse, summary="Log in (JSON)")
def api_login(
    payload: LoginRequest,
    request: Request,
    auth: AuthService = Depends(_auth_service),
):
    """Authenticate with email/password and set the session cookie."""
    user = auth.authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    request.session[SESSION_USER_ID_KEY] = user.id
    return LoginResponse(
        message="Logged in successfully",
        user=UserResponse.model_validate(user),
    )


@router.post("/logout", summary="Log out")
def api_logout(request: Request):
    request.session.clear()
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse, summary="Current user")
def api_me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)
