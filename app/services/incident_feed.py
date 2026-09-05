import json
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.incident import ServiceIncident


def serialize_incident(row: ServiceIncident) -> dict:
    return {
        "incident_id": row.incident_id,
        "service_key": row.service_key,
        "state": row.state,
        "severity": row.severity,
        "status": row.status,
        "details": json.loads(row.details_json or "{}"),
        "opened_at": row.opened_at,
        "resolved_at": row.resolved_at,
    }

async def list_incidents(db: AsyncSession, status: str | None = None, service_key: str | None = None, limit: int = 100) -> list[ServiceIncident]:
    query = select(ServiceIncident).order_by(ServiceIncident.opened_at.desc()).limit(min(max(limit, 1), 500))
    if status:
        query = query.where(ServiceIncident.status == status)
    if service_key:
        query = query.where(ServiceIncident.service_key == service_key.upper())
    return list((await db.execute(query)).scalars().all())

async def incident_summary(db: AsyncSession) -> dict:
    rows = list((await db.execute(select(ServiceIncident))).scalars().all())
    opened = [row for row in rows if row.status == "open"]
    return {
        "open_total": len(opened),
        "critical": sum(row.severity == "critical" for row in opened),
        "warning": sum(row.severity == "warning" for row in opened),
        "resolved_total": sum(row.status == "resolved" for row in rows),
        "affected_services": sorted({row.service_key for row in opened}),
    }
