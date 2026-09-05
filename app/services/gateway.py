import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gateway import CorrelatedEvent, GatewayRoute
from app.schemas.gateway import CorrelatedEventIn, GatewayRouteIn


def _dump(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


async def upsert_route(db: AsyncSession, body: GatewayRouteIn) -> GatewayRoute:
    result = await db.execute(select(GatewayRoute).where(GatewayRoute.route_key == body.route_key))
    row = result.scalar_one_or_none()
    if row is None:
        row = GatewayRoute(route_key=body.route_key)
        db.add(row)
    row.system_key = body.system_key.upper()
    row.public_path = body.public_path
    row.upstream_path = body.upstream_path
    row.methods_json = _dump([method.upper() for method in body.methods])
    row.auth_policy = body.auth_policy
    row.rate_limit_per_minute = body.rate_limit_per_minute
    row.enabled = body.enabled
    await db.commit()
    await db.refresh(row)
    return row


async def list_routes(db: AsyncSession, system_key: str | None = None) -> list[GatewayRoute]:
    stmt = select(GatewayRoute)
    if system_key:
        stmt = stmt.where(GatewayRoute.system_key == system_key.upper())
    result = await db.execute(stmt.order_by(GatewayRoute.route_key))
    return list(result.scalars().all())


async def record_correlated_event(db: AsyncSession, body: CorrelatedEventIn) -> CorrelatedEvent:
    row = CorrelatedEvent(
        event_type=body.event_type,
        source_system_key=body.source_system_key.upper(),
        subject=body.subject,
        severity=body.severity,
        incident_id=body.incident_id,
        parent_correlation_id=body.parent_correlation_id,
        payload_json=_dump(body.payload),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_correlated_events(db: AsyncSession, correlation_id: str | None = None, incident_id: str | None = None, limit: int = 100) -> list[CorrelatedEvent]:
    stmt = select(CorrelatedEvent)
    if correlation_id:
        stmt = stmt.where((CorrelatedEvent.correlation_id == correlation_id) | (CorrelatedEvent.parent_correlation_id == correlation_id))
    if incident_id:
        stmt = stmt.where(CorrelatedEvent.incident_id == incident_id)
    result = await db.execute(stmt.order_by(CorrelatedEvent.occurred_at.desc()).limit(limit))
    return list(result.scalars().all())


def serialize_route(row: GatewayRoute) -> dict:
    return {
        "route_id": row.route_id,
        "route_key": row.route_key,
        "system_key": row.system_key,
        "public_path": row.public_path,
        "upstream_path": row.upstream_path,
        "methods": json.loads(row.methods_json),
        "auth_policy": row.auth_policy,
        "rate_limit_per_minute": row.rate_limit_per_minute,
        "enabled": row.enabled,
        "updated_at": row.updated_at,
    }


def serialize_correlated_event(row: CorrelatedEvent) -> dict:
    return {
        "correlation_id": row.correlation_id,
        "event_type": row.event_type,
        "source_system_key": row.source_system_key,
        "subject": row.subject,
        "severity": row.severity,
        "incident_id": row.incident_id,
        "parent_correlation_id": row.parent_correlation_id,
        "payload": json.loads(row.payload_json),
        "occurred_at": row.occurred_at,
    }
