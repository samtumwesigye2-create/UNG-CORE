import json

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resource_catalog import ResourceRecord


class ResourceConflict(ValueError):
    pass


async def get_resource(db, resource_id: str):
    if hasattr(db, "resources"):
        return db.resources.get(resource_id)
    return await db.get(ResourceRecord, resource_id)


async def register_resource(db, payload: dict) -> ResourceRecord:
    resource_id = str(payload["resource_id"]).strip()
    if await get_resource(db, resource_id) is not None:
        raise ResourceConflict(f"resource already exists: {resource_id}")
    row = ResourceRecord(
        resource_id=resource_id,
        resource_type=str(payload["resource_type"]).strip(),
        system_key=str(payload["system_key"]).strip(),
        name=str(payload["name"]).strip(),
        version=payload.get("version"),
        health_state=payload.get("health_state", "unknown"),
        metadata_json=json.dumps(payload.get("metadata", {}), sort_keys=True),
        dependencies_json=json.dumps(payload.get("dependencies", [])),
        controllable=bool(payload.get("controllable", False)),
    )
    if hasattr(db, "resources"):
        db.resources[resource_id] = row
        return row
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def find_resources(db, query: str = "", resource_type: str | None = None):
    needle = query.strip().lower()
    if hasattr(db, "resources"):
        rows = list(db.resources.values())
        if resource_type:
            rows = [row for row in rows if row.resource_type == resource_type]
        if needle:
            rows = [row for row in rows if needle in " ".join((row.resource_id, row.resource_type, row.system_key, row.name)).lower()]
        return sorted(rows, key=lambda row: (row.name.lower(), row.resource_id))

    stmt = select(ResourceRecord)
    if resource_type:
        stmt = stmt.where(ResourceRecord.resource_type == resource_type)
    if needle:
        pattern = f"%{needle}%"
        stmt = stmt.where(or_(ResourceRecord.resource_id.ilike(pattern), ResourceRecord.system_key.ilike(pattern), ResourceRecord.name.ilike(pattern)))
    stmt = stmt.order_by(ResourceRecord.name.asc(), ResourceRecord.resource_id.asc())
    return list((await db.execute(stmt)).scalars().all())


def serialize_resource(row: ResourceRecord) -> dict:
    return {
        "resource_id": row.resource_id,
        "resource_type": row.resource_type,
        "system_key": row.system_key,
        "name": row.name,
        "version": row.version,
        "health_state": row.health_state,
        "metadata": json.loads(row.metadata_json or "{}"),
        "dependencies": json.loads(row.dependencies_json or "[]"),
        "controllable": row.controllable,
    }
