from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ServiceHeartbeat(Base):
    __tablename__ = "service_heartbeats"
    __table_args__ = (UniqueConstraint("service_key", name="uq_service_heartbeats_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service_key: Mapped[str] = mapped_column(String(80), index=True)
    reported_status: Mapped[str] = mapped_column(String(32), default="healthy", index=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
