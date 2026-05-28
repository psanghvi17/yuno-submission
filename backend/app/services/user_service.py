from pydantic import ValidationError

from app.core.security import hash_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserNotFound(Exception):
    pass


class UserValidationError(Exception):
    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__(str(errors))


class UserService:
    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    def list_users(self) -> list[User]:
        return self.user_repo.list_all()

    def get_user(self, user_id: int) -> User:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFound(f"User {user_id} not found")
        return user

    def create_user(self, data: UserCreate) -> User:
        self._ensure_unique_email(data.email)
        return self.user_repo.create(
            email=str(data.email),
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            is_active=data.is_active,
        )

    def update_user(
        self,
        user_id: int,
        data: UserUpdate,
        *,
        acting_user_id: int,
    ) -> User:
        user = self.get_user(user_id)
        updates = data.model_dump(exclude_unset=True, exclude_none=True)

        if "email" in updates:
            new_email = str(updates.pop("email"))
            if new_email != user.email:
                self._ensure_unique_email(new_email, exclude_id=user.id)
            updates["email"] = new_email

        if "password" in updates:
            password = updates.pop("password")
            if password:
                updates["hashed_password"] = hash_password(password)

        if "is_active" in updates and user.id == acting_user_id and not updates["is_active"]:
            raise UserValidationError(
                {"is_active": "You cannot deactivate your own account"}
            )

        if not updates:
            return user

        return self.user_repo.update(user, **updates)

    def delete_user(self, user_id: int, *, acting_user_id: int) -> None:
        if user_id == acting_user_id:
            raise UserValidationError(
                {"form": "You cannot delete your own account while signed in"}
            )
        user = self.get_user(user_id)
        self.user_repo.delete(user)

    @staticmethod
    def build_create_from_form(
        *,
        email: str,
        password: str,
        password_confirm: str,
        full_name: str,
        is_active: bool,
    ) -> UserCreate:
        errors: dict[str, str] = {}
        if password != password_confirm:
            errors["password_confirm"] = "Passwords do not match"
        try:
            payload = UserCreate(
                email=email,
                password=password,
                full_name=full_name,
                is_active=is_active,
            )
        except ValidationError as exc:
            for err in exc.errors():
                field = ".".join(str(part) for part in err["loc"])
                errors[field or "form"] = err["msg"]
        if errors:
            raise UserValidationError(errors)
        return payload

    @staticmethod
    def build_update_from_form(
        *,
        email: str,
        password: str,
        password_confirm: str,
        full_name: str,
        is_active: bool,
    ) -> UserUpdate:
        errors: dict[str, str] = {}
        if password or password_confirm:
            if password != password_confirm:
                errors["password_confirm"] = "Passwords do not match"
            elif len(password) < 8:
                errors["password"] = "Password must be at least 8 characters"
        fields: dict = {
            "email": email,
            "full_name": full_name,
            "is_active": is_active,
        }
        if password:
            fields["password"] = password
        try:
            payload = UserUpdate(**fields)
        except ValidationError as exc:
            for err in exc.errors():
                field = ".".join(str(part) for part in err["loc"])
                errors[field or "form"] = err["msg"]
        if errors:
            raise UserValidationError(errors)
        return payload

    def _ensure_unique_email(self, email: str, *, exclude_id: int | None = None) -> None:
        existing = self.user_repo.get_by_email(email)
        if existing and existing.id != exclude_id:
            raise UserValidationError({"email": "A user with this email already exists"})
