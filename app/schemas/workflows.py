from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkflowStartIn(BaseModel):
    workflow_key: str = Field(min_length=2, max_length=120)
    subject: str = Field(min_length=1, max_length=255)
    input: dict[str, Any] = Field(default_factory=dict)


class WorkflowExecutionOut(BaseModel):
    execution_id: str
    workflow_key: str
    subject: str
    requested_by: str
    status: str
    input: dict[str, Any]
    created_at: datetime
    updated_at: datetime
