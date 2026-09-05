import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertPolicy(Base):
    __tablename__ = "alert_policies"
    __table_args__ = (UniqueConstraint("policy_key", name="uq_alert_policy_key"),)

    policy_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_key: Mapped[str] = mapped_column(String(160), index=True)
    service_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    minimum_severity: Mapped[str] = mapped_column(String(16), default="warning", index=True)
    trigger_states_json: Mapped[str] = mapped_column(Text, default='["degraded","offline"]')
    escalation_minutes_json: Mapped[str] = mapped_column(Text, default="[5,15,30]")
    targets_json: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_alert_dedupe_key"),)

    alert_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dedupe_key: Mapped[str] = mapped_column(String(220), index=True)
    policy_key: Mapped[str] = mapped_column(String(160), index=True)
    service_key: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    escalation_stage: Mapped[int] = mapped_column(Integer, default=0)
    incident_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
