import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ServiceCredential(Base):
    __tablename__ = "service_credentials"
    __table_args__ = (UniqueConstraint("credential_key", name="uq_service_credential_key"),)

    credential_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    credential_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    system_key: Mapped[str] = mapped_column(String(80), index=True)
    auth_type: Mapped[str] = mapped_column(String(32), default="bearer")
    secret_env_var: Mapped[str] = mapped_column(String(160))
    header_name: Mapped[str] = mapped_column(String(128), default="Authorization")
    prefix: Mapped[str] = mapped_column(String(64), default="Bearer ")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_idempotency_key"),)

    record_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    action: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(32), default="started", index=True)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CircuitState(Base):
    __tablename__ = "circuit_states"
    __table_args__ = (UniqueConstraint("system_key", name="uq_circuit_system_key"),)

    circuit_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    system_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(24), default="closed", index=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    failure_threshold: Mapped[int] = mapped_column(Integer, default=5)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_after_seconds: Mapped[int] = mapped_column(Integer, default=60)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class DeadLetter(Base):
    __tablename__ = "dead_letters"

    dead_letter_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(80), index=True)
    system_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(160), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="dead", index=True)
    replay_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
