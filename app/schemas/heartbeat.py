from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class HeartbeatIn(BaseModel):
    status: Literal["healthy", "degraded"] = "healthy"
    latency_ms: int | None = Field(default=None, ge=0)
    details: dict = Field(default_factory=dict)


class ServiceHealthOut(BaseModel):
    service_key: str
    state: Literal["healthy", "degraded", "offline", "unknown", "disabled"]
    reported_status: str | None = None
    latency_ms: int | None = None
    last_seen_at: datetime | None = None
    age_seconds: int | None = None
    details: dict = Field(default_factory=dict)
