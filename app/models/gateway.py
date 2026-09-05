import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GatewayRoute(Base):
    __tablename__ = "gateway_routes"
    __table_args__ = (UniqueConstraint("route_key", name="uq_gateway_route_key"),)

    route_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    route_key: Mapped[str] = mapped_column(String(160), index=True)
    system_key: Mapped[str] = mapped_column(String(120), index=True)
    public_path: Mapped[str] = mapped_column(String(400))
    upstream_path: Mapped[str] = mapped_column(String(400))
    methods_json: Mapped[str] = mapped_column(Text, default='["GET"]')
    auth_policy: Mapped[str] = mapped_column(String(120), default="authenticated")
    rate_limit_per_minute: Mapped[int | None] = mapped_column(nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CorrelatedEvent(Base):
    __tablename__ = "correlated_events"

    correlation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type: Mapped[str] = mapped_column(String(160), index=True)
    source_system_key: Mapped[str] = mapped_column(String(120), index=True)
    subject: Mapped[str] = mapped_column(String(255), index=True)
    severity: Mapped[str] = mapped_column(String(40), default="info", index=True)
    incident_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    parent_correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
