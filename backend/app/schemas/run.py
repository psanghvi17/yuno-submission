from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RunMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    from_agent_id: int | None
    to_agent_id: int | None
    role: str
    content: str
    channel: str
    created_at: datetime


class RunLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    level: str
    message: str
    metadata: dict = Field(validation_alias="log_metadata")
    created_at: datetime


class RunUsageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    agent_id: int | None
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    created_at: datetime


class WorkflowRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    triggered_by: str
    cancel_requested: bool = False
    created_at: datetime


class WorkflowRunDetail(WorkflowRunRead):
    messages: list[RunMessageRead] = []
    logs: list[RunLogRead] = []
    usage: list[RunUsageRead] = []
    total_cost_usd: Decimal = Decimal("0")
