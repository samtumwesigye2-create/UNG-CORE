import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApprovalPolicy(Base):
    __tablename__ = "approval_policies"
    __table_args__ = (UniqueConstraint("policy_key", name="uq_approval_policy_key"),)

    policy_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    action_pattern: Mapped[str] = mapped_column(String(160), index=True)
    system_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    required_roles_json: Mapped[str] = mapped_column(Text, default="[]")
    expires_minutes: Mapped[int] = mapped_column(Integer, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_key: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(160), index=True)
    actor_id: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    system_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    approval_count: Mapped[int] = mapped_column(Integer, default=0)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (UniqueConstraint("request_id", "approver_id", name="uq_approval_decision_request_actor"),)

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    approver_id: Mapped[str] = mapped_column(String(128), index=True)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    roles_json: Mapped[str] = mapped_column(Text, default="[]")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
