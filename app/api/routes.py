import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.core.config import settings
from app.db.session import get_db
from app.schemas.contracts import AuditEventIn, AuditEventOut, Principal, RelayEnvelope
from app.services.audit import record_audit
from app.services.relay import publish

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name, "version": settings.service_version}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    checks = {"database": "down", "iam": "configured" if settings.iam_base_url else "missing", "relay": "configured" if settings.data_relay_base_url else "missing"}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "checks": checks},
        ) from exc
    return {"status": "ready", "environment": settings.environment, "checks": checks}


@router.post("/v1/audit/events", response_model=AuditEventOut)
async def create_audit_event(
    body: AuditEventIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.audit.write")),
):
    if body.actor_id != principal.subject and "ung.core.audit.write.any" not in principal.permissions:
        body = body.model_copy(update={"actor_id": principal.subject})
    row = await record_audit(db, body)
    return AuditEventOut(
        event_id=row.event_id,
        actor_id=row.actor_id,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        payload=json.loads(row.payload_json),
        occurred_at=row.occurred_at,
    )


@router.post("/v1/events/publish", status_code=status.HTTP_202_ACCEPTED)
async def publish_event(
    envelope: RelayEnvelope,
    principal: Principal = Depends(require_permission("ung.core.events.publish")),
):
    envelope = envelope.model_copy(update={"source": settings.app_name})
    try:
        await publish(envelope)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Data Relay unavailable") from exc
    return {"status": "accepted", "event_type": envelope.event_type, "subject": envelope.subject, "actor": principal.subject}
