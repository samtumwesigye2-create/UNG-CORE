import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.core.config import settings
from app.db.session import get_db
from app.schemas.contracts import AuditEventIn, AuditEventOut, Principal, RelayEnvelope
from app.schemas.heartbeat import HeartbeatIn, ServiceHealthOut
from app.schemas.registry import ServiceDiscoveryOut, ServiceRegistrationIn, ServiceRegistrationOut
from app.services.audit import record_audit
from app.services.heartbeat import get_health_snapshot, record_heartbeat
from app.services.relay import publish
from app.services.registry import get_service, list_services, serialize, upsert_service

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
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"status": "not_ready", "checks": checks}) from exc
    return {"status": "ready", "environment": settings.environment, "checks": checks}

@router.post("/v1/audit/events", response_model=AuditEventOut)
async def create_audit_event(body: AuditEventIn, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.audit.write"))):
    if body.actor_id != principal.subject and "ung.core.audit.write.any" not in principal.permissions:
        body = body.model_copy(update={"actor_id": principal.subject})
    row = await record_audit(db, body)
    return AuditEventOut(event_id=row.event_id, actor_id=row.actor_id, action=row.action, resource_type=row.resource_type, resource_id=row.resource_id, payload=json.loads(row.payload_json), occurred_at=row.occurred_at)

@router.post("/v1/events/publish", status_code=status.HTTP_202_ACCEPTED)
async def publish_event(envelope: RelayEnvelope, principal: Principal = Depends(require_permission("ung.core.events.publish"))):
    envelope = envelope.model_copy(update={"source": settings.app_name})
    try:
        await publish(envelope)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Data Relay unavailable") from exc
    return {"status": "accepted", "event_type": envelope.event_type, "subject": envelope.subject, "actor": principal.subject}

@router.put("/v1/services/{service_key}", response_model=ServiceRegistrationOut)
async def register_service(service_key: str, body: ServiceRegistrationIn, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.registry.write"))):
    if service_key.upper() != body.service_key.upper():
        raise HTTPException(status_code=400, detail="service_key path/body mismatch")
    body = body.model_copy(update={"service_key": service_key.upper()})
    row = await upsert_service(db, body)
    return ServiceRegistrationOut(**serialize(row))

@router.get("/v1/services", response_model=list[ServiceRegistrationOut])
async def services(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.registry.read"))):
    return [ServiceRegistrationOut(**serialize(row)) for row in await list_services(db)]

@router.get("/v1/services/{service_key}", response_model=ServiceDiscoveryOut)
async def discover_service(service_key: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.registry.read"))):
    row = await get_service(db, service_key.upper())
    if row is None or not row.enabled:
        raise HTTPException(status_code=404, detail="service not registered")
    data = serialize(row)
    return ServiceDiscoveryOut(service_key=data["service_key"], base_url=data["base_url"], version=data["version"], capabilities=data["capabilities"])

@router.post("/v1/services/{service_key}/heartbeat", status_code=status.HTTP_202_ACCEPTED)
async def heartbeat_service(service_key: str, body: HeartbeatIn, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.heartbeat.write"))):
    try:
        row = await record_heartbeat(db, service_key, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="service not registered") from exc
    return {"status": "accepted", "service_key": row.service_key, "last_seen_at": row.last_seen_at, "actor": principal.subject}

@router.get("/v1/services/health/snapshot", response_model=list[ServiceHealthOut])
async def service_health_snapshot(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.registry.read"))):
    return [ServiceHealthOut(**item) for item in await get_health_snapshot(db)]
