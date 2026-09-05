import json, uuid
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
