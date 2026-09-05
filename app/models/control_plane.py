from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrganizationRegistry(Base):
    __tablename__ = "organization_registry"

    organization_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_type: Mapped[str] = mapped_column(String(80), default="agency")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SystemRegistry(Base):
    __tablename__ = "system_registry"

    system_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_organization_key: Mapped[str] = mapped_column(String(120), index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    criticality: Mapped[str] = mapped_column(String(40), default="standard", index=True)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SystemDependency(Base):
    __tablename__ = "system_dependencies"
    __table_args__ = (UniqueConstraint("system_key", "depends_on_system_key", name="uq_system_dependency"),)

    dependency_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    system_key: Mapped[str] = mapped_column(String(120), index=True)
    depends_on_system_key: Mapped[str] = mapped_column(String(120), index=True)
    dependency_type: Mapped[str] = mapped_column(String(60), default="runtime")
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ConfigurationRegistry(Base):
    __tablename__ = "configuration_registry"
    __table_args__ = (UniqueConstraint("scope", "config_key", name="uq_configuration_scope_key"),)

    config_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(120), index=True)
    config_key: Mapped[str] = mapped_column(String(160), index=True)
    value_json: Mapped[str] = mapped_column(Text, default="null")
    is_secret_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str] = mapped_column(String(255), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
