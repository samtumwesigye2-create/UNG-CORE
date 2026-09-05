import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service_heartbeat import ServiceHeartbeat
from app.models.service_registry import RegisteredService
from app.models.telemetry import ServiceTelemetrySample
from app.services.heartbeat import DEGRADED_AFTER_SECONDS, OFFLINE_AFTER_SECONDS, classify_health


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def record_telemetry_sample(db: AsyncSession, service_key: str) -> ServiceTelemetrySample:
    key = service_key.upper()
    service = (await db.execute(select(RegisteredService).where(RegisteredService.service_key == key))).scalar_one_or_none()
    if service is None:
        raise LookupError("service not registered")
    heartbeat = (await db.execute(select(ServiceHeartbeat).where(ServiceHeartbeat.service_key == key))).scalar_one_or_none()
    health = classify_health(service, heartbeat)
    row = ServiceTelemetrySample(
        service_key=key,
        status=health["state"],
        latency_ms=health["latency_ms"],
        details_json=json.dumps({"reported_status": health["reported_status"], "age_seconds": health["age_seconds"], "details": health["details"]}),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_telemetry(db: AsyncSession, service_key: str | None = None, limit: int = 200) -> list[ServiceTelemetrySample]:
    stmt = select(ServiceTelemetrySample)
    if service_key:
        stmt = stmt.where(ServiceTelemetrySample.service_key == service_key.upper())
    stmt = stmt.order_by(ServiceTelemetrySample.observed_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def service_sla_summary(db: AsyncSession, service_key: str, window_minutes: int = 60) -> dict:
    key = service_key.upper()
    cutoff = _utcnow() - timedelta(minutes=window_minutes)
    rows = list((await db.execute(select(ServiceTelemetrySample).where(ServiceTelemetrySample.service_key == key, ServiceTelemetrySample.observed_at >= cutoff))).scalars().all())
    if not rows:
        return {"service_key": key, "window_minutes": window_minutes, "samples": 0, "availability_pct": None, "average_latency_ms": None, "state": "unknown"}
    healthy = sum(1 for row in rows if row.status == "healthy")
    latencies = [row.latency_ms for row in rows if row.latency_ms is not None]
    availability = round((healthy / len(rows)) * 100, 3)
    average_latency = round(sum(latencies) / len(latencies), 2) if latencies else None
    if availability >= 99.9:
        state = "meeting_sla"
    elif availability >= 99.0:
        state = "at_risk"
    else:
        state = "breached"
    return {"service_key": key, "window_minutes": window_minutes, "samples": len(rows), "availability_pct": availability, "average_latency_ms": average_latency, "state": state}


async def fleet_health_summary(db: AsyncSession) -> dict:
    services = list((await db.execute(select(RegisteredService).where(RegisteredService.enabled.is_(True)))).scalars().all())
    heartbeats = list((await db.execute(select(ServiceHeartbeat))).scalars().all())
    by_key = {row.service_key: row for row in heartbeats}
    states = [classify_health(service, by_key.get(service.service_key))["state"] for service in services]
    return {
        "total": len(states),
        "healthy": states.count("healthy"),
        "degraded": states.count("degraded"),
        "offline": states.count("offline"),
        "unknown": states.count("unknown"),
        "thresholds": {"degraded_after_seconds": DEGRADED_AFTER_SECONDS, "offline_after_seconds": OFFLINE_AFTER_SECONDS},
    }


def serialize_telemetry(row: ServiceTelemetrySample) -> dict:
    return {
        "sample_id": row.sample_id,
        "service_key": row.service_key,
        "status": row.status,
        "latency_ms": row.latency_ms,
        "availability_pct": row.availability_pct,
        "details": json.loads(row.details_json or "{}"),
        "observed_at": row.observed_at,
    }
