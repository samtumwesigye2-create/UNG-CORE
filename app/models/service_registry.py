from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class RegisteredService(Base):
    __tablename__ = "registered_services"
    __table_args__ = (UniqueConstraint("service_key", name="uq_registered_services_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service_key: Mapped[str] = mapped_column(String(80), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    base_url: Mapped[str] = mapped_column(String(512))
    version: Mapped[str] = mapped_column(String(64), default="unknown")
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    health_path: Mapped[str] = mapped_column(String(128), default="/health")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
