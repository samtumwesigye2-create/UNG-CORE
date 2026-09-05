from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import current_principal, require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.control_plane import list_systems, serialize_system

router = APIRouter(prefix="/v1/operator", tags=["operator"])


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
    permissions = set(principal.permissions)
    is_admin = "ung.core.admin" in permissions

    def allowed(permission: str) -> bool:
        return is_admin or permission in permissions

    return {
        "control_center": allowed("ung.core.control.read"),
        "registry_read": allowed("ung.core.registry.read"),
        "registry_write": allowed("ung.core.registry.write"),
        "incidents": allowed("ung.core.incidents.read"),
        "approvals": allowed("ung.core.approvals.read"),
        "jobs": allowed("ung.core.jobs.read"),
        "audit": allowed("ung.core.audit.read"),
        "configuration_read": allowed("ung.core.config.read"),
        "configuration_write": allowed("ung.core.config.write"),
        "workflow_execute": allowed("ung.core.workflows.execute"),
        "event_publish": allowed("ung.core.events.publish"),
        "recovery": allowed("ung.core.recovery.write"),
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
    return {"count": len(systems), "systems": systems}


@router.get("/workspace")
async def operator_workspace(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.control.read")),
):
    systems_payload = await operator_systems(db=db, _=principal)
    permissions = set(principal.permissions)
    is_admin = "ung.core.admin" in permissions
    return {
        "operator": {
            "subject": principal.subject,
            "display_name": principal.display_name,
            "roles": sorted(set(principal.roles)),
        },
        "navigation": {
            "operations": is_admin or "ung.core.control.read" in permissions,
            "approvals": is_admin or "ung.core.approvals.read" in permissions,
            "jobs": is_admin or "ung.core.jobs.read" in permissions,
            "audit": is_admin or "ung.core.audit.read" in permissions,
            "configuration": is_admin or "ung.core.config.read" in permissions,
            "recovery": is_admin or "ung.core.recovery.write" in permissions,
        },
        "systems": systems_payload["systems"],
        "system_count": systems_payload["count"],
    }
