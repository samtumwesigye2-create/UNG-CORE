import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config_history import ConfigurationVersion
from app.models.control_plane import ConfigurationRegistry, OrganizationRegistry, SystemDependency, SystemRegistry
from app.schemas.control_plane import ConfigurationIn, DependencyIn, OrganizationIn, SystemIn


def _dump(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


async def upsert_organization(db: AsyncSession, body: OrganizationIn) -> OrganizationRegistry:
    key = body.organization_key.upper()
    row = await db.get(OrganizationRegistry, key)
    if row is None:
        row = OrganizationRegistry(organization_key=key)
        db.add(row)
    row.display_name = body.display_name
    row.organization_type = body.organization_type
    row.enabled = body.enabled
    row.metadata_json = _dump(body.metadata)
    await db.commit()
    await db.refresh(row)
    return row


async def list_organizations(db: AsyncSession) -> list[OrganizationRegistry]:
    result = await db.execute(select(OrganizationRegistry).order_by(OrganizationRegistry.organization_key))
    return list(result.scalars().all())


async def upsert_system(db: AsyncSession, body: SystemIn) -> SystemRegistry:
    key = body.system_key.upper()
    row = await db.get(SystemRegistry, key)
    if row is None:
        row = SystemRegistry(system_key=key)
        db.add(row)
    row.display_name = body.display_name
    row.owner_organization_key = body.owner_organization_key.upper()
    row.lifecycle_status = body.lifecycle_status
    row.criticality = body.criticality
    row.base_url = body.base_url
    row.enabled = body.enabled
    row.capabilities_json = _dump(body.capabilities)
    await db.commit()
    await db.refresh(row)
    return row


async def list_systems(db: AsyncSession) -> list[SystemRegistry]:
    result = await db.execute(select(SystemRegistry).order_by(SystemRegistry.system_key))
    return list(result.scalars().all())


async def add_dependency(db: AsyncSession, system_key: str, body: DependencyIn) -> SystemDependency:
    system_key = system_key.upper()
    dependency_key = body.depends_on_system_key.upper()
    result = await db.execute(select(SystemDependency).where(SystemDependency.system_key == system_key, SystemDependency.depends_on_system_key == dependency_key))
    row = result.scalar_one_or_none()
    if row is None:
        row = SystemDependency(system_key=system_key, depends_on_system_key=dependency_key)
        db.add(row)
    row.dependency_type = body.dependency_type
    row.required = body.required
    await db.commit()
    await db.refresh(row)
    return row


async def list_dependencies(db: AsyncSession, system_key: str | None = None) -> list[SystemDependency]:
    stmt = select(SystemDependency)
    if system_key:
        stmt = stmt.where(SystemDependency.system_key == system_key.upper())
    result = await db.execute(stmt.order_by(SystemDependency.system_key, SystemDependency.depends_on_system_key))
    return list(result.scalars().all())


async def _next_config_version(db: AsyncSession, scope: str, config_key: str) -> int:
    result = await db.execute(select(func.max(ConfigurationVersion.version)).where(ConfigurationVersion.scope == scope, ConfigurationVersion.config_key == config_key))
    current = result.scalar_one_or_none()
    return int(current or 0) + 1


async def upsert_configuration(db: AsyncSession, scope: str, config_key: str, body: ConfigurationIn, updated_by: str) -> ConfigurationRegistry:
    scope = scope.upper()
    result = await db.execute(select(ConfigurationRegistry).where(ConfigurationRegistry.scope == scope, ConfigurationRegistry.config_key == config_key))
    row = result.scalar_one_or_none()
    if row is None:
        row = ConfigurationRegistry(scope=scope, config_key=config_key, updated_by=updated_by)
        db.add(row)
    value_json = _dump(body.value)
    row.value_json = value_json
    row.is_secret_reference = body.is_secret_reference
    row.updated_by = updated_by
    version = await _next_config_version(db, scope, config_key)
    db.add(ConfigurationVersion(scope=scope, config_key=config_key, version=version, value_json=value_json, changed_by=updated_by))
    await db.commit()
    await db.refresh(row)
    return row


async def list_configuration(db: AsyncSession, scope: str) -> list[ConfigurationRegistry]:
    result = await db.execute(select(ConfigurationRegistry).where(ConfigurationRegistry.scope == scope.upper()).order_by(ConfigurationRegistry.config_key))
    return list(result.scalars().all())


async def list_configuration_history(db: AsyncSession, scope: str, config_key: str) -> list[ConfigurationVersion]:
    result = await db.execute(select(ConfigurationVersion).where(ConfigurationVersion.scope == scope.upper(), ConfigurationVersion.config_key == config_key).order_by(ConfigurationVersion.version.desc()))
    return list(result.scalars().all())


async def rollback_configuration(db: AsyncSession, scope: str, config_key: str, version: int, changed_by: str) -> ConfigurationRegistry:
    scope = scope.upper()
    result = await db.execute(select(ConfigurationVersion).where(ConfigurationVersion.scope == scope, ConfigurationVersion.config_key == config_key, ConfigurationVersion.version == version))
    historical = result.scalar_one_or_none()
    if historical is None:
        raise LookupError("configuration version not found")
    current_result = await db.execute(select(ConfigurationRegistry).where(ConfigurationRegistry.scope == scope, ConfigurationRegistry.config_key == config_key))
    row = current_result.scalar_one_or_none()
    if row is None:
        row = ConfigurationRegistry(scope=scope, config_key=config_key, updated_by=changed_by)
        db.add(row)
    row.value_json = historical.value_json
    row.updated_by = changed_by
    new_version = await _next_config_version(db, scope, config_key)
    db.add(ConfigurationVersion(scope=scope, config_key=config_key, version=new_version, value_json=historical.value_json, changed_by=changed_by))
    await db.commit()
    await db.refresh(row)
    return row


def serialize_organization(row: OrganizationRegistry) -> dict:
    return {"organization_key": row.organization_key, "display_name": row.display_name, "organization_type": row.organization_type, "enabled": row.enabled, "metadata": json.loads(row.metadata_json)}


def serialize_system(row: SystemRegistry) -> dict:
    return {"system_key": row.system_key, "display_name": row.display_name, "owner_organization_key": row.owner_organization_key, "lifecycle_status": row.lifecycle_status, "criticality": row.criticality, "base_url": row.base_url, "enabled": row.enabled, "capabilities": json.loads(row.capabilities_json)}


def serialize_dependency(row: SystemDependency) -> dict:
    return {"dependency_id": row.dependency_id, "system_key": row.system_key, "depends_on_system_key": row.depends_on_system_key, "dependency_type": row.dependency_type, "required": row.required}


def serialize_configuration(row: ConfigurationRegistry) -> dict:
    return {"scope": row.scope, "config_key": row.config_key, "value": json.loads(row.value_json), "is_secret_reference": row.is_secret_reference, "updated_by": row.updated_by, "updated_at": row.updated_at}


def serialize_configuration_version(row: ConfigurationVersion) -> dict:
    return {"scope": row.scope, "config_key": row.config_key, "version": row.version, "value": json.loads(row.value_json), "changed_by": row.changed_by, "changed_at": row.changed_at}
