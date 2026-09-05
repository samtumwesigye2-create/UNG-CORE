from typing import Any

from pydantic import BaseModel, Field


class GatewayRouteIn(BaseModel):
    route_key: str = Field(min_length=2, max_length=160)
    system_key: str = Field(min_length=2, max_length=120)
    public_path: str
    upstream_path: str
    methods: list[str] = ["GET"]
    auth_policy: str = "authenticated"
    rate_limit_per_minute: int | None = Field(default=None, ge=1)
    enabled: bool = True


class CorrelatedEventIn(BaseModel):
    event_type: str
    source_system_key: str
    subject: str
    severity: str = "info"
    incident_id: str | None = None
    parent_correlation_id: str | None = None
    payload: dict[str, Any] = {}
