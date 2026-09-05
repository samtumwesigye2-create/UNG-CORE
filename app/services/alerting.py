import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alerting import Alert, AlertPolicy

SEVERITY_RANK = {"info": 0, "warning": 1, "degraded": 2, "critical": 3}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def serialize_policy(row: AlertPolicy) -> dict:
    return {"policy_id": row.policy_id, "policy_key": row.policy_key, "service_key": row.service_key, "minimum_severity": row.minimum_severity, "trigger_states": json.loads(row.trigger_states_json or "[]"), "escalation_minutes": json.loads(row.escalation_minutes_json or "[]"), "targets": json.loads(row.targets_json or "[]"), "enabled": row.enabled}


def serialize_alert(row: Alert) -> dict:
    return {"alert_id": row.alert_id, "policy_key": row.policy_key, "service_key": row.service_key, "severity": row.severity, "state": row.state, "status": row.status, "escalation_stage": row.escalation_stage, "incident_id": row.incident_id, "details": json.loads(row.details_json or "{}"), "opened_at": row.opened_at, "acknowledged_at": row.acknowledged_at, "acknowledged_by": row.acknowledged_by, "resolved_at": row.resolved_at}


async def upsert_policy(db: AsyncSession, policy_key: str, body) -> AlertPolicy:
    key = policy_key.lower()
    row = (await db.execute(select(AlertPolicy).where(AlertPolicy.policy_key == key))).scalar_one_or_none()
    values = {"service_key": body.service_key.upper() if body.service_key else None, "minimum_severity": body.minimum_severity.lower(), "trigger_states_json": json.dumps(body.trigger_states), "escalation_minutes_json": json.dumps(body.escalation_minutes), "targets_json": json.dumps(body.targets), "enabled": body.enabled}
    if row is None:
        row = AlertPolicy(policy_key=key, **values); db.add(row)
    else:
        for name, value in values.items(): setattr(row, name, value)
    await db.commit(); await db.refresh(row); return row


async def list_policies(db: AsyncSession) -> list[AlertPolicy]:
    return list((await db.execute(select(AlertPolicy).order_by(AlertPolicy.policy_key))).scalars().all())


async def list_alerts(db: AsyncSession, status_filter: str | None = None, service_key: str | None = None, limit: int = 100) -> list[Alert]:
    stmt = select(Alert).order_by(Alert.opened_at.desc()).limit(limit)
    if status_filter: stmt = stmt.where(Alert.status == status_filter)
    if service_key: stmt = stmt.where(Alert.service_key == service_key.upper())
    return list((await db.execute(stmt)).scalars().all())


async def evaluate_signal(db: AsyncSession, service_key: str, state: str, severity: str, details: dict, incident_id: str | None = None) -> list[Alert]:
    service_key = service_key.upper(); policies = await list_policies(db); changed: list[Alert] = []
    for policy in policies:
        if not policy.enabled or (policy.service_key and policy.service_key != service_key): continue
        if state not in json.loads(policy.trigger_states_json or "[]"): continue
        if SEVERITY_RANK.get(severity, 0) < SEVERITY_RANK.get(policy.minimum_severity, 1): continue
        dedupe = f"{policy.policy_key}:{service_key}:{state}"
        row = (await db.execute(select(Alert).where(Alert.dedupe_key == dedupe))).scalar_one_or_none()
        if row is None:
            row = Alert(dedupe_key=dedupe, policy_key=policy.policy_key, service_key=service_key, severity=severity, state=state, incident_id=incident_id, details_json=json.dumps(details)); db.add(row)
        elif row.status == "resolved":
            row.status = "open"; row.opened_at = _now(); row.resolved_at = None; row.acknowledged_at = None; row.acknowledged_by = None; row.escalation_stage = 0
        row.severity = severity; row.details_json = json.dumps(details); changed.append(row)
    await db.commit()
    for row in changed: await db.refresh(row)
    return changed


async def acknowledge_alert(db: AsyncSession, alert_id: str, actor: str) -> Alert:
    row = await db.get(Alert, alert_id)
    if row is None: raise LookupError("alert not found")
    row.status = "acknowledged"; row.acknowledged_at = _now(); row.acknowledged_by = actor
    await db.commit(); await db.refresh(row); return row


async def resolve_alert(db: AsyncSession, alert_id: str) -> Alert:
    row = await db.get(Alert, alert_id)
    if row is None: raise LookupError("alert not found")
    row.status = "resolved"; row.resolved_at = _now()
    await db.commit(); await db.refresh(row); return row


async def resolve_service_alerts(db: AsyncSession, service_key: str) -> int:
    rows = list((await db.execute(select(Alert).where(Alert.service_key == service_key.upper(), Alert.status != "resolved"))).scalars().all())
    now = _now()
    for row in rows: row.status = "resolved"; row.resolved_at = now
    if rows: await db.commit()
    return len(rows)


async def advance_escalations(db: AsyncSession) -> list[Alert]:
    open_alerts = list((await db.execute(select(Alert).where(Alert.status == "open"))).scalars().all()); policies = {p.policy_key: p for p in await list_policies(db)}; changed: list[Alert] = []; now = _now()
    for alert in open_alerts:
        policy = policies.get(alert.policy_key)
        if not policy: continue
        stages = json.loads(policy.escalation_minutes_json or "[]"); opened = alert.opened_at.replace(tzinfo=alert.opened_at.tzinfo or timezone.utc)
        target_stage = sum(1 for minute in stages if now >= opened + timedelta(minutes=minute))
        if target_stage > alert.escalation_stage: alert.escalation_stage = target_stage; changed.append(alert)
    if changed:
        await db.commit()
        for row in changed: await db.refresh(row)
    return changed


async def alert_summary(db: AsyncSession) -> dict:
    rows = await list_alerts(db, limit=500); active = [r for r in rows if r.status != "resolved"]
    return {"active_total": len(active), "open": sum(r.status == "open" for r in active), "acknowledged": sum(r.status == "acknowledged" for r in active), "critical": sum(r.severity == "critical" for r in active), "escalated": sum(r.escalation_stage > 0 for r in active)}
