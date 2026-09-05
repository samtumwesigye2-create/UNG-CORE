from datetime import datetime
from pydantic import BaseModel, Field

class IncidentOut(BaseModel):
    incident_id: str
    service_key: str
    state: str
    severity: str
    status: str
    details: dict = Field(default_factory=dict)
    opened_at: datetime
    resolved_at: datetime | None = None

class IncidentSummaryOut(BaseModel):
    open_total: int
    critical: int
    warning: int
    resolved_total: int
    affected_services: list[str] = Field(default_factory=list)
