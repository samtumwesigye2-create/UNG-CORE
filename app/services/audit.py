import json, uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditEvent
from app.schemas.contracts import AuditEventIn

async def record_audit(db: AsyncSession, event: AuditEventIn) -> AuditEvent:
    row = AuditEvent(
        event_id=str(uuid.uuid4()), actor_id=event.actor_id, action=event.action,
        resource_type=event.resource_type, resource_id=event.resource_id,
        payload_json=json.dumps(event.payload, separators=(",", ":"), sort_keys=True),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def serialize_audit(row: AuditEvent) -> dict:
    return {
        "event_id": row.event_id,
        "actor_id": row.actor_id,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "payload": json.loads(row.payload_json or "{}"),
        "occurred_at": row.occurred_at,
    }


async def list_audit_events(db: AsyncSession, actor_id: str | None = None, action: str | None = None, resource_type: str | None = None, resource_id: str | None = None, correlation_id: str | None = None, limit: int = 100) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if resource_type:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AuditEvent.resource_id == resource_id)
    rows = list((await db.execute(stmt)).scalars().all())
    if correlation_id:
        rows = [r for r in rows if json.loads(r.payload_json or "{}").get("correlation_id") == correlation_id]
    return rows


async def audit_summary(db: AsyncSession) -> dict:
    rows = await list_audit_events(db, limit=500)
    return {
        "total_recent": len(rows),
        "unique_actors": len({r.actor_id for r in rows}),
        "unique_actions": len({r.action for r in rows}),
        "unique_resources": len({(r.resource_type, r.resource_id) for r in rows}),
    }
