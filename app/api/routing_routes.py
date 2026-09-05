from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.gateway import list_correlated_events
from app.services.routing import correlate_and_route, gateway_routing_status, list_rules, serialize_rule, upsert_rule

router = APIRouter(prefix="/v1/routing", tags=["routing"])


class RoutingRuleIn(BaseModel):
    event_type: str
    source_system_key: str | None = None
    minimum_severity: str = "info"
    target_systems: list[str] = Field(default_factory=list)
    create_incident: bool = False
    enabled: bool = True


@router.put("/rules/{rule_key}")
async def set_rule(rule_key: str, body: RoutingRuleIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.routing.write"))):
    row = await upsert_rule(db, rule_key, body.event_type, body.source_system_key, body.minimum_severity, body.target_systems, body.create_incident, body.enabled)
    return serialize_rule(row)


@router.get("/rules")
async def rules(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.routing.read"))):
    return [serialize_rule(row) for row in await list_rules(db)]


@router.post("/correlate/{correlation_id}")
async def route_correlated_event(correlation_id: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.routing.execute"))):
    rows = await list_correlated_events(db, correlation_id=correlation_id, limit=1)
    event = next((row for row in rows if row.correlation_id == correlation_id), None)
    if event is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="correlated event not found")
    return await correlate_and_route(db, event)


@router.get("/gateway-status")
async def gateway_status(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.gateway.read"))):
    return await gateway_routing_status(db)
