from pydantic import BaseModel, Field, field_validator

from app.core.email import is_valid_login_email, normalize_email


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not is_valid_login_email(value):
            raise ValueError("Invalid email address")
        return normalize_email(value)


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    message: str
    user: UserResponse
