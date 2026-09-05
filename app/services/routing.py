import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gateway import CorrelatedEvent, GatewayRoute
from app.models.incident import ServiceIncident
from app.models.routing import EventRoutingRule

SEVERITY = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


async def upsert_rule(db: AsyncSession, rule_key: str, event_type: str, source_system_key: str | None, minimum_severity: str, target_systems: list[str], create_incident: bool, enabled: bool = True):
    result = await db.execute(select(EventRoutingRule).where(EventRoutingRule.rule_key == rule_key))
    row = result.scalar_one_or_none()
    if row is None:
        row = EventRoutingRule(rule_key=rule_key)
        db.add(row)
    row.event_type = event_type
    row.source_system_key = source_system_key.upper() if source_system_key else None
    row.minimum_severity = minimum_severity
    row.target_systems_json = json.dumps([x.upper() for x in target_systems])
    row.create_incident = create_incident
    row.enabled = enabled
    await db.commit()
    await db.refresh(row)
    return row


async def list_rules(db: AsyncSession):
    result = await db.execute(select(EventRoutingRule).order_by(EventRoutingRule.rule_key))
    return list(result.scalars().all())


def serialize_rule(row: EventRoutingRule):
    return {"rule_id": row.rule_id, "rule_key": row.rule_key, "event_type": row.event_type, "source_system_key": row.source_system_key, "minimum_severity": row.minimum_severity, "target_systems": json.loads(row.target_systems_json), "create_incident": row.create_incident, "enabled": row.enabled}


async def correlate_and_route(db: AsyncSession, event: CorrelatedEvent) -> dict:
    rules = await list_rules(db)
    matched = []
    targets = set()
    incident_id = event.incident_id
    for rule in rules:
        if not rule.enabled or rule.event_type != event.event_type:
            continue
        if rule.source_system_key and rule.source_system_key != event.source_system_key:
            continue
        if SEVERITY.get(event.severity, 0) < SEVERITY.get(rule.minimum_severity, 0):
            continue
        matched.append(rule.rule_key)
        targets.update(json.loads(rule.target_systems_json))
        if rule.create_incident and not incident_id:
            dedupe = f"event:{event.source_system_key}:{event.event_type}:{event.subject}"
            existing = (await db.execute(select(ServiceIncident).where(ServiceIncident.dedupe_key == dedupe, ServiceIncident.status == "open"))).scalar_one_or_none()
            if existing is None:
                existing = ServiceIncident(incident_id=str(uuid.uuid4()), service_key=event.source_system_key, state="event_correlated", severity=event.severity, status="open", dedupe_key=dedupe, details_json=json.dumps({"correlation_id": event.correlation_id, "event_type": event.event_type, "subject": event.subject}))
                db.add(existing)
                await db.flush()
            incident_id = existing.incident_id
            event.incident_id = incident_id
    await db.commit()
    return {"correlation_id": event.correlation_id, "incident_id": incident_id, "matched_rules": matched, "target_systems": sorted(targets)}


async def gateway_routing_status(db: AsyncSession) -> dict:
    routes = list((await db.execute(select(GatewayRoute))).scalars().all())
    enabled = [r for r in routes if r.enabled]
    by_system = {}
    for route in enabled:
        by_system[route.system_key] = by_system.get(route.system_key, 0) + 1
    return {"total_routes": len(routes), "enabled_routes": len(enabled), "disabled_routes": len(routes) - len(enabled), "routes_by_system": by_system}
