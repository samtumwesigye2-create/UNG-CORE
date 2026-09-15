from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResourceRecord(Base):
    __tablename__ = "resource_catalog"

    resource_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(80), index=True)
    system_key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    health_state: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    dependencies_json: Mapped[str] = mapped_column(Text, default="[]")
    controllable: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
