import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.core.config import settings
from app.db.session import get_db
from app.schemas.contracts import AuditEventIn, AuditEventOut, Principal, RelayEnvelope
from app.schemas.control_plane import ConfigurationIn, DependencyIn, OrganizationIn, SystemIn
from app.schemas.heartbeat import HeartbeatIn, ServiceHealthOut
from app.schemas.incidents import IncidentOut, IncidentSummaryOut
from app.schemas.registry import ServiceDiscoveryOut, ServiceRegistrationIn, ServiceRegistrationOut
from app.schemas.workflows import WorkflowExecutionOut, WorkflowStartIn
from app.services.audit import record_audit
from app.services.control_center import control_center_snapshot, dependency_impact
from app.services.control_plane import add_dependency, list_configuration, list_dependencies, list_organizations, list_systems, serialize_configuration, serialize_dependency, serialize_organization, serialize_system, upsert_configuration, upsert_organization, upsert_system
from app.services.heartbeat import get_health_snapshot, record_heartbeat
from app.services.incident_feed import incident_summary, list_incidents, serialize_incident
from app.services.relay import publish
from app.services.registry import get_service, list_services, serialize, upsert_service
from app.services.workflows import get_workflow, list_workflows, serialize_workflow, start_workflow

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

@router.get("/v1/incidents/summary", response_model=IncidentSummaryOut)
async def incidents_summary(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.incidents.read"))):
    return IncidentSummaryOut(**await incident_summary(db))

@router.get("/v1/incidents", response_model=list[IncidentOut])
async def incidents(status_filter: str | None = Query(default=None, alias="status"), service_key: str | None = None, limit: int = Query(default=100, ge=1, le=500), db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.incidents.read"))):
    if status_filter not in {None, "open", "resolved"}:
        raise HTTPException(status_code=400, detail="status must be open or resolved")
    return [IncidentOut(**serialize_incident(row)) for row in await list_incidents(db, status_filter, service_key, limit)]

@router.put("/v1/services/{service_key}", response_model=ServiceRegistrationOut)
async def register_service(service_key: str, body: ServiceRegistrationIn, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.registry.write"))):
    if service_key.upper() != body.service_key.upper():
        raise HTTPException(status_code=400, detail="service_key path/body mismatch")
    row = await upsert_service(db, body.model_copy(update={"service_key": service_key.upper()}))
    return ServiceRegistrationOut(**serialize(row))

@router.get("/v1/services", response_model=list[ServiceRegistrationOut])
async def services(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.registry.read"))):
    return [ServiceRegistrationOut(**serialize(row)) for row in await list_services(db)]

@router.get("/v1/services/health/snapshot", response_model=list[ServiceHealthOut])
async def service_health_snapshot(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.registry.read"))):
    return [ServiceHealthOut(**item) for item in await get_health_snapshot(db)]

@router.post("/v1/services/{service_key}/heartbeat", status_code=status.HTTP_202_ACCEPTED)
async def heartbeat_service(service_key: str, body: HeartbeatIn, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.heartbeat.write"))):
    try:
        row = await record_heartbeat(db, service_key, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="service not registered") from exc
    return {"status": "accepted", "service_key": row.service_key, "last_seen_at": row.last_seen_at, "actor": principal.subject}

@router.get("/v1/services/{service_key}", response_model=ServiceDiscoveryOut)
async def discover_service(service_key: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.registry.read"))):
    row = await get_service(db, service_key.upper())
    if row is None or not row.enabled:
        raise HTTPException(status_code=404, detail="service not registered")
    data = serialize(row)
    return ServiceDiscoveryOut(service_key=data["service_key"], base_url=data["base_url"], version=data["version"], capabilities=data["capabilities"])

@router.post("/v1/workflows", response_model=WorkflowExecutionOut, status_code=status.HTTP_202_ACCEPTED)
async def create_workflow(body: WorkflowStartIn, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.workflows.execute"))):
    return WorkflowExecutionOut(**serialize_workflow(await start_workflow(db, body, principal.subject)))

@router.get("/v1/workflows", response_model=list[WorkflowExecutionOut])
async def workflows(limit: int = Query(default=100, ge=1, le=500), db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.workflows.read"))):
    return [WorkflowExecutionOut(**serialize_workflow(row)) for row in await list_workflows(db, limit)]

@router.get("/v1/workflows/{execution_id}", response_model=WorkflowExecutionOut)
async def workflow(execution_id: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.workflows.read"))):
    row = await get_workflow(db, execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="workflow execution not found")
    return WorkflowExecutionOut(**serialize_workflow(row))

@router.put("/v1/organizations/{organization_key}")
async def register_organization(organization_key: str, body: OrganizationIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.control.write"))):
    if organization_key.upper() != body.organization_key.upper():
        raise HTTPException(status_code=400, detail="organization_key path/body mismatch")
    return serialize_organization(await upsert_organization(db, body.model_copy(update={"organization_key": organization_key.upper()})))

@router.get("/v1/organizations")
async def organizations(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.control.read"))):
    return [serialize_organization(row) for row in await list_organizations(db)]

@router.put("/v1/systems/{system_key}")
async def register_system(system_key: str, body: SystemIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.control.write"))):
    if system_key.upper() != body.system_key.upper():
        raise HTTPException(status_code=400, detail="system_key path/body mismatch")
    return serialize_system(await upsert_system(db, body.model_copy(update={"system_key": system_key.upper()})))

@router.get("/v1/systems")
async def systems(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.control.read"))):
    return [serialize_system(row) for row in await list_systems(db)]

@router.put("/v1/systems/{system_key}/dependencies")
async def register_dependency(system_key: str, body: DependencyIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.control.write"))):
    if system_key.upper() == body.depends_on_system_key.upper():
        raise HTTPException(status_code=400, detail="system cannot depend on itself")
    return serialize_dependency(await add_dependency(db, system_key, body))

@router.get("/v1/dependencies")
async def dependencies(system_key: str | None = None, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.control.read"))):
    return [serialize_dependency(row) for row in await list_dependencies(db, system_key)]

@router.put("/v1/config/{scope}/{config_key}")
async def set_configuration(scope: str, config_key: str, body: ConfigurationIn, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.config.write"))):
    return serialize_configuration(await upsert_configuration(db, scope, config_key, body, principal.subject))

@router.get("/v1/config/{scope}")
async def configuration(scope: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.config.read"))):
    return [serialize_configuration(row) for row in await list_configuration(db, scope)]

@router.get("/v1/control-center/status")
async def control_center_status(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.control.read"))):
    return await control_center_snapshot(db)

@router.get("/v1/control-center/impact/{system_key}")
async def control_center_impact(system_key: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.control.read"))):
    return await dependency_impact(db, system_key)
