from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import current_principal, require_permission
from app.core.hardening import production_readiness
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.alerting import alert_summary
from app.services.approvals import approval_summary
from app.services.audit import audit_summary
from app.services.command_history import command_summary
from app.services.control_plane import list_systems, serialize_system
from app.services.event_delivery import delivery_summary
from app.services.incident_feed import incident_summary
from app.services.routing import gateway_routing_status
from app.services.scheduler import job_summary
from app.services.security_resilience import resilience_summary
from app.services.telemetry import fleet_health_summary

router = APIRouter(prefix="/v1/operator", tags=["operator"])


def _allowed(principal: Principal, permission: str) -> bool:
    permissions = set(principal.permissions)
    return "ung.core.admin" in permissions or permission in permissions


@router.get("/me")
async def operator_me(principal: Principal = Depends(current_principal)):
    return {
        "subject": principal.subject,
        "display_name": principal.display_name,
        "roles": sorted(set(principal.roles)),
        "permissions": sorted(set(principal.permissions)),
        "is_core_admin": "ung.core.admin" in principal.permissions,
    }


@router.get("/capabilities")
async def operator_capabilities(principal: Principal = Depends(current_principal)):
    return {
        "control_center": _allowed(principal, "ung.core.control.read"),
        "registry_read": _allowed(principal, "ung.core.registry.read"),
        "registry_write": _allowed(principal, "ung.core.registry.write"),
        "incidents": _allowed(principal, "ung.core.incidents.read"),
        "approvals": _allowed(principal, "ung.core.approvals.read"),
        "jobs": _allowed(principal, "ung.core.jobs.read"),
        "audit": _allowed(principal, "ung.core.audit.read"),
        "configuration_read": _allowed(principal, "ung.core.config.read"),
        "configuration_write": _allowed(principal, "ung.core.config.write"),
        "workflow_execute": _allowed(principal, "ung.core.workflows.execute"),
        "event_publish": _allowed(principal, "ung.core.events.publish"),
        "recovery": _allowed(principal, "ung.core.recovery.write"),
    }


@router.get("/systems")
async def operator_systems(
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.control.read")),
):
    rows = await list_systems(db)
    systems = []
    for row in rows:
        item = serialize_system(row)
        if not item.get("enabled", False):
            continue
        base_url = item.get("base_url")
        systems.append(
            {
                "system_key": item["system_key"],
                "display_name": item["display_name"],
                "owner_organization_key": item["owner_organization_key"],
                "lifecycle_status": item["lifecycle_status"],
                "criticality": item["criticality"],
                "capabilities": item.get("capabilities", []),
                "launchable": bool(base_url),
                "launch_url": base_url if base_url else None,
            }
        )
    systems.sort(key=lambda item: (item["display_name"].lower(), item["system_key"]))
    return {"count": len(systems), "systems": systems}


@router.get("/workspace")
async def operator_workspace(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.control.read")),
):
    systems_payload = await operator_systems(db=db, _=principal)
    return {
        "operator": {
            "subject": principal.subject,
            "display_name": principal.display_name,
            "roles": sorted(set(principal.roles)),
        },
        "navigation": {
            "operations": True,
            "incidents": _allowed(principal, "ung.core.incidents.read"),
            "approvals": _allowed(principal, "ung.core.approvals.read"),
            "jobs": _allowed(principal, "ung.core.jobs.read"),
            "audit": _allowed(principal, "ung.core.audit.read"),
            "configuration": _allowed(principal, "ung.core.config.read"),
            "recovery": _allowed(principal, "ung.core.recovery.write"),
        },
        "systems": systems_payload["systems"],
        "system_count": systems_payload["count"],
    }


@router.get("/dashboard")
async def operator_dashboard(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.control.read")),
):
    """Permission-aware operational summary for the human Control Center."""
    dashboard = {
        "readiness": production_readiness(),
        "gateway": await gateway_routing_status(db),
        "telemetry": await fleet_health_summary(db),
        "alerts": await alert_summary(db),
        "event_delivery": await delivery_summary(db),
    }

    if _allowed(principal, "ung.core.incidents.read"):
        dashboard["incidents"] = await incident_summary(db)
    if _allowed(principal, "ung.core.approvals.read"):
        dashboard["approvals"] = await approval_summary(db)
    if _allowed(principal, "ung.core.jobs.read"):
        dashboard["jobs"] = await job_summary(db)
    if _allowed(principal, "ung.core.audit.read"):
        dashboard["audit"] = await audit_summary(db)
        dashboard["commands"] = await command_summary(db)
    if _allowed(principal, "ung.core.recovery.write"):
        dashboard["resilience"] = await resilience_summary(db)

    return dashboard
