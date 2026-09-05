import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.service_heartbeat import ServiceHeartbeat
from app.models.service_registry import RegisteredService
from app.schemas.heartbeat import HeartbeatIn

DEGRADED_AFTER_SECONDS = 90
OFFLINE_AFTER_SECONDS = 180


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def record_heartbeat(db: AsyncSession, service_key: str, body: HeartbeatIn) -> ServiceHeartbeat:
    key = service_key.upper()
    registered = (await db.execute(select(RegisteredService).where(RegisteredService.service_key == key))).scalar_one_or_none()
    if registered is None:
        raise LookupError("service not registered")

    row = (await db.execute(select(ServiceHeartbeat).where(ServiceHeartbeat.service_key == key))).scalar_one_or_none()
    values = {
        "reported_status": body.status,
        "latency_ms": body.latency_ms,
        "details_json": json.dumps(body.details),
        "last_seen_at": _utcnow(),
    }
    if row is None:
        row = ServiceHeartbeat(service_key=key, **values)
        db.add(row)
    else:
        for name, value in values.items():
            setattr(row, name, value)

    await db.commit()
    await db.refresh(row)
    return row


def classify_health(service: RegisteredService, heartbeat: ServiceHeartbeat | None) -> dict:
    if not service.enabled:
        return {"service_key": service.service_key, "state": "disabled", "reported_status": None, "latency_ms": None, "last_seen_at": None, "age_seconds": None, "details": {}}
    if heartbeat is None:
        return {"service_key": service.service_key, "state": "unknown", "reported_status": None, "latency_ms": None, "last_seen_at": None, "age_seconds": None, "details": {}}

    seen = heartbeat.last_seen_at
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    age = max(0, int((_utcnow() - seen).total_seconds()))
    if age >= OFFLINE_AFTER_SECONDS:
        state = "offline"
    elif heartbeat.reported_status == "degraded" or age >= DEGRADED_AFTER_SECONDS:
        state = "degraded"
    else:
        state = "healthy"

    return {
        "service_key": service.service_key,
        "state": state,
        "reported_status": heartbeat.reported_status,
        "latency_ms": heartbeat.latency_ms,
        "last_seen_at": heartbeat.last_seen_at,
        "age_seconds": age,
        "details": json.loads(heartbeat.details_json or "{}"),
    }


async def get_health_snapshot(db: AsyncSession) -> list[dict]:
    services = list((await db.execute(select(RegisteredService).order_by(RegisteredService.service_key))).scalars().all())
    heartbeats = list((await db.execute(select(ServiceHeartbeat))).scalars().all())
    by_key = {row.service_key: row for row in heartbeats}
    return [classify_health(service, by_key.get(service.service_key)) for service in services]
