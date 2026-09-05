import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfigurationVersion(Base):
    __tablename__ = "configuration_versions"
    __table_args__ = (UniqueConstraint("scope", "config_key", "version", name="uq_config_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scope: Mapped[str] = mapped_column(String(120), index=True)
    config_key: Mapped[str] = mapped_column(String(180), index=True)
    version: Mapped[int] = mapped_column(Integer)
    value_json: Mapped[str] = mapped_column(Text)
    changed_by: Mapped[str] = mapped_column(String(255), index=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
