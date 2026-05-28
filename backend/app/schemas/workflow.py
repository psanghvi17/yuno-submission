from typing import Any

from pydantic import BaseModel, Field, field_validator


class WorkflowBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    graph_json: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)
    is_template: bool = False

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class WorkflowCreate(WorkflowBase):
    agent_links: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    graph_json: dict[str, Any] | None = None
    version: int | None = Field(default=None, ge=1)
    is_template: bool | None = None
    agent_links: list[dict[str, Any]] | None = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class WorkflowAgentLinkResponse(BaseModel):
    id: int
    agent_id: int
    node_id: str

    model_config = {"from_attributes": True}


class WorkflowGraphSave(BaseModel):
    """Simple {nodes, edges} graph persisted by the visual builder."""

    graph_json: dict[str, Any]

    @field_validator("graph_json")
    @classmethod
    def graph_must_be_object(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("graph_json must be an object")
        return value


class WorkflowResponse(WorkflowBase):
    id: int
    agent_links: list[WorkflowAgentLinkResponse] = Field(default_factory=list)
    created_at: Any
    updated_at: Any

    model_config = {"from_attributes": True}
