from datetime import datetime
from pydantic import BaseModel, Field

class Principal(BaseModel):
    subject: str
    display_name: str | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)

class AuditEventIn(BaseModel):
    actor_id: str
    action: str
    resource_type: str
    resource_id: str | None = None
    payload: dict = Field(default_factory=dict)

class AuditEventOut(AuditEventIn):
    event_id: str
    occurred_at: datetime

class RelayEnvelope(BaseModel):
    event_type: str
    source: str = "UNG-CORE"
    subject: str
    data: dict
    correlation_id: str | None = None
