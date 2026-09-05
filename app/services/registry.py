import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.service_registry import RegisteredService
from app.schemas.registry import ServiceRegistrationIn


def serialize(row: RegisteredService) -> dict:
    return {
        "service_key": row.service_key,
        "display_name": row.display_name,
        "base_url": row.base_url,
        "version": row.version,
        "capabilities": json.loads(row.capabilities_json),
        "health_path": row.health_path,
        "enabled": row.enabled,
        "registered_at": row.registered_at,
        "updated_at": row.updated_at,
    }

async def upsert_service(db: AsyncSession, body: ServiceRegistrationIn) -> RegisteredService:
    result = await db.execute(select(RegisteredService).where(RegisteredService.service_key == body.service_key))
    row = result.scalar_one_or_none()
    values = {
        "display_name": body.display_name,
        "base_url": str(body.base_url).rstrip("/"),
        "version": body.version,
        "capabilities_json": json.dumps(sorted(set(body.capabilities))),
        "health_path": body.health_path if body.health_path.startswith("/") else f"/{body.health_path}",
        "enabled": body.enabled,
    }
    if row is None:
        row = RegisteredService(service_key=body.service_key, **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row

async def list_services(db: AsyncSession, enabled_only: bool = True) -> list[RegisteredService]:
    query = select(RegisteredService).order_by(RegisteredService.service_key)
    if enabled_only:
        query = query.where(RegisteredService.enabled.is_(True))
    return list((await db.execute(query)).scalars().all())

async def get_service(db: AsyncSession, service_key: str) -> RegisteredService | None:
    return (await db.execute(select(RegisteredService).where(RegisteredService.service_key == service_key))).scalar_one_or_none()
