from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)
    is_active: bool = True

    @field_validator("email", "full_name", mode="before")
    @classmethod
    def strip_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None

    @field_validator("email", "full_name", mode="before")
    @classmethod
    def strip_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    is_active: bool

    model_config = {"from_attributes": True}
