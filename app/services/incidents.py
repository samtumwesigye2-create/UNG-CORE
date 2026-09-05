import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import ServiceIncident
from app.schemas.contracts import RelayEnvelope
from app.services.relay import publish


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _severity(state: str) -> str:
    return "critical" if state == "offline" else "warning"


async def open_or_update_incident(db: AsyncSession, service_key: str, state: str, details: dict) -> ServiceIncident | None:
    if state not in {"degraded", "offline"}:
        return None

    dedupe_key = f"service-health:{service_key}:{state}"
    row = (await db.execute(select(ServiceIncident).where(ServiceIncident.dedupe_key == dedupe_key))).scalar_one_or_none()
    if row is None:
        row = ServiceIncident(
            incident_id=str(uuid.uuid4()),
            service_key=service_key,
            state=state,
            severity=_severity(state),
            status="open",
            dedupe_key=dedupe_key,
            details_json=json.dumps(details),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        try:
            await publish(RelayEnvelope(
                event_type="core.service.incident.opened",
                subject=service_key,
                data={
                    "incident_id": row.incident_id,
                    "service_key": service_key,
                    "state": state,
                    "severity": row.severity,
                    "details": details,
                },
                correlation_id=row.incident_id,
            ))
        except Exception:
            pass
        return row

    if row.status != "open":
        row.status = "open"
        row.resolved_at = None
    row.details_json = json.dumps(details)
    await db.commit()
    await db.refresh(row)
    return row


async def resolve_service_incidents(db: AsyncSession, service_key: str) -> list[ServiceIncident]:
    rows = list((await db.execute(select(ServiceIncident).where(ServiceIncident.service_key == service_key, ServiceIncident.status == "open"))).scalars().all())
    resolved: list[ServiceIncident] = []
    for row in rows:
        row.status = "resolved"
        row.resolved_at = _utcnow()
        resolved.append(row)
    if resolved:
        await db.commit()
        for row in resolved:
            try:
                await publish(RelayEnvelope(
                    event_type="core.service.incident.resolved",
                    subject=service_key,
                    data={
                        "incident_id": row.incident_id,
                        "service_key": service_key,
                        "previous_state": row.state,
                    },
                    correlation_id=row.incident_id,
                ))
            except Exception:
                pass
    return resolved
