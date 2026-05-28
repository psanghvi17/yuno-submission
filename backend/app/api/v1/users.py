from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user, get_user_repository
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.user_service import UserNotFound, UserService, UserValidationError

router = APIRouter(prefix="/users", tags=["Users"])


def _user_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> UserService:
    return UserService(user_repo)


@router.get("", response_model=list[UserResponse])
def list_users(
    _user: User = Depends(get_current_user),
    service: UserService = Depends(_user_service),
):
    return service.list_users()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    _user: User = Depends(get_current_user),
    service: UserService = Depends(_user_service),
):
    try:
        return service.create_user(payload)
    except UserValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors,
        )


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    _user: User = Depends(get_current_user),
    service: UserService = Depends(_user_service),
):
    try:
        return service.get_user(user_id)
    except UserNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    service: UserService = Depends(_user_service),
):
    try:
        return service.update_user(
            user_id,
            payload,
            acting_user_id=user.id,
        )
    except UserNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    except UserValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors,
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    user: User = Depends(get_current_user),
    service: UserService = Depends(_user_service),
):
    try:
        service.delete_user(user_id, acting_user_id=user.id)
    except UserNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    except UserValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors,
        )
