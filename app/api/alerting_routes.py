from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.alerting import acknowledge_alert, advance_escalations, alert_summary, evaluate_signal, list_alerts, list_policies, resolve_alert, serialize_alert, serialize_policy, upsert_policy

router = APIRouter(prefix="/v1/alerting", tags=["alerting"])


class AlertPolicyIn(BaseModel):
    service_key: str | None = None
    minimum_severity: str = "warning"
    trigger_states: list[str] = Field(default_factory=lambda: ["degraded", "offline"])
    escalation_minutes: list[int] = Field(default_factory=lambda: [5, 15, 30])
    targets: list[str] = Field(default_factory=list)
    enabled: bool = True


class AlertSignalIn(BaseModel):
    service_key: str
    state: str
    severity: str = "warning"
    incident_id: str | None = None
    details: dict = Field(default_factory=dict)


@router.put("/policies/{policy_key}")
async def set_policy(policy_key: str, body: AlertPolicyIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.alerting.write"))):
    return serialize_policy(await upsert_policy(db, policy_key, body))


@router.get("/policies")
async def policies(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.alerting.read"))):
    return [serialize_policy(row) for row in await list_policies(db)]


@router.post("/evaluate")
async def evaluate(body: AlertSignalIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.alerting.execute"))):
    return [serialize_alert(row) for row in await evaluate_signal(db, body.service_key, body.state, body.severity, body.details, body.incident_id)]


@router.get("/alerts")
async def alerts(status: str | None = None, service_key: str | None = None, limit: int = Query(default=100, ge=1, le=500), db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.alerting.read"))):
    return [serialize_alert(row) for row in await list_alerts(db, status, service_key, limit)]


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge(alert_id: str, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.alerting.ack"))):
    try:
        return serialize_alert(await acknowledge_alert(db, alert_id, principal.subject))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="alert not found") from exc


@router.post("/alerts/{alert_id}/resolve")
async def resolve(alert_id: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.alerting.resolve"))):
    try:
        return serialize_alert(await resolve_alert(db, alert_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="alert not found") from exc


@router.post("/escalations/run")
async def run_escalations(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.alerting.execute"))):
    changed = await advance_escalations(db)
    return {"advanced": len(changed), "alerts": [serialize_alert(row) for row in changed]}


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.alerting.read"))):
    return await alert_summary(db)
