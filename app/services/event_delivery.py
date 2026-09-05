import json
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_delivery import OutboundEventDelivery
from app.models.service_registry import RegisteredService


def _utcnow():
    return datetime.now(timezone.utc)


def serialize_delivery(row: OutboundEventDelivery) -> dict:
    return {
        "delivery_id": row.delivery_id,
        "event_type": row.event_type,
        "source_system": row.source_system,
        "target_system": row.target_system,
        "target_url": row.target_url,
        "correlation_id": row.correlation_id,
        "job_id": row.job_id,
        "payload": json.loads(row.payload_json or "{}"),
        "status": row.status,
        "attempts": row.attempts,
        "max_attempts": row.max_attempts,
        "last_status_code": row.last_status_code,
        "last_error": row.last_error,
        "created_at": row.created_at,
        "delivered_at": row.delivered_at,
    }


async def create_delivery(db: AsyncSession, *, event_type: str, target_system: str, payload: dict, correlation_id: str | None = None, job_id: str | None = None, max_attempts: int = 3) -> OutboundEventDelivery:
    system_key = target_system.upper()
    service = await db.scalar(select(RegisteredService).where(RegisteredService.service_key == system_key, RegisteredService.enabled.is_(True)))
    if service is None:
        raise LookupError(f"registered target system not found: {system_key}")
    row = OutboundEventDelivery(
        delivery_id=str(uuid.uuid4()), event_type=event_type, target_system=system_key,
        target_url=service.base_url.rstrip("/") + "/v1/events", correlation_id=correlation_id,
        job_id=job_id, payload_json=json.dumps(payload, separators=(",", ":"), sort_keys=True),
        max_attempts=max_attempts,
    )
    db.add(row)
    await db.commit(); await db.refresh(row)
    return row


async def deliver(db: AsyncSession, row: OutboundEventDelivery) -> OutboundEventDelivery:
    envelope = {
        "event_type": row.event_type,
        "source": row.source_system,
        "subject": row.target_system,
        "data": json.loads(row.payload_json or "{}"),
        "correlation_id": row.correlation_id,
    }
    row.attempts += 1
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(row.target_url, json=envelope, headers={"X-UNG-Delivery-ID": row.delivery_id})
        row.last_status_code = response.status_code
        if 200 <= response.status_code < 300:
            row.status = "delivered"; row.delivered_at = _utcnow(); row.last_error = None
        elif row.attempts >= row.max_attempts:
            row.status = "failed"; row.last_error = f"HTTP {response.status_code}"
        else:
            row.status = "retry_wait"; row.last_error = f"HTTP {response.status_code}"
    except Exception as exc:
        row.last_error = str(exc)
        row.status = "failed" if row.attempts >= row.max_attempts else "retry_wait"
    await db.commit(); await db.refresh(row)
    return row


async def publish_event(db: AsyncSession, **kwargs) -> OutboundEventDelivery:
    row = await create_delivery(db, **kwargs)
    return await deliver(db, row)


async def retry_delivery(db: AsyncSession, delivery_id: str) -> OutboundEventDelivery:
    row = await db.get(OutboundEventDelivery, delivery_id)
    if row is None: raise LookupError(delivery_id)
    if row.status == "delivered": raise ValueError("delivery already succeeded")
    if row.attempts >= row.max_attempts: row.attempts = 0
    row.status = "pending"
    await db.commit()
    return await deliver(db, row)


async def list_deliveries(db: AsyncSession, status: str | None = None, target_system: str | None = None, limit: int = 100):
    stmt = select(OutboundEventDelivery).order_by(OutboundEventDelivery.created_at.desc()).limit(limit)
    if status: stmt = stmt.where(OutboundEventDelivery.status == status)
    if target_system: stmt = stmt.where(OutboundEventDelivery.target_system == target_system.upper())
    return list((await db.scalars(stmt)).all())


async def delivery_summary(db: AsyncSession):
    result = {"pending": 0, "retry_wait": 0, "delivered": 0, "failed": 0, "total": 0}
    rows = (await db.execute(select(OutboundEventDelivery.status, func.count()).group_by(OutboundEventDelivery.status))).all()
    for status, count in rows:
        result[status] = count; result["total"] += count
    return result
