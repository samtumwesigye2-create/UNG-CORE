from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.control_plane import SystemDependency, SystemRegistry
from app.models.service_heartbeat import ServiceHeartbeat


async def control_center_snapshot(db: AsyncSession) -> dict:
    systems = list((await db.execute(select(SystemRegistry))).scalars().all())
    heartbeats = list((await db.execute(select(ServiceHeartbeat))).scalars().all())
    heartbeat_by_key = {row.service_key.upper(): row for row in heartbeats}

    rows = []
    healthy = degraded = unavailable = 0
    for system in systems:
        hb = heartbeat_by_key.get(system.system_key.upper())
        state = hb.reported_status if hb is not None else ("unknown" if system.enabled else "disabled")
        if state in {"ok", "healthy", "up"}:
            healthy += 1
        elif state in {"down", "unavailable", "critical"}:
            unavailable += 1
        else:
            degraded += 1
        rows.append({
            "system_key": system.system_key,
            "display_name": system.display_name,
            "criticality": system.criticality,
            "enabled": system.enabled,
            "status": state,
            "last_seen_at": hb.last_seen_at if hb is not None else None,
        })

    return {
        "total_systems": len(systems),
        "healthy": healthy,
        "degraded_or_unknown": degraded,
        "unavailable": unavailable,
        "systems": rows,
    }


async def dependency_impact(db: AsyncSession, system_key: str) -> dict:
    key = system_key.upper()
    deps = list((await db.execute(select(SystemDependency))).scalars().all())
    direct = sorted({d.system_key for d in deps if d.depends_on_system_key.upper() == key})
    impacted = set(direct)
    frontier = list(direct)
    while frontier:
        current = frontier.pop()
        for dep in deps:
            if dep.depends_on_system_key.upper() == current.upper() and dep.system_key not in impacted:
                impacted.add(dep.system_key)
                frontier.append(dep.system_key)
    return {"system_key": key, "direct_dependents": direct, "all_impacted_systems": sorted(impacted), "impact_count": len(impacted)}


async def ecosystem_topology(db: AsyncSession) -> dict:
    systems = list((await db.execute(select(SystemRegistry).order_by(SystemRegistry.system_key))).scalars().all())
    dependencies = list((await db.execute(select(SystemDependency).order_by(SystemDependency.system_key, SystemDependency.depends_on_system_key))).scalars().all())
    nodes = [
        {
            "id": system.system_key,
            "label": system.display_name,
            "criticality": system.criticality,
            "enabled": system.enabled,
            "lifecycle_status": system.lifecycle_status,
        }
        for system in systems
    ]
    edges = [
        {
            "source": dependency.system_key,
            "target": dependency.depends_on_system_key,
            "type": dependency.dependency_type,
            "required": dependency.required,
        }
        for dependency in dependencies
    ]
    return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}
