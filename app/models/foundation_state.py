import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FoundationState(Base):
    __tablename__ = "foundation_state"
    __table_args__ = (UniqueConstraint("namespace", "state_key", name="uq_foundation_state_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace: Mapped[str] = mapped_column(String(120), index=True)
    state_key: Mapped[str] = mapped_column(String(180), index=True)
    value_json: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[str] = mapped_column(String(255), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
