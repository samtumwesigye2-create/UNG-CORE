import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventRoutingRule(Base):
    __tablename__ = "event_routing_rules"
    __table_args__ = (UniqueConstraint("rule_key", name="uq_event_routing_rule_key"),)

    rule_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_key: Mapped[str] = mapped_column(String(160), index=True)
    event_type: Mapped[str] = mapped_column(String(160), index=True)
    source_system_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    minimum_severity: Mapped[str] = mapped_column(String(40), default="info")
    target_systems_json: Mapped[str] = mapped_column(Text, default="[]")
    create_incident: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
