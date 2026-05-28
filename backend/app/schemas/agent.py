from typing import Any

from pydantic import BaseModel, Field, field_validator


class AgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: str = Field(default="", max_length=255)
    system_prompt: str = ""
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=128)
    tools: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    @field_validator("name", "role", "system_prompt", "model", mode="before")
    @classmethod
    def strip_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("tools", mode="before")
    @classmethod
    def normalize_tools(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.replace(",", "\n").split("\n") if part.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("tools must be a list or string")


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    system_prompt: str | None = None
    model: str | None = Field(default=None, min_length=1, max_length=128)
    tools: list[str] | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None

    @field_validator("name", "role", "system_prompt", "model", mode="before")
    @classmethod
    def strip_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("tools", mode="before")
    @classmethod
    def normalize_tools(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        return AgentBase.normalize_tools(value)


class AgentResponse(AgentBase):
    id: int
    created_at: Any
    updated_at: Any

    model_config = {"from_attributes": True}
